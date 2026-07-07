from dataclasses import dataclass
import math
import itertools
import numpy as np
import pandas as pd
import plotly.express as px
import pandas as pd
from typing import Callable


@dataclass(slots=True)
class Range:
    minimum: float | None = None
    maximum: float | None = None

    def contains(self, value):
        if self.minimum is not None and value < self.minimum:
            return False

        if self.maximum is not None and value > self.maximum:
            return False

        return True
    

class SpectrumSignal:
    ZERO_POWER = -999.0  # dBm, represents no signal
    def __init__(self, tones=None):
        self.tones = tones or {}

    def total_power_dbm(self):
        if not self.tones: return self.ZERO_POWER
        powers_mw = 10 ** (np.array(list(self.tones.values())) / 10)
        return 10 * np.log10(np.sum(powers_mw))
    
    def add_tone(self, freq, power_dbm):
        """Adds power correctly (mW summation) to an existing tone."""
        if freq in self.tones:
            total_mw = _dbm_to_mw(self.tones[freq]) + _dbm_to_mw(power_dbm)
            self.tones[freq] = _mw_to_dbm(total_mw)
        else:
            self.tones[freq] = power_dbm

    def power_at(self, frequency, default=-np.inf):
        return self.tones.get(frequency, default)
    
    def center_frequency(self):
        if not self.tones:
            return None

        freqs = np.array(list(self.tones.keys()))
        powers = np.array(list(self.tones.values()))

        # convert dBm to mW
        powers_mw = 10 ** (powers / 10)

        return np.sum(freqs * powers_mw) / np.sum(powers_mw)
    

@dataclass(slots=True)
class StageResult:
    name: str
    part_number: str
    signal: SpectrumSignal

    @property
    def tones(self):
        return self.signal.tones

    @property
    def total_power(self):
        return self.signal.total_power_dbm()


# ___________________________________________________________________
# Helper Functions
def _dbm_to_mw(dbm):
    return 10 ** (dbm / 10)

def _mw_to_dbm(mw):
    return 10 * np.log10(mw) if mw > 1e-15 else -999.0

def _merge_tone(tones_dict, freq, power_dbm):
    """Helper to merge power into a dict using mW summation."""
    existing_mw = _dbm_to_mw(tones_dict.get(freq, -999.0))
    new_mw = _dbm_to_mw(power_dbm)
    tones_dict[freq] = _mw_to_dbm(existing_mw + new_mw)


# ___________________________________________________________________
# Signal Processing
def _apply_im3(signal, oip3_dbm, threshold_dbm=-60):
    """Calculates IM3 products and returns a new dictionary of tones."""
    new_tones = signal.tones.copy()
    
    # Only process signals above the threshold to improve performance and realism
    active_tones = [t for t in signal.tones.items() if t[1] > threshold_dbm]
    
    if len(active_tones) < 2:
        return new_tones

    for (f1, p1), (f2, p2) in itertools.combinations(active_tones, 2):
        # Calculate IM3 frequencies
        f_im3a, f_im3b = abs(2 * f1 - f2), abs(2 * f2 - f1)
        
        # IM3 Power = 2*P1 + P2 - 2*OIP3
        p_im3 = 2 * p1 + p2 - (2 * oip3_dbm)
        
        # Add products to spectrum
        if p_im3 > threshold_dbm:
            total_mw_a = _dbm_to_mw(new_tones.get(f_im3a, -999)) + _dbm_to_mw(p_im3)
            new_tones[f_im3a] = _mw_to_dbm(total_mw_a)
            
            total_mw_b = _dbm_to_mw(new_tones.get(f_im3b, -999)) + _dbm_to_mw(p_im3)
            new_tones[f_im3b] = _mw_to_dbm(total_mw_b)
            
    return new_tones


# ___________________________________________________________________
# Core Components
class PowerRail:
    def __init__(self, voltage, current_typ_ma, current_max_ma):
        self.voltage = voltage
        self.current_typ_ma = current_typ_ma
        self.current_max_ma = current_max_ma


