from dataclasses import dataclass, field
import math
import itertools
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from typing import Callable


# ___________________________________________________________________
# Constants
THERMAL_NOISE_FLOOR = -174.0  # dBm/Hz at room temperature


# ___________________________________________________________________
# Signal
class SpectrumSignal:
    def __init__(self, tones=None):
        self.tones = tones.copy() if tones is not None else {}

    def total_power_dbm(self):
        if not self.tones: 
            return -math.inf
        powers_mw = _dbm_to_mw(np.array(list(self.tones.values())))
        return _mw_to_dbm(np.sum(powers_mw)) 
    
    def add_tone(self, freq, power_dbm):
        """Adds freq+power information to the signal. If the tone already exists, the powers are added."""
        if freq in self.tones:
            self.tones[freq] = _mw_to_dbm(_dbm_to_mw(self.tones[freq]) + _dbm_to_mw(power_dbm))
        else:
            self.tones[freq] = power_dbm

    def power_at(self, frequency, default=-np.inf):
        power = self.tones.get(frequency, default)
        if power == -np.inf:
            raise ValueError(f"Frequency {frequency} Hz not found in signal tones.")
        return power

    def get_snr(self, freq: float, default_power = -np.inf, noise_floor_dbm: float = THERMAL_NOISE_FLOOR) -> float:
        """Returns the SNR in dB for a specific tone."""
        tone_power = self.power_at(freq, default=default_power)
        return float(tone_power) - float(noise_floor_dbm)


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


@dataclass
class DiagnosticResult:
    test_name: str
    passed: bool
    description: str

    def __str__(self):
        status = "✅" if self.passed else "❌"
        return f"{status} {self.test_name}: {self.description}"


class PowerRail:
    def __init__(self, voltage, current_typ, current_max=None):
        self.voltage = voltage
        self.current_typ = current_typ
        self.current_max = current_max if current_max else current_typ


# ___________________________________________________________________
# Helper Functions
def _dbm_to_mw(dbm):
    return 10 ** (dbm / 10)

def _mw_to_dbm(mw):
    return 10 * np.log10(mw)


# ___________________________________________________________________
# Core Components
class RFComponent:
    def __init__(
            self, 
            name, 
            part_number, 
            max_input_power_dbm=None, 
            power_rail=None
        ):
        self.name = name           
        self.part_number = part_number 
        self.power_rail = power_rail
        self.max_input_power_dbm = max_input_power_dbm

    def __repr__(self):
        return f"{self.name} ({self.part_number})"
    
    def run_diagnostics(self, signal):
        raise NotImplementedError(f"Model '{self.__class__.__name__}' must implement the run_diagnostics() method.")

    def get_noise_budget(self, noise_floor, analysis_freq, gain=None):
        """Calculates the noise budget at a given analysis frequency and the current noise floor. Returns the updated noise floor and the analysis frequency."""
        if gain is None:
            gain = self.get_gain(analysis_freq)
        nf = self.get_noise_figure(analysis_freq)
        return noise_floor + gain + nf, analysis_freq

    def dc_power_report(self):
        if self.power_rail is None:
            return None

        return {
            "Stage": self.name,
            "Part Number": self.part_number,
            "Voltage [V]": self.power_rail.voltage,
            "Current typ [A]": self.power_rail.current_typ,
            "Current max [A]": self.power_rail.current_max,
            "Power typ [W]": round(self.power_rail.voltage * self.power_rail.current_typ, 3),
            "Power max [W]": round(self.power_rail.voltage * self.power_rail.current_max, 3),
        }
    
    def process(self, signal):
        raise NotImplementedError(f"Model '{self.__class__.__name__}' must implement the process() method.")

    def get_gain(self, freq=None):
        raise NotImplementedError(f"Model '{self.__class__.__name__}' must implement the get_gain() method.")

    def get_noise_figure(self, freq=None):
        raise NotImplementedError(f"Model '{self.__class__.__name__}' must implement the get_noise_figure() method.")


