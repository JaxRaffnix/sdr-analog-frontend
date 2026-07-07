import math
import itertools
import numpy as np

class SpectrumSignal:
    def __init__(self, tones=None):
        self.tones = tones if tones is not None else {}

    def total_power_dbm(self):
        if not self.tones:
            return -999.0
        total_mw = sum(10**(p_dbm / 10) for p_dbm in self.tones.values())
        return 10 * math.log10(total_mw)

    def top_tones_str(self, limit=5):
        if not self.tones:
            return "Kein Signal"
        sorted_tones = sorted(self.tones.items(), key=lambda item: item[1], reverse=True)
        return "<br>".join([f"{f:.1f} MHz: **{p:.2f} dBm**" for f, p in sorted_tones[:limit]])

class RFComponent:
    def __init__(
        self,
        name,
        description="",
        voltage_v=0,
        current_typ_ma=0,
        current_max_ma=0
    ):
        self.name = name
        self.description = description
        self.voltage_v = float(voltage_v)
        self.current_typ_ma = float(current_typ_ma)
        self.current_max_ma = float(current_max_ma)

    def process(self, signal):
        raise NotImplementedError

    def dc_power_typ_mw(self):
        return self.voltage_v * self.current_typ_ma

    def dc_power_max_mw(self):
        return self.voltage_v * self.current_max_ma
    
    def insertion_loss(self, freq_mhz):
        return 0.0

    def dc_power(self):
        return {
            "component": self.name,
            "voltage": self.voltage_v,
            "typ": self.voltage_v*self.current_typ_ma,
            "max": self.voltage_v*self.current_max_ma
        }


class Mixer(RFComponent):
    def __init__(self, name, description, conversion_loss_db, lo_freq_mhz, lo_power_dbm, lo_rf_isolation=35, if_rf_isolation=25):
        super().__init__(
            name=name,
            description=description,
            voltage_v=0.0,
            current_typ_ma=0.0,
            current_max_ma=0.0
        )
        self.conversion_loss_db = conversion_loss_db
        self.lo_freq = lo_freq_mhz
        self.lo_power = lo_power_dbm
        self.lo_rf_iso = lo_rf_isolation
        self.if_rf_iso = if_rf_isolation

    def process(self, signal):
        out_tones = {self.lo_freq: self.lo_power - self.lo_rf_iso}
        for f, p in signal.tones.items():
            out_tones[f] = p - self.if_rf_iso
            out_tones[f + self.lo_freq] = p + self.conversion_loss_db
            out_tones[abs(f - self.lo_freq)] = p + self.conversion_loss_db
        out_signal = SpectrumSignal(out_tones)
        return out_signal, [], signal.total_power_dbm(), out_signal.total_power_dbm()
    

class StaticModel:
    """For simple components like Baluns with constant loss."""
    def __init__(self, loss_db):
        self.loss_db = loss_db
    
    def get_insertion_loss(self, freq):
        return self.loss_db

class TableModel:
    """For filters (LPF, BPF) with datasheet lookup tables."""
    def __init__(self, data_table):
        # data_table expects [freq_mhz, loss_db]
        data = np.array(data_table)
        self.freqs = data[:, 0]
        self.loss = -data[:, 1]  # Ensure loss is negative

    def get_insertion_loss(self, freq):
        return np.interp(freq, self.freqs, self.loss, left=self.loss[0], right=self.loss[-1])

class Filter(RFComponent):
    def __init__(self, name, description, model, datasheet_url="", voltage_v=0.0):
        super().__init__(
            name=name,
            description=description,
            voltage_v=voltage_v,
            current_typ_ma=0.0,
            current_max_ma=0.0
        )

        self.model = model
        self.datasheet_url = datasheet_url

    def insertion_loss(self, freq_mhz):
        return self.model.get_insertion_loss(freq_mhz)

    def process(self, signal, **kwargs):
        out_tones = {}
        for f, p in signal.tones.items():
            # Get dynamic loss from the assigned model
            loss = self.model.get_insertion_loss(f)
            out_tones[f] = p + loss
            
        out_signal = SpectrumSignal(out_tones)
        return out_signal, [], signal.total_power_dbm(), out_signal.total_power_dbm()
    
class AmplifierModel:
    def __init__(self, gain_data, oip3_data, p1db_data):
        # Daten-Struktur: [ [freq_ghz, value], ... ]
        self.gain_data = np.array(gain_data)
        self.oip3_data = np.array(oip3_data)
        self.p1db_data = np.array(p1db_data)

    def get_gain(self, freq_mhz):
        return np.interp(freq_mhz / 1000.0, self.gain_data[:, 0], self.gain_data[:, 1])

    def get_oip3(self, freq_mhz):
        return np.interp(freq_mhz / 1000.0, self.oip3_data[:, 0], self.oip3_data[:, 1])

    def get_p1db(self, freq_mhz):
        return np.interp(freq_mhz / 1000.0, self.p1db_data[:, 0], self.p1db_data[:, 1])
    