class RFComponent:
    def __init__(self, name, part_number, max_input_power_dbm=None, power_rail=None):
        self.name = name           
        self.part_number = part_number 
        self.power_rail = power_rail
        self.max_input_power_dbm = max_input_power_dbm

    def __repr__(self):
        return f"{self.name} ({self.part_number})"

    def check_limits(self, signal):
        """Standardized rating check."""
        pin = signal.total_power_dbm()
        if pin is not None and self.max_input_power_dbm is not None and pin > self.max_input_power_dbm:
            print(f"Rating Exceeded: {pin:.1f} dBm > {self.max_input_power_dbm} dBm")

    def dc_power_report(self):
        if self.power_rail is None:
            return None

        rail = self.power_rail
        return {
            "component": self.name,
            "part_number": self.part_number,
            "voltage": rail.voltage,
            "current_typ_ma": rail.current_typ_ma,
            "current_max_ma": rail.current_max_ma,
            "power_typ_mw": rail.voltage * rail.current_typ_ma,
            "power_max_mw": rail.voltage * rail.current_max_ma,
        }

    def process(self, signal):
        raise NotImplementedError(f"{self.__class__.__name__} must implement the process() method.")


class Amplifier(RFComponent):
    def __init__(
        self, 
        name, 
        part_number, 
        gain_model, 
        p1db_dbm=None, 
        oip3_dbm=None, 
        **kwargs
    ):
        super().__init__(name, part_number,  **kwargs)
        self.gain_model = gain_model
        self.p1db_dbm = p1db_dbm
        self.oip3_dbm = oip3_dbm

    def _get_gain(self, freq):
        return self.gain_model.get_gain(freq) if hasattr(self.gain_model, "get_gain") else self.gain_model
    def _get_p1db(self, freq):
        return self.gain_model.get_p1db(freq) if hasattr(self.gain_model, "get_p1db") else self.p1db_dbm
    def _get_oip3(self, freq):
        return self.gain_model.get_oip3(freq) if hasattr(self.gain_model, "get_oip3") else self.oip3_dbm

    def check_compression(self, signal):
        center_f = signal.center_frequency()
        pout = signal.total_power_dbm()
        p1db = self._get_p1db(center_f)

        if pout >= p1db:
            print(
                f"CRITICAL: {self.name} saturated "
                f"(Pout={pout:.1f} dBm, P1dB={p1db:.1f} dBm)"
            )
        headroom = p1db - pout
        if headroom < 1.0:
            print(f"Compression! Pout is {headroom:.1f} dB from P1dB. Expect high distortion.")

    def process(self, signal: SpectrumSignal):
        self.check_limits(signal)
        
        # 1. Apply Gain
        out_tones = {}
        for f, p in signal.tones.items():
            gain = self._get_gain(f)
            out_tones[f] = p + gain

        amplified = SpectrumSignal(out_tones)
        model_freq = amplified.center_frequency()
        oip3 = self._get_oip3(model_freq)

        # 2. Compression Check
        temp_signal = SpectrumSignal(out_tones)
        pout = temp_signal.total_power_dbm()
        self.check_compression(signal)
            
        # 3. Apply Non-Linearity (IM3)
        center_f = signal.center_frequency()
        oip3 = self._get_oip3(center_f)        
        final_tones = _apply_im3(temp_signal, oip3)
        
        return SpectrumSignal(final_tones)


class Filter(RFComponent):
    def __init__(
        self, 
        name, 
        part_number, 
        insertion_loss: int | float | Callable[[float], float],
        freq_range: Range|None = None,
        rejection_db=100, 
        **kwargs
    ):
        super().__init__(name, part_number, **kwargs)
        self.insertion_loss = insertion_loss        
        self.freq_range = freq_range
        self.rejection_db = abs(rejection_db) if rejection_db else None

    def _get_loss(self, freq):
        if isinstance(self.insertion_loss, (int, float)):
            return self.insertion_loss
        return self.insertion_loss(freq)

    def process(self, signal: SpectrumSignal):
        self.check_limits(signal)

        out_tones = {}
        for freq, power in signal.tones.items():
            if self.freq_range and not self.freq_range.contains(freq):
                loss = self.rejection_db
            else:
                loss = self._get_loss(freq)

            out_tones[freq] = power - abs(loss)
                
        return SpectrumSignal(out_tones)