class Amplifier(RFComponent):
    def __init__(
        self, 
        name, 
        part_number, 
        gain_model, 
        p1db_model,
        oip3_model,
        nf_db=None,
        max_output_power_dbm=None,
        **kwargs
    ):
        super().__init__(name, part_number, **kwargs)
        self.gain_model = gain_model
        self.p1db_model = p1db_model
        self.oip3_model = oip3_model
        self.nf_db = nf_db
        self.max_output_power_dbm = max_output_power_dbm

    def get_p1db(self, freq):
        return self.p1db_model.get_p1db(freq) if hasattr(self.p1db_model, "get_p1db") else self.p1db_model
    
    def get_oip3(self, freq):
        return self.oip3_model.get_oip3(freq) if hasattr(self.oip3_model, "get_oip3") else self.oip3_model

    def get_gain(self, freq=None):
        return self.gain_model.get_gain(freq) if hasattr(self.gain_model, "get_gain") else self.gain_model

    def get_noise_figure(self, freq=None):
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

    def process(self, signal: SpectrumSignal):
        out_signal = SpectrumSignal()

        for f, p in signal.tones.items():
            out_signal.add_tone(f, p + self.get_gain(f))

        dominant_freq = None
        if out_signal.tones:
            dominant_freq = max(out_signal.tones.items(), key=lambda item: item[1])[0]
        print(f"{self.name}: Amplifier dominant frequency is: {dominant_freq:.1f} Hz")

        oip3 = self.get_oip3(dominant_freq)
        if oip3 is not None:
            self._apply_im3(out_signal, oip3)

        return out_signal
    
    def run_diagnostics(self, signal):
        reports = []
        pout = signal.total_power_dbm() + self.get_gain() # Pout after gain
        
        p1db = self.get_p1db(None) # Use None or a dominant frequency
        if p1db is not None:
            passed = pout < p1db
            self.add_diagnostic("Compression", passed, f"Pout {pout:.1f} dBm < P1dB {p1db:.1f} dBm")
            
        if self.max_output_power_dbm is not None:
            passed = pout <= self.max_output_power_dbm
            self.add_diagnostic("Max Power", passed, f"Pout {pout:.1f} dBm <= Max Output Power {self.max_output_power_dbm:.1f} dBm")
            
        return reports


class Filter(RFComponent):
    def __init__(
        self, 
        name, 
        part_number, 
        insertion_loss: int | float | Callable[[float], float],
        freq_range: Range|None = None,
        rejection_db: float = 100.0, 
        center_freq_hz=None,
        **kwargs
    ):
        super().__init__(name, part_number, **kwargs)
        self.insertion_loss = insertion_loss        
        self.freq_range = freq_range
        self.rejection_db = abs(rejection_db) if rejection_db else None
        self.center_freq_hz = center_freq_hz

    def _get_loss(self, freq: float) -> float:
        if self.freq_range and freq not in self.freq_range:
            return float(self.rejection_db) if self.rejection_db is not None else 0.0
            
        if isinstance(self.insertion_loss, (int, float)):
            return float(self.insertion_loss)
        return self.insertion_loss(freq)

    def get_gain(self, freq=None):
        if freq is None:
            raise ValueError(f"{self.name}: frequency is required to evaluate filter gain")
        return -abs(self._get_loss(freq))

    def get_noise_figure(self, freq=None):
        if freq is None:
            raise ValueError(f"{self.name}: frequency is required to evaluate filter noise figure")
        return abs(self._get_loss(freq))

    def process(self, signal: SpectrumSignal):
        out_signal = SpectrumSignal()
        for freq, power in signal.tones.items():
            loss = self._get_loss(freq)
            out_signal.add_tone(freq, power - abs(loss))
                
        return out_signal
    
    def run_diagnostics(self, signal):
        reports = []
        return reports
    

