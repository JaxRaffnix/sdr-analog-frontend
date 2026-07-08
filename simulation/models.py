from dataclasses import dataclass, field
import math
import itertools
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from typing import Callable


# ___________________________________________________________________
# Signal

THERMAL_NOISE_FLOOR = -174.0  # dBm/Hz at room temperature

class SpectrumSignal:
    def __init__(self, tones=None, noise_power_dbm=THERMAL_NOISE_FLOOR):
        self.tones = tones.copy() if tones is not None else {}
        self.noise_power_dbm = noise_power_dbm

    def total_power_dbm(self):
        if not self.tones: 
            return -math.inf
        powers_mw = _dbm_to_mw(np.array(list(self.tones.values())))
        return 10 * np.log10(np.sum(powers_mw))
    
    def add_tone(self, freq, power_dbm):
        if freq in self.tones:
            existing_mw = _dbm_to_mw(self.tones[freq])
            added_mw = _dbm_to_mw(power_dbm)
            self.tones[freq] = _mw_to_dbm(existing_mw + added_mw)
        else:
            self.tones[freq] = power_dbm

    def power_at(self, frequency, default=-np.inf):
        power = self.tones.get(frequency, default)
        if power == -np.inf:
            raise ValueError(f"Frequency {frequency} Hz not found in signal tones.")
        return power
    
    def effective_frequency(self):
        if not self.tones:
            return None

        freqs = np.array(list(self.tones.keys()))
        powers = np.array(list(self.tones.values()))
        powers_mw = _dbm_to_mw(powers)
        return np.sum(freqs * powers_mw) / np.sum(powers_mw)

    def get_snr_db(self, freq_hz: float) -> float:
        """Returns the SNR in dB for a specific tone."""
        tone_power = self.power_at(freq_hz)            
        return tone_power - self.noise_power_dbm
    

# ___________________________________________________________________
# Data Classes
@dataclass(slots=True)
class Range:
    minimum: float | None = None
    maximum: float | None = None

    def __contains__(self, value):
        if self.minimum is not None and value < self.minimum:
            return False
        if self.maximum is not None and value > self.maximum:
            return False
        return True


@dataclass(slots=True)
class StageResult:
    name: str
    part_number: str
    signal: SpectrumSignal

    @property
    def tones(self):
        return self.signal.tones
    
    @property
    def noise_dbm(self):
        return self.signal.noise_power_dbm

    @property
    def total_power(self):
        return self.signal.total_power_dbm()


class PowerRail:
    def __init__(self, voltage, current_typ_a, current_max_a):
        self.voltage = voltage
        self.current_typ_a = current_typ_a
        self.current_max_a = current_max_a


# ___________________________________________________________________
# Helper Functions
def _dbm_to_mw(dbm):
    return 10 ** (dbm / 10)

def _mw_to_dbm(mw):
    return 10 * np.log10(mw)


# ___________________________________________________________________
# Core Components
class RFComponent:
    THERMAL_NOISE_FLOOR = -174.0  # dBm/Hz at room temperature
    def __init__(self, name, part_number, max_input_power_dbm=None, power_rail=None):
        self.name = name           
        self.part_number = part_number 
        self.power_rail = power_rail
        self.max_input_power_dbm = max_input_power_dbm

    def __repr__(self):
        return f"{self.name} ({self.part_number})"

    def check_limits(self, signal):
        pin = signal.total_power_dbm()
        if self.max_input_power_dbm is not None and pin > self.max_input_power_dbm:
            print(f"[{self.name}] Rating Exceeded: {pin:.1f} dBm > {self.max_input_power_dbm} dBm")

    def dc_power_report(self):
        if self.power_rail is None:
            return None

        rail = self.power_rail
        return {
            "component": self.name,
            "part_number": self.part_number,
            "voltage": rail.voltage,
            "current_typ_a": rail.current_typ_a,
            "current_max_a": rail.current_max_a,
            "power_typ_w": round(rail.voltage * rail.current_typ_a, 6),
            "power_max_w": round(rail.voltage * rail.current_max_a, 6),
        }

    def process(self, signal):
        raise NotImplementedError(f"{self.__class__.__name__} must implement the process() method.")

    def gain_db(self, freq_hz=None):
        raise NotImplementedError(f"{self.__class__.__name__} must implement the gain_db() method.")

    def noise_figure_db(self, freq_hz=None):
        raise NotImplementedError(f"{self.__class__.__name__} must implement the noise_figure_db() method.")

    def calc_output_noise(self, input_noise_dbm: float, gain_db: float, noise_figure_db: float) -> float:
        amplified_input_noise_mw = 10 ** ((input_noise_dbm + gain_db) / 10)
        added_noise_mw = _dbm_to_mw(self.THERMAL_NOISE_FLOOR + noise_figure_db + gain_db)
        return _mw_to_dbm(amplified_input_noise_mw + added_noise_mw)