class Mixer(RFComponent):
    def __init__(
        self,
        name,
        part_number,
        conversion_loss_db,
        lo_rf_iso_db,
        rf_if_iso_db,
        required_lo_power_dbm=None,
        max_lo_power_dbm=None,
        **kwargs,
    ):
        super().__init__(
            name, 
            part_number, 
            **kwargs
        )

        self.conversion_loss_db = conversion_loss_db

        self.lo_signal = None
        self.lo_freq = None
        self.lo_rf_iso = lo_rf_iso_db
        self.if_rf_iso = rf_if_iso_db
        self.required_lo_power_dbm = required_lo_power_dbm
        self.max_lo_power_dbm = max_lo_power_dbm

    def set_lo_signal(self, signal: SpectrumSignal, lo_freq_mhz):
        self.lo_signal = signal
        self.lo_freq = lo_freq_mhz

        lo_power = self.lo_signal.tones.get(self.lo_freq)

        if lo_power is None:
            print(f"LO signal has no carrier at {self.lo_freq:.3f} MHz")
        
        if self.required_lo_power_dbm is not None and abs(lo_power) < self.required_lo_power_dbm:
            print(f"LO drive {lo_power:.1f} dBm below required {self.required_lo_power_dbm:.1f} dBm")

        if self.max_lo_power_dbm is not None and abs(lo_power) > self.max_lo_power_dbm:
            print(f"LO drive {lo_power:.1f} dBm above maximum {self.max_lo_power_dbm:.1f} dBm")


    def process(self, rf_signal: SpectrumSignal):
        self.check_limits(rf_signal)

        if self.lo_signal is None or self.lo_freq is None:
            raise ValueError(
                f"{self.name}: LO signal not configured"
            )

        lo_power = self.lo_signal.tones.get(self.lo_freq)

        if lo_power is None:
            return SpectrumSignal({})

        self.check_limits(rf_signal)

        out_tones = {}

        # LO leakage
        for f, p in self.lo_signal.tones.items():
            _merge_tone(
                out_tones,
                f,
                p - self.lo_rf_iso
            )

        # RF feedthrough + mixing
        for f, p in rf_signal.tones.items():

            _merge_tone(
                out_tones,
                f,
                p - self.if_rf_iso
            )

            conv_p = p - self.conversion_loss_db

            _merge_tone(
                out_tones,
                f + self.lo_freq,
                conv_p
            )

            _merge_tone(
                out_tones,
                abs(f - self.lo_freq),
                conv_p
            )

        return SpectrumSignal(out_tones)

# ___________________________________________________________________
# Models

class TableModel:
    """For filters (LPF, BPF) with datasheet lookup tables."""
    def __init__(self, data_table):
        # data_table expects [freq_mhz, loss_db]
        data = np.array(data_table)
        self.freqs = data[:, 0]
        self.loss = data[:, 1] 

    def __call__(self, freq):
        """Allows the model to be called like a function: model(freq)"""
        return np.interp(freq, self.freqs, self.loss, left=self.loss[0], right=self.loss[-1])
    

class AmplifierModel:
    def __init__(self, gain_data, oip3_data, p1db_data):
        self.gain = TableModel(gain_data)
        self.oip3 = TableModel(oip3_data)
        self.p1db = TableModel(p1db_data)

    def get_gain(self, freq_mhz):
        return self.gain(freq_mhz)

    def get_oip3(self, freq_mhz):
        return self.oip3(freq_mhz)

    def get_p1db(self, freq_mhz):
        return self.p1db(freq_mhz)
    