class Mixer(RFComponent):
    def __init__(
        self,
        name,
        part_number,
        conversion_loss_db,
        lo_rf_iso_db,
        rf_if_iso_db,
        lo_if_iso_db=30.0, 
        required_lo_power_dbm=None,
        max_lo_power_dbm=None,
        nf_db=None,
        **kwargs,
    ):
        super().__init__(name, part_number, **kwargs)
        self.conversion_loss_db = abs(conversion_loss_db)
        self.lo_rf_iso = abs(lo_rf_iso_db)
        self.rf_if_iso = abs(rf_if_iso_db)
        self.lo_if_iso = abs(lo_if_iso_db)
        self.required_lo_power_dbm = required_lo_power_dbm
        self.max_lo_power_dbm = max_lo_power_dbm
        self.nf_db = nf_db if nf_db is not None else self.conversion_loss_db
        self.lo_signal = None
        self.lo_freq = None
        self.mode = "Rx"

    def get_gain(self, freq=None):
        return -self.conversion_loss_db

    def get_noise_figure(self, freq=None):
        return self.nf_db

    def set_lo_signal(self, signal, lo_freq_hz):
        self.lo_signal = signal
        self.lo_freq = lo_freq_hz

        lo_power = signal.power_at(lo_freq_hz)
        if self.required_lo_power_dbm and lo_power < self.required_lo_power_dbm:
            print(f"❌ {self.name}: LO input power {lo_power:.1f} dBm > {self.required_lo_power_dbm:.1f} dBm")
        if self.max_lo_power_dbm and lo_power > self.max_lo_power_dbm:
            print(f"❌ {self.name}: LO input power {lo_power:.1f} dBm < {self.max_lo_power_dbm:.1f} dBm")

    def process(self, signal, mode="Rx"):
        """
        mode: "RX" (RF to IF downconversion) or "TX" (IF to RF upconversion)
        """
        # --- 1. ROUTE ISOLATION & NOISE PHYSICS BASED ON MODE ---
        if mode == "RX":
            lo_leakage_iso = self.lo_if_iso
            signal_leakage_iso = self.rf_if_iso 
        else:
            lo_leakage_iso = self.lo_rf_iso
            signal_leakage_iso = self.rf_if_iso # IF-to-RF isolation is symmetric to RF-to-IF

        out_signal = SpectrumSignal()        
        # LO Leakage to output port
        for f, p in self.lo_signal.tones.items():
            out_signal.add_tone(f, p - lo_leakage_iso)

        # Input Signal Leakage & Conversion
        for f, p in signal.tones.items():
            # Input leaking straight through to output
            out_signal.add_tone(f, p - signal_leakage_iso)
            
            # Desired mixing products (f_In + f_LO) and |f_In - f_LO|
            conv_p = p - self.conversion_loss_db
            out_signal.add_tone(abs(f + self.lo_freq), conv_p)
            out_signal.add_tone(abs(f - self.lo_freq), conv_p)

        return out_signal

    def get_noise_budget(self, noise_floor, analysis_freq, gain=None):
        input_noise_mw = _dbm_to_mw(noise_floor)

        if self.mode.upper() == "RX":
            input_noise_mw *= 2  # Folded noise (+3 dB)
            lo_iso = self.lo_if_iso
            analysis_freq = abs(analysis_freq - self.lo_freq)
        else:
            lo_iso = self.lo_rf_iso
            analysis_freq = abs(analysis_freq + self.lo_freq)

        if self.lo_signal and hasattr(self.lo_signal, "noise_power_dbm"):
            lo_noise_mw = _dbm_to_mw(self.lo_signal.noise_power_dbm - lo_iso)
            input_noise_mw += lo_noise_mw

        return super().get_noise_budget(_mw_to_dbm(input_noise_mw), analysis_freq, gain)
    
    def run_diagnostics(self, signal):
        reports = []
        if self.lo_signal:
            lo_power = self.lo_signal.power_at(self.lo_freq)
            
            # Check LO Requirements
            if self.required_lo_power_dbm is not None:
                passed = lo_power >= self.required_lo_power_dbm
                self.add_diagnostic("LO Drive", passed, f"{lo_power:.1f} dBm >= {self.required_lo_power_dbm:.1f} dBm")
            
            # Check LO Max
            if self.max_lo_power_dbm is not None:
                passed = lo_power <= self.max_lo_power_dbm
                self.add_diagnostic("LO Max Power", passed, f"{lo_power:.1f} dBm <= {self.max_lo_power_dbm:.1f} dBm")

            if self.lo_signal is None:
                self.add_diagnostic("LO Signal", False, "No LO signal available")

            if self.mode.upper() not in ["RX", "TX"]:
                self.add_diagnostic("Mixer Mode", False, f"Invalid mode: {self.mode}. Expected 'RX' or 'TX'.")

        return reports

    