class Amplifier(RFComponent):
    def __init__(
        self, 
        name, 
        part_number, 
        gain_model, 
        p1db_dbm=None, 
        oip3_dbm=None, 
        noise_figure_db=None,
        max_output_power_dbm=None,
        **kwargs
    ):
        super().__init__(name, part_number, **kwargs)
        self.gain_model = gain_model
        self.p1db_dbm = p1db_dbm
        self.oip3_dbm = oip3_dbm
        self.nf_db = noise_figure_db
        self.max_output_power_dbm = max_output_power_dbm

    def _get_gain(self, freq):
        return self.gain_model.get_gain(freq) if hasattr(self.gain_model, "get_gain") else self.gain_model
    def _get_p1db(self, freq):
        return self.gain_model.get_p1db(freq) if hasattr(self.gain_model, "get_p1db") else self.p1db_dbm
    def _get_oip3(self, freq):
        return self.gain_model.get_oip3(freq) if hasattr(self.gain_model, "get_oip3") else self.oip3_dbm

    def gain_db(self, freq_hz=None):
        return self._get_gain(freq_hz or 0.0)

    def noise_figure_db(self, freq_hz=None):
        return self.nf_db if self.nf_db is not None else 0.0
    
    def _apply_im3(self, signal: SpectrumSignal, oip3_dbm: float, threshold_dbm: float = -60):
        active_tones = [(f, p) for f, p in signal.tones.items() if p > threshold_dbm]        
        if len(active_tones) < 2:
            return

        for (f1, p1), (f2, p2) in itertools.combinations(active_tones, 2):
            f_im3a, f_im3b = abs(2 * f1 - f2), abs(2 * f2 - f1)            
            p_im3a = (2 * p1) + p2 - (2 * oip3_dbm)
            p_im3b = (2 * p2) + p1 - (2 * oip3_dbm)
            
            if p_im3a > threshold_dbm:
                signal.add_tone(f_im3a, p_im3a)
            if p_im3b > threshold_dbm:
                signal.add_tone(f_im3b, p_im3b)

    def check_compression(self, signal, eff_freq):
        if signal is None or not signal.tones:
            return

        pout = signal.total_power_dbm()
        p1db = self._get_p1db(eff_freq)
        if p1db is None:
            return

        if pout >= p1db:
            print(f"[{self.name}] CRITICAL: Saturated (Pout={pout:.1f} dBm, P1dB={p1db:.1f} dBm)")
        headroom = p1db - pout
        if 0 < headroom < 1.0:
            print(f"[{self.name}] Compression! Pout is {headroom:.1f} dB from P1dB. Expect high distortion.")

    def check_output_power(self, signal):
        if self.max_output_power_dbm is None or signal is None or not signal.tones:
            return

        pout = signal.total_power_dbm()
        if pout > self.max_output_power_dbm:
            print(f"[{self.name}] Output exceeds limit: {pout:.1f} dBm > {self.max_output_power_dbm:.1f} dBm")

    def process(self, signal: SpectrumSignal):
        self.check_limits(signal)
        eff_freq = signal.effective_frequency()

        nom_gain = self.gain_db(eff_freq)
        nom_nf = self.noise_figure_db(eff_freq)
        new_noise = self.calc_output_noise(signal.noise_power_dbm, nom_gain, nom_nf)

        out_signal = SpectrumSignal(noise_power_dbm=new_noise)

        for f, p in signal.tones.items():
            out_signal.add_tone(f, p + self._get_gain(f))

        self.check_compression(out_signal, eff_freq)
        self.check_output_power(out_signal)

        oip3 = self._get_oip3(eff_freq) if eff_freq is not None else None
        if oip3 is not None:
            self._apply_im3(out_signal, oip3)

        return out_signal