class ADC(RFComponent):
    def __init__(
        self,
        name,
        part_number,
        sample_rate_mhz,
        bandwidth_mhz,
        resolution_bits,
        full_scale_dbm,
        **kwargs,
    ):
        super().__init__(name, part_number, **kwargs)
        self.sample_rate_mhz = sample_rate_mhz
        self.bandwidth_mhz = bandwidth_mhz
        self.resolution_bits = resolution_bits
        self.full_scale_dbm = full_scale_dbm

    def process(self, signal: SpectrumSignal):
        self.check_limits(signal)

        input_power = signal.total_power_dbm()
        if input_power > self.full_scale_dbm:
            print(
                f"ADC clipping: "
                f"{input_power:.1f} dBm > "
                f"full scale {self.full_scale_dbm:.1f} dBm"
            )



        # Check frequency range
        for freq in signal.tones:
            if freq > self.bandwidth_mhz:
                print(
                    f"ADC bandwidth exceeded: "
                    f"{freq:.1f} MHz > "
                    f"{self.bandwidth_mhz:.1f} MHz"
                )
            if freq > self.sample_rate_mhz / 2:
                print(
                    f"Signal at {freq:.1f} MHz "
                    f"is in higher Nyquist zone"
                )

        return signal
    

# ___________________________________________________________________
# Signal Sources
class Source(RFComponent):
    def __init__(
        self,
        name,
        part_number,
        freq_mhz,
        output_power_dbm,
        freq_range: Range|None = None,
        power_range: Range|None = None,
        harmonics=None,
        pfd_freq_mhz=None,
        spur_level_dbc=None,
        dc=None,
        **kwargs,
    ):
        super().__init__(name, part_number, **kwargs)
        self.freq_mhz = freq_mhz
        self.output_power_dbm = output_power_dbm
        self.freq_range = freq_range
        self.power_range = power_range
        self.harmonics = harmonics or {}
        self.pfd_freq_mhz  = pfd_freq_mhz
        self.spur_level_dbc = spur_level_dbc
        self.dc = dc

    def check_range(self):
        if self.freq_range is not None and not self.freq_range.contains(self.freq_mhz):
            print(
                f"Frequency {self.freq_mhz:.1f} MHz outside "
                f"range {self.freq_range.minimum:.1f}-"
                f"{self.freq_range.maximum:.1f} MHz"
            )
        if self.power_range is not None and not self.power_range.contains(self.output_power_dbm):
            print(
                f"Output power {self.output_power_dbm:.1f} dBm outside "
                f"range {self.power_range.minimum:.1f}-"
                f"{self.power_range.maximum:.1f} dBm"
            )
    
    def _apply_harmonics(self, signal):
        tones = signal.tones.copy()
        for f_fund, p_fund in signal.tones.items():
            for order, level_dbc in self.harmonics.items():
                f_harm = f_fund * order
                p_harm = p_fund - abs(level_dbc)

                _merge_tone(tones,f_harm,p_harm)

        return SpectrumSignal(tones)
    
    def _apply_spurs(self, signal):
        if self.pfd_freq_mhz is None or self.spur_level_dbc is None:
            return signal

        tones = signal.tones.copy()
        carrier_power = signal.tones[self.freq_mhz]

        # Generate first N PFD spurs
        for n in range(1, 6):
            spur_power = carrier_power - abs(self.spur_level_dbc)
            for spur_freq in (
                self.freq_mhz + n * self.pfd_freq_mhz,
                self.freq_mhz - n * self.pfd_freq_mhz,
            ):
                if spur_freq > 0:
                    tones[spur_freq] = spur_power

        return SpectrumSignal(tones)

    def process(self, signal=None):
        self.check_limits(signal)
        self.check_range()

        signal = SpectrumSignal({self.freq_mhz: self.output_power_dbm})
        if self.harmonics:
            signal = self._apply_harmonics(signal)
        if self.spur_level_dbc is not None:
            signal = self._apply_spurs(signal)

        return signal
    

class AntennaSource(RFComponent):
    def __init__(self, name, temp_k=290.0):
        super().__init__(name, "Antenna")
        self.temp_k = temp_k # Kelvin
        self.tones = {}

    def add_signal(self, freq_mhz, power_dbm):
        """Adds a wanted signal or an interferer."""
        self.tones[freq_mhz] = power_dbm
        return self

    def add_thermal_noise(self, bandwidth_mhz):
        """Adds thermal noise floor: -174 dBm/Hz + 10*log10(BW)."""
        # Noise (dBm) = -174 + 10*log10(BW_in_Hz)
        bw_hz = bandwidth_mhz * 1e6
        noise_floor_dbm = -174 + 10 * math.log10(bw_hz)
        self.tones[0.0] = noise_floor_dbm # Or apply to a range of frequencies
        return self

    def process(self, signal=None):
        # Returns the composite signal as the start of the RX path
        return SpectrumSignal(self.tones)