class Limiter(RFComponent):
    def __init__(
        self, 
        name, 
        part_number, 
        insertion_loss_db: float,
        limiting_threshold_dbm: float,
        flat_leakage_dbm: float,
        freq_range=None,
        **kwargs
    ):
        super().__init__(name, part_number, **kwargs)
        self.il_db = insertion_loss_db
        self.threshold_dbm = limiting_threshold_dbm
        self.flat_leakage_dbm = flat_leakage_dbm
        self.freq_range = freq_range
        self.last_effective_loss = insertion_loss_db

    def get_gain(self, freq=None):
        # Small-signal gain is simply the negative insertion loss
        return -self.il_db

    def get_noise_figure(self, freq=None):
        # For passive components, NF equals insertion loss
        return self.il_db

    def process(self, signal):
        pin_total = signal.total_power_dbm()        
        pout_linear = pin_total - self.il_db
        
        # 3. Apply limiting logic
        if pout_linear <= self.threshold_dbm:
            self.last_effective_loss = self.il_db
        else:
            pout_actual = min(pout_linear, self.flat_leakage_dbm)
            self.last_effective_loss = pin_total - pout_actual
        out_signal = SpectrumSignal()
        
        # 5. Apply the effective loss to all incoming tones
        for freq, power in signal.tones.items():
            out_signal.add_tone(freq, power - self.last_effective_loss)
            
        return out_signal
    
    def get_noise_budget(self, noise_floor, analysis_freq, gain=None):
        nf = self.get_noise_figure(analysis_freq)
        return noise_floor - self.last_effective_loss + nf, analysis_freq
    
    def run_diagnostics(self, signal):
        reports = []
        pin = signal.total_power_dbm()
        # Active if actual loss is greater than insertion loss
        is_limiting = self.last_effective_loss > self.il_db
        
        self.add_diagnostic("Limiter Status", not is_limiting, f"{self.last_effective_loss} < {self.il_db} dB (Insertion Loss)")
        return reports

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

        out_signal = SpectrumSignal()

        for freq, power in signal.tones.items():
            if freq > self.sample_rate_hz / 2:
                alias_freq = abs(freq - self.sample_rate_hz * round(freq / self.sample_rate_hz))
                out_signal.add_tone(alias_freq, power)
            else:
                out_signal.add_tone(freq, power)

        self.nyquist_freq = self.sample_rate_hz / 2

        return out_signal
    
    def get_noise_budget(self, noise_floor, analysis_freq, gain=None):
        quant_snr_db = 6.02 * self.resolution_bits + 1.76
        quant_noise_dbm = self.full_scale_dbm - quant_snr_db
        
        return _mw_to_dbm(_dbm_to_mw(noise_floor) + _dbm_to_mw(quant_noise_dbm)), analysis_freq
    
    def run_diagnostics(self, signal):
        reports = []
        p_in = signal.total_power_dbm()
        
        # 1. Full Scale / Clipping Check
        headroom = self.full_scale_dbm - p_in
        passed = headroom > 0
        self.add_diagnostic("ADC Full Scale", passed, f"{p_in:.1f} dBm <= Full Scale {self.full_scale_dbm:.1f} dBm")

        # 2. Bandwidth/Nyquist Check
        for freq in signal.tones:
            # Check bandwidth
            bw_ok = freq <= self.bandwidth_hz
            self.add_diagnostic("ADC Bandwidth", bw_ok, f"{freq/1e6:.1f} MHz <= Bandwidth {self.bandwidth_hz/1e6:.1f} MHz")
            
            # Check Nyquist
            nyq_ok = freq <= (self.sample_rate_hz / 2)
            self.add_diagnostic("ADC Nyquist", nyq_ok, f"{freq/1e6:.1f} MHz <= Nyquist {self.sample_rate_hz/2e6:.1f} MHz")
            
        return reports

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

    def get_gain(self, freq=None):
        return 0.0
    
    def get_noise_figure(self, freq=None):
        return 0.0

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
        out_signal = SpectrumSignal(tones=signal.tones)
        
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
        out_signal = SpectrumSignal(tones=signal.tones)        
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
        signal = SpectrumSignal({self.freq_hz: self.output_power_dbm},)
        if self.harmonics:
            signal = self._apply_harmonics(signal)
        if self.spur_level_dbc is not None:
            signal = self._apply_spurs(signal)

        if hasattr(self, 'fs_hz') and self.fs_hz:
            signal = self._apply_sinc_roll_off(signal, self.fs_hz)
            signal = self._apply_images(signal, self.fs_hz)

        return signal
    
    def run_diagnostics(self, signal):
        reports = []
        
        if self.freq_range is not None:
            passed = self.freq_hz in self.freq_range
            min_v = self.freq_range.minimum / 1e6 if self.freq_range.minimum else 0
            max_v = self.freq_range.maximum / 1e6 if self.freq_range.maximum else float('inf')
            self.add_diagnostic("Freq Range", passed, f"{self.freq_hz/1e6:.1f} MHz is in range [{min_v:.1f}, {max_v:.1f}] MHz")

        if self.power_range is not None:
            passed = self.output_power_dbm in self.power_range
            self.add_diagnostic("Power Range", passed, f"{self.output_power_dbm:.1f} dBm is in range [{self.power_range.minimum:.1f}, {self.power_range.maximum:.1f}] dBm")

        return reports
    