class Filter(RFComponent):
    def __init__(
        self, 
        name, 
        part_number, 
        insertion_loss: int | float | Callable[[float], float],
        freq_range: Range|None = None,
        rejection_db: float = 100.0, 
        **kwargs
    ):
        super().__init__(name, part_number, **kwargs)
        self.insertion_loss = insertion_loss        
        self.freq_range = freq_range
        self.rejection_db = abs(rejection_db) if rejection_db else None

    def _get_loss(self, freq: float) -> float:
        if self.freq_range and freq not in self.freq_range:
            return self.rejection_db
            
        if isinstance(self.insertion_loss, (int, float)):
            return float(self.insertion_loss)
        return self.insertion_loss(freq)

    def gain_db(self, freq_hz=None):
        if freq_hz is None:
            raise ValueError(f"{self.name}: frequency is required to evaluate filter gain")
        return -abs(self._get_loss(freq_hz))

    def noise_figure_db(self, freq_hz=None):
        if freq_hz is None:
            raise ValueError(f"{self.name}: frequency is required to evaluate filter noise figure")
        return abs(self._get_loss(freq_hz))

    def process(self, signal: SpectrumSignal):
        self.check_limits(signal)

        eff_freq = signal.effective_frequency()
        new_noise = self.calc_output_noise(
            input_noise_dbm=signal.noise_power_dbm, 
            gain_db=self.gain_db(eff_freq), 
            noise_figure_db=self.noise_figure_db(eff_freq)
        )

        out_signal = SpectrumSignal(noise_power_dbm=new_noise)
        for freq, power in signal.tones.items():
            loss = self._get_loss(freq)
            out_signal.add_tone(freq, power - abs(loss))
                
        return out_signal


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
        noise_figure_db=None,
        **kwargs,
    ):
        super().__init__(name, part_number, **kwargs)
        self.conversion_loss_db = abs(conversion_loss_db)
        self.lo_rf_iso = abs(lo_rf_iso_db)
        self.rf_if_iso = abs(rf_if_iso_db)
        self.required_lo_power_dbm = required_lo_power_dbm
        self.max_lo_power_dbm = max_lo_power_dbm
        self.nf_db = noise_figure_db if noise_figure_db is not None else self.conversion_loss_db
        self.lo_signal = None
        self.lo_freq = None

    def gain_db(self, freq_hz=None):
        return -self.conversion_loss_db

    def noise_figure_db(self, freq_hz=None):
        return self.nf_db

    def set_lo_signal(self, signal: SpectrumSignal, lo_freq_hz):
        self.lo_signal = signal
        self.lo_freq = lo_freq_hz

        lo_power = signal.power_at(lo_freq_hz)
        if self.required_lo_power_dbm and lo_power < self.required_lo_power_dbm:
            print(f"[{self.name}] LO drive {lo_power:.1f} dBm low (req: {self.required_lo_power_dbm})")
        if self.max_lo_power_dbm and lo_power > self.max_lo_power_dbm:
            print(f"[{self.name}] LO drive {lo_power:.1f} dBm high (max: {self.max_lo_power_dbm})")

    def process(self, rf_signal: SpectrumSignal):
        self.check_limits(rf_signal)

        if self.lo_signal is None:
            raise ValueError(f"Mixer {self.name} missing LO signal")
        
        new_noise = self.calc_output_noise(
            rf_signal.noise_power_dbm, 
            gain_db=self.gain_db(), 
            noise_figure_db=self.noise_figure_db()
        )
        out_signal = SpectrumSignal(noise_power_dbm=new_noise)

        for f, p in self.lo_signal.tones.items():
            out_signal.add_tone(f, p - self.lo_rf_iso)

        for f, p in rf_signal.tones.items():
            out_signal.add_tone(f, p - self.rf_if_iso)
            conv_p = p - self.conversion_loss_db
            out_signal.add_tone(abs(f + self.lo_freq), conv_p)
            out_signal.add_tone(abs(f - self.lo_freq), conv_p)

        # TODO: RF and IF Max values
        # lo_power = self.lo_signal.tones.get(self.lo_freq)
        # rf_input_power = rf_signal.total_power_dbm()
        # if self.max_rf_input_power_dbm is not None and rf_input_power > self.max_rf_input_power_dbm:
        #     print(f"{self.name} RF input exceeds limit: {rf_input_power:.1f} dBm > {self.max_rf_input_power_dbm:.1f} dBm")

        # if self.max_if_output_power_dbm is not None:
        #     if out_signal.total_power_dbm() > self.max_if_output_power_dbm:
        #         print(
        #             f"{self.name} IF output exceeds limit: "
        #             f"{out_signal.total_power_dbm():.1f} dBm > {self.max_if_output_power_dbm:.1f} dBm"
        #         )

        return out_signal