# ___________________________________________________________________
# DC Power Calculation
def calculate_system_budget(components):
    # 1. Extract reports concisely
    reports = [c.dc_power_report() for c in components if c.dc_power_report()]
    if not reports:
        return None

    df = pd.DataFrame(reports)

    # 2. Rename columns for clean display
    df = df.rename(columns={
        "voltage": "Voltage [V]",
        "component": "Component",
        "current_typ_ma": "Current typ [mA]",
        "current_max_ma": "Current max [mA]",
        "power_typ_mw": "Power typ [mW]",
        "power_max_mw": "Power max [mW]",
    })

    # 3. Group by voltage and inject a subtotal row for each rail
    rows_with_subtotals = []
    
    for voltage, group in df.groupby("Voltage [V]"):
        # Add the individual devices for this rail
        rows_with_subtotals.append(group)
        
        # Add a subtotal row
        subtotal = pd.DataFrame({
            "Voltage [V]": [voltage],
            "Component": [f"↳ {voltage}V RAIL TOTAL"],
            "Current typ [mA]": [group["Current typ [mA]"].sum()],
            "Current max [mA]": [group["Current max [mA]"].sum()],
            "Power typ [mW]": [group["Power typ [mW]"].sum()],
            "Power max [mW]": [group["Power max [mW]"].sum()]
        })
        rows_with_subtotals.append(subtotal)

    # 4. Combine everything
    final_df = pd.concat(rows_with_subtotals, ignore_index=True)

    # 5. Set a MultiIndex to visually nest the devices under their voltage rail
    # We drop part_number here to keep the visual focus on current/power, 
    # but you can easily add it back to the index if needed.
    final_df = final_df.set_index(["Voltage [V]", "Component"])
    
    # Optional: Keep only the columns you care about most
    columns_to_show = ["Current typ [mA]", "Current max [mA]", "Power typ [mW]", "Power max [mW]"]
    
    return final_df[columns_to_show]

# ___________________________________________________________________
# Run Simulation Function
def run_simulation(components, signal) -> list[StageResult]:
    log = []

    for component in components:
        signal= component.process(signal)

        log.append(
            StageResult(
                name=component.name,
                part_number=component.part_number,
                signal=signal,
            )
        )

    return log


def format_simulation_results(log):
    return pd.DataFrame([
        {
            "Component": stage["name"],
            "Part Number": stage["part_number"],
            "Total P (dBm)": f"{stage['total_power']:.2f}",
            "Spectrum": ", ".join(
                f"{f:.0f} MHz: {p:.1f} dBm"
                for f, p in stage["tones"].items()
            ),
        }
        for stage in log
    ])


def plot_spectrum(log: list[StageResult], component: str):
    stage = next(s for s in log if s.name == component)

    df = pd.DataFrame(
        stage.tones.items(),
        columns=["Frequency (MHz)", "Power (dBm)"],
    )

    fig = px.bar(
        df,
        x="Frequency (MHz)",
        y="Power (dBm)",
        title=f"Spectrum at {component}",
        range_y=[-120, 20],
    )

    fig.update_traces(width=2)
    return fig


def create_frequency_matrix(log):
    freqs = sorted({
        f
        for stage in log
        for f in stage.tones
    })

    return (
        pd.DataFrame(
            {
                stage.name: [
                    stage.tones.get(f, np.nan)
                    for f in freqs
                ]
                for stage in log
            },
            index=freqs,
        )
        .rename_axis("Frequency (MHz)")
    )


def style_rf_matrix(df):
    return (
        df.style
        .background_gradient(
            cmap="viridis",
            axis=None,
            vmin=-80,
            vmax=10,
        )
        .format("{:.1f} dBm", na_rep="-")
    )