class AntennaSource(RFComponent):
    def __init__(
            self, 
            name: str, 
            part_number: str, 
            bandwidth_hz: float,
            analysis_freq: float,
            **kwargs,
        ):
        super().__init__(name, part_number, **kwargs)
        self.bandwidth_hz = bandwidth_hz
        self.signal = SpectrumSignal()

    def add_signal(self, freq_hz: float, power_dbm: float):
        self.signal.add_tone(freq_hz, power_dbm)
        return self

    def process(self, signal = None) -> SpectrumSignal:
        return SpectrumSignal(tones=self.signal.tones)
    
    def get_noise_budget(self, noise_floor, analysis_freq, gain=None):
        return -174.0 + _mw_to_dbm(self.bandwidth_hz), analysis_freq
    
    def run_diagnostics(self, signal):
        reports = []
        passed = len(self.signal.tones) > 0
        self.add_diagnostic("Signal Input", passed, f"Number of tones: {len(self.signal.tones)}")
        return reports


# ___________________________________________________________________
# DC Power Calculation
def calculate_dc_power(stages):
    reports = [s.dc_power_report() for s in stages if s.dc_power_report() is not None]
    df = pd.DataFrame(reports).set_index("Voltage [V]").sort_index().round(3)

    df["Current typ [mA]"] = df["Current typ [A]"] * 1e3
    df["Current max [mA]"] = df["Current max [A]"] * 1e3
    df = df.drop(columns=["Current typ [A]", "Current max [A]"])

    total_df = df.groupby("Voltage [V]").sum().drop(["Stage", "Part Number"], axis=1).round(3)

    return df, total_df


# ___________________________________________________________________
# Run Simulation Function
def print_system_report(components):
    print("--- RF System Diagnostic Report ---")
    for comp in components:
        diags = comp.get_diagnostics()
        if not diags:
            continue
        print(f"\nComponent: {comp.name}")
        for d in diags:
            print(f"  {d}")