# ___________________________________________________________________
# Models

class TableModel:
    def __init__(self, data_table):
        # data_table expects [freq_hz, loss_db]
        data = np.array(data_table)
        self.freqs = data[:, 0]
        self.loss = data[:, 1] 

    def __call__(self, freq):
        return np.interp(freq, self.freqs, self.loss, left=self.loss[0], right=self.loss[-1])
    

class AmplifierModel:
    def __init__(self, gain_data, oip3_data, p1db_data):
        self.gain = TableModel(gain_data)
        self.oip3 = TableModel(oip3_data)
        self.p1db = TableModel(p1db_data)

    def get_gain(self, freq_hz):
        return self.gain(freq_hz)

    def get_oip3(self, freq_hz):
        return self.oip3(freq_hz)

    def get_p1db(self, freq_hz):
        return self.p1db(freq_hz)
    

class ADC(RFComponent):
    def __init__(
        self,
        name,
        part_number,
        sample_rate_hz,
        bandwidth_hz,
        resolution_bits,
        full_scale_dbm,
        **kwargs,
    ):
        super().__init__(name, part_number, **kwargs)
        self.sample_rate_hz = sample_rate_hz
        self.bandwidth_hz = bandwidth_hz
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
        elif input_power > self.full_scale_dbm - 3:
            print(
                f"ADC input is close to full scale: "
                f"{self.full_scale_dbm - input_power:.1f} dB headroom"
            )

        quant_snr_db = 6.02 * self.resolution_bits + 1.76
        quant_noise_dbm = self.full_scale_dbm - quant_snr_db

        input_noise_mw = 10 ** (signal.noise_power_dbm / 10)
        quant_noise_mw = 10 ** (quant_noise_dbm / 10)
        total_noise_dbm = 10 * math.log10(input_noise_mw + quant_noise_mw)
        out_signal = SpectrumSignal(noise_power_dbm=total_noise_dbm)

        for freq, power in signal.tones.items():
            if freq > self.sample_rate_hz / 2:
                alias_freq = abs(freq - self.sample_rate_hz * round(freq / self.sample_rate_hz))
                out_signal.add_tone(alias_freq, power)
            else:
                out_signal.add_tone(freq, power)

        pout = out_signal.total_power_dbm()
        if pout > self.full_scale_dbm:
            print(f"[{self.name}] Clipping! {pout:.1f} dBm > FS {self.full_scale_dbm} dBm")
        elif pout > self.full_scale_dbm - 3:
            print(f"[{self.name}] Low Headroom: {self.full_scale_dbm - pout:.1f} dB")
        for freq in signal.tones:
            if freq > self.bandwidth_hz:
                print(f"[{self.name}] Warning: Frequency exceeds ADC bandwidth: {freq / 1e6:.1f} MHz > {self.bandwidth_hz / 1e6:.1f} MHz")
            if freq > self.sample_rate_hz / 2:
                    print(f"Signal at {freq / 1e6:.1f} MHz is in higher Nyquist zone")

        return out_signal
    