class Amplifier(RFComponent):
    def __init__(
        self,
        name,
        description,
        model,
        voltage_v=5.0,
        current_typ_ma=58.0,
        current_max_ma=66.0
    ):
        super().__init__(
            name=name,
            description=description,
            voltage_v=voltage_v,
            current_typ_ma=current_typ_ma,
            current_max_ma=current_max_ma
        )

        self.model = model

    def insertion_loss(self, freq_mhz):
        return -self.model.get_gain(freq_mhz)

    def process(self, signal, **kwargs):
        warnings = []
        out_tones = {}
        
        for f, p in signal.tones.items():
            gain = self.model.get_gain(f) # Dynamischer Gain
            out_tones[f] = p + gain
            
        # IM3 Berechnung mit dynamischem OIP3
        # Wir nehmen hier die Frequenz des ersten Tons für das OIP3-Modell
        if not signal.tones:
            return signal, ["Kein Eingangssignal"], -999, -999
        f_mid = next(iter(signal.tones))
        
        oip3 = self.model.get_oip3(f_mid)
        p1db = self.model.get_p1db(f_mid)
        
        if oip3 is not None and len(out_tones) >= 2:
            im3_products = {}
            for (f1, p1), (f2, p2) in itertools.combinations(out_tones.items(), 2):
                if p1 < -60 or p2 < -60: continue

                f_im3_a, f_im3_b = abs(2 * f1 - f2), abs(2 * f2 - f1)
                p_im3_a = 2 * p1 + p2 - 2 * oip3
                p_im3_b = 2 * p2 + p1 - 2 * oip3

                if p_im3_a > -100: im3_products[f_im3_a] = p_im3_a
                if p_im3_b > -100: im3_products[f_im3_b] = p_im3_b

            for f_im3, p_im3 in im3_products.items():
                if f_im3 in out_tones:
                    mw_existing = 10**(out_tones[f_im3]/10)
                    mw_new = 10**(p_im3/10)
                    out_tones[f_im3] = 10 * math.log10(mw_existing + mw_new)
                else:
                    out_tones[f_im3] = p_im3
        
        out_signal = SpectrumSignal(out_tones)
        return out_signal, warnings, signal.total_power_dbm(), out_signal.total_power_dbm()
    

class PLLADF4351(RFComponent):
    def __init__(
        self,
        name="ADF4351",
        frequency_mhz=1500,
        output_power_dbm=3,
        voltage_v=3.3,
        current_typ_ma=100,
        current_max_ma=150,
        harmonics=None
    ):
        super().__init__(
            name=name,
            description="PLL Synthesizer",
            voltage_v=voltage_v,
            current_typ_ma=current_typ_ma,
            current_max_ma=current_max_ma
        )

        self.frequency_mhz = frequency_mhz
        self.output_power_dbm = output_power_dbm

        # Relative harmonic levels
        self.harmonics = harmonics or {
            2: -20,
            3: -30,
            4: -40
        }

    def add_spur(self, tones):

    spur_spacing = self.reference_frequency / self.divider

    for n in [-2,-1,1,2]:

        spur_freq = self.frequency_mhz + n*spur_spacing

        tones[spur_freq] = self.output_power_dbm - 55


    def output_signal(self):

        tones = {}

        # fundamental
        tones[self.frequency_mhz] = self.output_power_dbm


        # harmonics
        for harmonic, level in self.harmonics.items():
            freq = self.frequency_mhz * harmonic

            # harmonic level relative to carrier
            tones[freq] = self.output_power_dbm + level


        return SpectrumSignal(tones)

##############################################


def analyze_path(name, components, frequencies, input_power_dbm):

    rf_table = []

    totals = {}

    for freq in frequencies:

        power = input_power_dbm

        totals[freq] = power


    for comp in components:

        row = {
            "Component": comp.name
        }

        for freq in frequencies:

            loss = comp.insertion_loss(freq)

            totals[freq] += loss

            row[freq] = loss

        rf_table.append(row)


    dc_table = []

    for comp in components:
        dc = comp.dc_power()

        if dc["voltage"] > 0:
            dc_table.append(dc)


    return {
        "name": name,
        "rf": rf_table,
        "final_power": totals,
        "dc": dc_table
    }


# def analyze_system(path_name, start_signal, components):
#     rf_md = f"### {path_name} - RF Signal\n"
#     rf_md += "| Component | Total P_in | Total P_out | Spektrum (Top 5 Töne) | Warnings |\n"
#     rf_md += "|---|---|---|---|---|\n"

#     # Dictionary zum Gruppieren nach Spannung: {voltage: [typ_power_sum, max_power_sum]}
#     dc_summary = {}

#     current_signal = start_signal
#     for comp in components:
#         current_signal, warnings, p_in, p_out = comp.process(current_signal)
#         warn_str = "<br>".join([f"<span style='color:red;'>⚠️ {w}</span>" for w in warnings])
#         tones_str = current_signal.top_tones_str(limit=5)
#         rf_md += f"| **{comp.name}** | {p_in:.2f} dBm | **{p_out:.2f} dBm** | {tones_str} | {warn_str} |\n"

#         # DC Power Berechnung gruppiert
#         if comp.voltage_v > 0:
#             v = comp.voltage_v
#             if v not in dc_summary:
#                 dc_summary[v] = [0.0, 0.0]
#             dc_summary[v][0] += comp.dc_power_typ_mw()
#             dc_summary[v][1] += comp.dc_power_max_mw()

#     # DC Tabelle nach Spannungsleveln generieren
#     dc_md = f"\n#### DC Power Budget ({path_name})\n"
#     dc_md += "| Rail Voltage (V) | Total Typ. Power (mW) | Total Max. Power (mW) |\n"
#     dc_md += "|---|---|---|\n"

#     grand_total_typ = 0
#     grand_total_max = 0

#     for v in sorted(dc_summary.keys()):
#         typ, max_p = dc_summary[v]
#         dc_md += f"| {v} V | {typ:.1f} | {max_p:.1f} |\n"
#         grand_total_typ += typ
#         grand_total_max += max_p

#     if dc_summary:
#         dc_md += f"| **TOTAL** | **{grand_total_typ:.1f} mW** | **{grand_total_max:.1f} mW** |\n"
#     else:
#         dc_md = "\n*Keine aktiven DC-Komponenten im Pfad.*\n"

#     return rf_md + "\n" + dc_md, current_signal