def run_simulation(stages, signal: SpectrumSignal, analysis_freq=None, noise_floor=None):
    noise_floor = THERMAL_NOISE_FLOOR or noise_floor

    diagnostics = []
    results = []
    noise_budges = []
    for stage in stages:

        diagnostics.extend(stage.run_diagnostics(signal))

        signal = stage.process(signal)
        results.append({
            "Stage": stage.name,
            "Part Number": stage.part_number,
            "Signal": signal,
            "Total Power [dBm]": signal.total_power_dbm(),
        })

        if analysis_freq is not None:
            noise_floor, analysis_freq = stage.get_noise_budget(noise_floor, analysis_freq)
            noise_budges.append({
                "Stage": stage.name,
                "Analysis Frequency [GHz]": analysis_freq / 1e9,
                "Tone Power [dBm]": signal.power_at(analysis_freq),
                "Noise Floor [dBm]": noise_floor,
                "SNR [dB]": signal.get_snr(freq=analysis_freq, noise_floor_dbm=noise_floor)
            })

    results_df = pd.DataFrame(results).set_index("Stage")
    noise_budget_df = pd.DataFrame(noise_budges).round(2)

    print_system_report(diagnostics)
    
    return results_df, diagnostics, noise_budget_df
    

# ___________________________________________________________________
# frequency analysis
PLOT_POWER_MIN_DB = -130
PLOT_POWER_MAX_DB = 30


def show_frequency_matrix(results: pd.DataFrame):
    MIN_FREQUENCY = 100_000
    
    tones_df = pd.DataFrame(results["Signal"].apply(lambda s: s.tones).tolist(), index=results.index)
    
    matrix = tones_df.T
    matrix = matrix[matrix.index > MIN_FREQUENCY].sort_index()

    matrix.index = matrix.index / 1e9

    matrix = matrix.rename_axis("Frequency [GHz]")
    matrix.columns.name = "Stage Power [dB]"

    return (
        matrix.style
        .background_gradient(cmap="viridis", axis=None, vmin=PLOT_POWER_MIN_DB, vmax=PLOT_POWER_MAX_DB)
        .format("{:.2f}", na_rep="")              
        .format_index("{:.3f}", axis=0) 
    )


def plot_spectrum(results: pd.DataFrame, stage: str):
    tones = results.loc[stage, "Signal"].tones
    
    freqs = [x for f in tones.keys() for x in (f / 1e9, f / 1e9, None)]
    powers = [x for p in tones.values() for x in (PLOT_POWER_MIN_DB, p, None)]

    fig = go.Figure(
        data=go.Scatter(
            x=freqs, y=powers, 
            mode='lines',
        )
    )
    
    fig.update_layout(
        title=dict(text=f"Spectrum at Stage: {stage}", x=0.5),
        xaxis=dict(title="Frequency [GHz]", showgrid=True),
        yaxis=dict(title="Power [dBm]", range=[PLOT_POWER_MIN_DB, PLOT_POWER_MAX_DB], showgrid=True)
    )

    return fig


# ___________________________________________________________________
# Noise Budget Calculation
def build_noise_budget(results: pd.DataFrame, analysis_freq):
    df = results.copy().set_index("Stage")
    
    df["Stage NF [dB]"] = df["SNR [dB]"].shift(1) - df["SNR [dB]"]
    df["Cumulative NF [dB]"] = df["SNR [dB]"].iloc[0] - df["SNR [dB]"]
            
    return df.style.format("{:.2f}", na_rep="")


def plot_noise_budget(df: pd.DataFrame):
    plot_df = df.reset_index()
    
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=plot_df["Stage"], y=plot_df["SNR [dB]"],
        mode='lines+markers',
        name='SNR',
    ))

    fig.add_trace(go.Bar(
        x=plot_df["Stage"], y=plot_df["Stage NF [dB]"],
        name='Stage NF',
    ))

    fig.update_layout(
        title="SNR Degradation Budget",
        xaxis_title="Stage",
        yaxis_title="dB",
    )

    return fig