# ___________________________________________________________________
# Signal Sources
class Source(RFComponent):
    def __init__(
        self,
        name,
        part_number,
        freq_hz,
        output_power_dbm,
        freq_range: Range|None = None,
        power_range: Range|None = None,
        harmonics=None,
        pfd_freq_hz=None,
        spur_level_dbc=None,
        fs_hz=None,
        image_suppression=-50,
        **kwargs,
    ):
        super().__init__(name, part_number, **kwargs)
        self.freq_hz = freq_hz
        self.output_power_dbm = output_power_dbm
        self.freq_range = freq_range
        self.power_range = power_range
        self.harmonics = harmonics or {}
        self.pfd_freq_hz  = pfd_freq_hz
        self.spur_level_dbc = spur_level_dbc
        self.fs_hz = fs_hz
        self.image_suppression = image_suppression

    def check_range(self):
        if self.freq_range is not None and not self.freq_hz in self.freq_range:
            print(
                f"Frequency {self.freq_hz / 1e6:.1f} MHz outside "
                f"range {self.freq_range.minimum / 1e6:.1f}-"
                f"{self.freq_range.maximum / 1e6:.1f} MHz"
            )
        if self.power_range is not None and not self.output_power_dbm in self.power_range:
            print(
                f"Output power {self.output_power_dbm:.1f} dBm outside "
                f"range {self.power_range.minimum:.1f}-"
                f"{self.power_range.maximum:.1f} dBm"
            )

    def _apply_sinc_roll_off(self, signal, fs_hz):
        """Applies the DAC sinc(x) roll-off: sin(pi*f/fs) / (pi*f/fs)"""
        tones = signal.tones.copy()
        for f, p in tones.items():
            if f > 0:
                sinc_val = np.sin(np.pi * f / fs_hz) / (np.pi * f / fs_hz)
                loss_db = 20 * np.log10(abs(sinc_val))
                tones[f] = p + loss_db
        return SpectrumSignal(tones)


    def _apply_images(self, signal: SpectrumSignal, fs_hz: float) -> SpectrumSignal:
        # 1. Initialize the new output signal with the incoming tones and noise floor
        out_signal = SpectrumSignal(
            tones=signal.tones, 
            noise_power_dbm=signal.noise_power_dbm
        )
        
        # 2. Safely get the carrier power
        carrier_power = signal.power_at(self.freq_hz)
        if carrier_power == -math.inf:
            return out_signal  # Carrier missing, nothing to generate images from
            
        # 3. Add First Nyquist zone images
        images = [fs_hz - self.freq_hz, fs_hz + self.freq_hz]
        for img_f in images:
            if img_f > 0:
                out_signal.add_tone(img_f, carrier_power + self.image_suppression)
                
        return out_signal

    def _apply_harmonics(self, signal: SpectrumSignal) -> SpectrumSignal:
        out_signal = SpectrumSignal(
            tones=signal.tones, 
        )        
        for f_fund, p_fund in signal.tones.items():
            for order, level_dbc in self.harmonics.items():
                f_harm = f_fund * order
                p_harm = p_fund - abs(level_dbc)
                
                out_signal.add_tone(f_harm, p_harm)
                
        return out_signal
    
    def _apply_spurs(self, signal):
        if self.pfd_freq_hz is None or self.spur_level_dbc is None:
            return signal

        tones = signal.tones.copy()
        carrier_power = signal.tones[self.freq_hz]

        # Generate first N PFD spurs
        for n in range(1, 6):
            spur_power = carrier_power - abs(self.spur_level_dbc)
            for spur_freq in (
                self.freq_hz + n * self.pfd_freq_hz,
                self.freq_hz - n * self.pfd_freq_hz,
            ):
                if spur_freq > 0:
                    tones[spur_freq] = spur_power

        return SpectrumSignal(tones)

    def process(self, signal=None):
        self.check_limits(signal)
        self.check_range()

        signal = SpectrumSignal({self.freq_hz: self.output_power_dbm})
        if self.harmonics:
            signal = self._apply_harmonics(signal)
        if self.spur_level_dbc is not None:
            signal = self._apply_spurs(signal)

        if hasattr(self, 'fs_hz') and self.fs_hz:
            signal = self._apply_sinc_roll_off(signal, self.fs_hz)
            signal = self._apply_images(signal, self.fs_hz)

        return signal
    

class AntennaSource(RFComponent):
    def __init__(
            self, 
            name: str, 
            part_number: str, 
            bandwidth_hz: float,
            **kwargs,
        ):
        super().__init__(name, part_number, **kwargs)
        self.bandwidth_hz = bandwidth_hz
        self.signal = SpectrumSignal()

    def add_signal(self, freq_hz: float, power_dbm: float):
        self.signal.add_tone(freq_hz, power_dbm)
        return self

    def process(self, input_signal = None) -> SpectrumSignal:
        # add thermal noise
        noise_floor_dbm = -174.0 + 10 * math.log10(self.bandwidth_hz)
        self.signal.noise_power_dbm = noise_floor_dbm
        
        return SpectrumSignal(
            tones=self.signal.tones, 
            noise_power_dbm=self.signal.noise_power_dbm
        )

# ___________________________________________________________________
# DC Power Calculation
def calculate_system_budget(components):
    reports = [c.dc_power_report() for c in components if c.dc_power_report()]
    if not reports:
        return None

    df = pd.DataFrame(reports).rename(columns={
        "voltage": "Voltage [V]",
        "part_number": "part_number",
        "current_typ_a": "Current typ [A]",
        "current_max_a": "Current max [A]",
        "power_typ_w": "Power typ [W]",
        "power_max_w": "Power max [W]",
    })

    rows = []
    for voltage, group in df.groupby("Voltage [V]"):
        rows.append(group)        
        rows.append(pd.DataFrame({
            "Voltage [V]": [voltage],
            "part_number": [f"↳ {voltage}V RAIL TOTAL"],
            "Current typ [A]": [group["Current typ [A]"].sum()],
            "Current max [A]": [group["Current max [A]"].sum()],
            "Power typ [W]": [group["Power typ [W]"].sum()],
            "Power max [W]": [group["Power max [W]"].sum()]
        }))

    # Calculate Grand Total
    grand_total = pd.DataFrame({
        "Voltage [V]": ["SYSTEM"],
        "part_number": ["GRAND TOTAL"],
        "Current typ [A]": [df["Current typ [A]"].sum()],
        "Current max [A]": [df["Current max [A]"].sum()],
        "Power typ [W]": [df["Power typ [W]"].sum()],
        "Power max [W]": [df["Power max [W]"].sum()]
    })
    rows.append(grand_total)

    final_df = pd.concat(rows, ignore_index=True)
    final_df = final_df.set_index(["Voltage [V]", "part_number"]).round(2)
    
    return final_df[["Current typ [A]", "Current max [A]", "Power typ [W]", "Power max [W]"]]

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
            "Component": stage.name,
            "Part Number": stage.part_number,
            "Total P (dBm)": f"{stage.total_power:.2f}",
            "Spectrum": ", ".join(
                f"{f / 1e6:.3f} MHz: {p:.1f} dBm"
                for f, p in stage.tones.items()
            ),
        }
        for stage in log
    ])

# ___________________________________________________________________
# plotting
def plot_spectrum(log: list[StageResult], component: str):

    stage = next(s for s in log if s.name == component)
    df = (
        pd.DataFrame(
            stage.tones.items(),
            columns=["Frequency (MHz)", "Power (dBm)"],
        )
        .assign(**{"Frequency (MHz)": lambda x: x["Frequency (MHz)"].div(1e6).round(3)})
        .sort_values("Frequency (MHz)")
    )

    fig = go.Figure()

    # Stem lines
    for _, row in df.iterrows():
        fig.add_trace(
            go.Scatter(
                x=[row["Frequency (MHz)"], row["Frequency (MHz)"]],
                y=[-120, row["Power (dBm)"]],
                mode="lines",
                line=dict(width=2),
                hoverinfo="skip",
                showlegend=False,
            )
        )
    fig.update_layout(
        height=450,
        xaxis=dict(title="Frequency [MHz]", showgrid=True, zeroline=False,),
        yaxis=dict(title="Power [dBm]", range=[-120, 20], showgrid=True,),
        title=dict(text=f"Spectrum at {component}",x=0.5,xanchor="center",)
    )

    return fig


# ___________________________________________________________________
# table formatting
def create_frequency_matrix(log):
    # Get all frequencies, excluding DC (0.0 Hz)
    freqs = sorted({
        f for stage in log
        for f in stage.tones if f > 100_000  # Filter out everything below 100 kHz
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
        # Apply gradient only to the numerical values (exclude index)
        .background_gradient(
            cmap="viridis",
            axis=None,
            vmin=-80,
            vmax=10,
        )
        # Use a dictionary or subset to ensure only cell values are formatted as dBm
        .format("{:.1f} dBm", na_rep="-")
        # Explicitly format the index (frequencies) separately to avoid "dBm" units
        .format_index(lambda f: f"{f / 1e6:.2f} MHz", axis=0) 
    )


# ___________________________________________________________________
# Noise Budget Calculation



def print_noise_budget(results_rx, target_freq):
    print(f"{'Stage':<15}  {'Noise Floor':<12} | {'SNR (dB)':<8}")
    print("-" * 65)
    
    for stage in results_rx:
        name = stage.name
        sig = stage.signal
        
        snr = sig.get_snr_db(target_freq)
        noise_floor = sig.noise_power_dbm
        
        print(f"{name:<15} {noise_floor:11.1f} | {snr:8.1f}")
