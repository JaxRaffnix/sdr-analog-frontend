from dataclasses import dataclass
import math
import itertools
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pandas as pd
from typing import Callable
import marimo as mo


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
    
    # def run_diagnostics(self, signal):
    #     raise NotImplementedError(f"Model '{self.__class__.__name__}' must implement the run_diagnostics() method.")

    def get_noise_budget(self, noise_floor, analysis_freq, gain=None, reference_noise_floor=None):
        """Propagate noise through a stage using its linear gain and noise figure."""
        if gain is None:
            gain = self.get_gain(analysis_freq)
        if reference_noise_floor is None:
            reference_noise_floor = noise_floor

        gain_linear = _dbm_to_mw(gain)
        noise_factor_excess = _dbm_to_mw(self.get_noise_figure(analysis_freq)) - 1.0
        output_noise_mw = (
            _dbm_to_mw(noise_floor) * gain_linear
            + _dbm_to_mw(reference_noise_floor) * gain_linear * noise_factor_excess
        )
        return _mw_to_dbm(output_noise_mw), analysis_freq

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
        nf_model,
        freq_range: Range|None = None,
        **kwargs
    ):
        super().__init__(name, part_number, **kwargs)
        self.gain_model = gain_model
        self.p1db_model = p1db_model
        self.oip3_model = oip3_model
        self.nf_model = nf_model
        self.freq_range = freq_range

    def get_p1db(self, freq):
        return self.p1db_model(freq) if callable(self.p1db_model) else self.p1db_model
    
    def get_oip3(self, freq):
        return self.oip3_model(freq) if callable(self.oip3_model) else self.oip3_model

    def get_gain(self, freq=None):
        return self.gain_model(freq) if callable(self.gain_model) else self.gain_model

    def get_noise_figure(self, freq=None):
        return self.nf_model(freq) if callable(self.nf_model) else self.nf_model
    
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
        reports = []
        out_signal = SpectrumSignal()

        for f, p in signal.tones.items():
            out_signal.add_tone(f, p + self.get_gain(f))

        dominant_freq = None
        if out_signal.tones:
            dominant_freq = max(out_signal.tones.items(), key=lambda item: item[1])[0]

        oip3 = self.get_oip3(dominant_freq)
        if oip3 is not None:
            self._apply_im3(out_signal, oip3)

        if self.max_input_power_dbm is not None:
            reports.append(DiagnosticResult("Max Output Power", out_signal.total_power_dbm() < self.max_input_power_dbm, f"Output Power {out_signal.total_power_dbm():.1f} dBm < Max Output Power {self.max_input_power_dbm:.1f} dBm"))
        reports.append(DiagnosticResult("Dominant Frequency", dominant_freq is not None, f"Dominant frequency is {(dominant_freq/ 1e6):.1f} MHz"))
        reports.append(DiagnosticResult("Compression", out_signal.total_power_dbm() < self.get_p1db(dominant_freq), f"Output Power {out_signal.total_power_dbm():.1f} dBm < P1dB {self.get_p1db(dominant_freq):.1f} dBm"))
        reports.append(DiagnosticResult("OIP3", out_signal.total_power_dbm() < self.get_oip3(dominant_freq), f"Output Power {out_signal.total_power_dbm():.1f} dBm < OIP3 {self.get_oip3(dominant_freq):.1f} dBm"))
        if self.freq_range is not None and dominant_freq is not None:
            reports.append(DiagnosticResult("Frequency Range", dominant_freq in self.freq_range, f"Dominant frequency {(dominant_freq/ 1e6):.1f} MHz is in range [{self.freq_range.minimum/1e6:.1f}, {self.freq_range.maximum/1e6:.1f}] MHz"))

        return out_signal, reports


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
                
        return out_signal, []
    

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
        nf_model=None,
        **kwargs,
    ):
        super().__init__(name, part_number, **kwargs)
        self.conversion_loss_db = abs(conversion_loss_db)
        self.lo_rf_iso = abs(lo_rf_iso_db)
        self.rf_if_iso = abs(rf_if_iso_db)
        self.lo_if_iso = abs(lo_if_iso_db)
        self.required_lo_power_dbm = required_lo_power_dbm
        self.max_lo_power_dbm = max_lo_power_dbm
        self.nf_model = nf_model if nf_model is not None else self.conversion_loss_db
        self.lo_signal = None
        self.lo_freq = None
        self.mode = "RX"

    # TODO: make RX, TX a explicit list and check aginst it, dont manually rewrite the names as strings

    def get_gain(self, freq=None):
        return -self.conversion_loss_db

    def get_noise_figure(self, freq=None):
        return self.nf_model

    def set_lo_signal(self, signal, lo_freq_hz):
        reports = []
        self.lo_signal = signal
        self.lo_freq = lo_freq_hz

        lo_power = signal.power_at(lo_freq_hz)

        reports.append(DiagnosticResult("LO Min Power", lo_power > self.required_lo_power_dbm, f"LO input power {lo_power:.1f} dBm > {self.required_lo_power_dbm:.1f} dBm"))

        reports.append(DiagnosticResult("LO Max Power", lo_power < self.max_lo_power_dbm, f"LO input power {lo_power:.1f} dBm < {self.max_lo_power_dbm:.1f} dBm"))

        return reports

    def process(self, signal, mode="RX"):
        """
        mode: "RX" (RF to IF downconversion) or "TX" (IF to RF upconversion)
        """
        reports = []
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

        reports.append(DiagnosticResult("Mixer Mode", mode in ["RX", "TX"], f"Mode '{mode}' is in ['RX', 'TX']."))
        reports.append(DiagnosticResult("LO Signal", self.lo_signal is not None, f"LO signal is 'present"))
        reports.append(DiagnosticResult("LO Frequency", self.lo_freq is not None, f"LO desired frequency is set to {self.lo_freq/ 1e6} MHz"))

        lo_power = self.lo_signal.power_at(self.lo_freq)
        reports.append(DiagnosticResult("LO Min Power", lo_power > self.required_lo_power_dbm, f"LO input power {lo_power:.1f} dBm > {self.required_lo_power_dbm:.1f} dBm"))
        reports.append(DiagnosticResult("LO Max Power", lo_power < self.max_lo_power_dbm, f"LO input power {lo_power:.1f} dBm <{self.max_lo_power_dbm:.1f} dBm"))

        return out_signal, reports

    def get_noise_budget(self, noise_floor, analysis_freq, gain=None, reference_noise_floor=None):
        if self.mode.upper() == "RX":
            lo_iso = self.lo_if_iso
            analysis_freq = abs(analysis_freq - self.lo_freq)
        else:
            lo_iso = self.lo_rf_iso
            analysis_freq = abs(analysis_freq + self.lo_freq)

        return super().get_noise_budget(
            noise_floor,
            analysis_freq,
            gain,
            reference_noise_floor,
        )

    
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
        reports = []
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

        reports.append(DiagnosticResult("Limiter Status", self.last_effective_loss <= self.il_db, f"Effective Loss {self.last_effective_loss:.1f} dB <= Insertion Loss {self.il_db:.1f} dB"))
        reports.append(DiagnosticResult("Power Clipping", pin_total < self.threshold_dbm, f"Input Power {pin_total:.1f} dBm < Limiter Threshold {self.threshold_dbm:.1f} dBm."))
        if self.max_input_power_dbm is not None:
            reports.append(DiagnosticResult("Max Output Power", out_signal.total_power_dbm() < self.max_input_power_dbm, f"Output Power {out_signal.total_power_dbm():.1f} dBm < Max Output Power {self.max_input_power_dbm:.1f} dBm"))
            
        return out_signal, reports
    
    def get_noise_budget(self, noise_floor, analysis_freq, gain=None, reference_noise_floor=None):
        return super().get_noise_budget(
            noise_floor,
            analysis_freq,
            gain=-self.last_effective_loss,
            reference_noise_floor=reference_noise_floor,
        )


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
        reports = []
        input_power = signal.total_power_dbm()

        out_signal = SpectrumSignal()

        for freq, power in signal.tones.items():
            if freq > self.sample_rate_hz / 2:
                alias_freq = abs(freq - self.sample_rate_hz * round(freq / self.sample_rate_hz))
                out_signal.add_tone(alias_freq, power)
            else:
                out_signal.add_tone(freq, power)

        self.nyquist_freq = self.sample_rate_hz / 2

        reports.append(DiagnosticResult("ADC Close to Full Scale", input_power <= self.full_scale_dbm -3, f"Input Power {input_power:.1f} dBm <= Full Scale {self.full_scale_dbm:.1f} -3 dBm"))
        reports.append(DiagnosticResult("ADC Full Scale", input_power <= self.full_scale_dbm, f"Input Power {input_power:.1f} dBm <= Full Scale {self.full_scale_dbm:.1f} dBm"))
        reports.append(DiagnosticResult("ADC Bandwidth", all(f <= self.bandwidth_hz for f in signal.tones), f"All tones within bandwidth {self.bandwidth_hz/1e6:.1f} MHz"))
        reports.append(DiagnosticResult("ADC Nyquist", all(f <= self.sample_rate_hz / 2 for f in signal.tones), f"All tones within Nyquist {self.sample_rate_hz/2e6:.1f} MHz"))
        reports.append(DiagnosticResult("Nyquist Frequency", any(f > self.sample_rate_hz / 2 for f in signal.tones), "Frequencies above Nyquist will be aliased to lower frequencies: " + ", ".join(f"{f/1e6:.1f} MHz" for f in signal.tones if f > self.sample_rate_hz / 2)))
        if self.max_input_power_dbm is not None:
            reports.append(DiagnosticResult("Max Output Power", out_signal.total_power_dbm() < self.max_input_power_dbm, f"Output Power {out_signal.total_power_dbm():.1f} dBm < Max Output Power {self.max_input_power_dbm:.1f} dBm"))

        return out_signal, reports
    
    def get_noise_budget(self, noise_floor, analysis_freq, gain=None, reference_noise_floor=None):
        quant_snr_db = 6.02 * self.resolution_bits + 1.76
        quant_noise_dbm = self.full_scale_dbm - quant_snr_db
        
        return _mw_to_dbm(_dbm_to_mw(noise_floor) + _dbm_to_mw(quant_noise_dbm)), analysis_freq
    

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
        self.freq_range: Range|None = freq_range
        self.power_range: Range|None = power_range
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
        reports = []
        signal = SpectrumSignal({self.freq_hz: self.output_power_dbm},)
        if self.harmonics:
            signal = self._apply_harmonics(signal)
        if self.spur_level_dbc is not None:
            signal = self._apply_spurs(signal)

        if hasattr(self, 'fs_hz') and self.fs_hz:
            signal = self._apply_sinc_roll_off(signal, self.fs_hz)
            signal = self._apply_images(signal, self.fs_hz)

        if self.freq_range is not None:
            reports.append(DiagnosticResult("Source Frequency", self.freq_hz in self.freq_range, f"Frequency {self.freq_hz/1e6:.1f} MHz is in range [{self.freq_range.minimum/1e6:.1f}, {self.freq_range.maximum/1e6:.1f}] MHz"))
            reports.append(DiagnosticResult("Source Power", self.output_power_dbm in self.power_range, f"Power {self.output_power_dbm:.1f} dBm is in range [{self.power_range.minimum:.1f}, {self.power_range.maximum:.1f}] dBm" ))

        return signal, reports
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

    def process(self, signal = None):
        reports = []
        return SpectrumSignal(tones=self.signal.tones), reports
    
    def get_noise_budget(self, noise_floor, analysis_freq, gain=None, reference_noise_floor=None):
        return -174.0 + _mw_to_dbm(self.bandwidth_hz), analysis_freq


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
def print_system_report(diagnostics):
    # print("Diagnostics Report:")
    if not diagnostics:
        print("No diagnostics generated.")
        return

    for component_name, reports in diagnostics.items():
        if not reports:
            continue
        print(f"\n{component_name}")
        for report in reports:
            print(f"  {report}")

def diagnostics_to_ui(diagnostics: dict):
    sections = []

    for component_name, reports in diagnostics.items():
        if not reports:
            continue

        # Calculate summary metrics for the header
        total = len(reports)
        failed_count = sum(1 for r in reports if not r.passed)
        status_icon = "❌" if failed_count > 0 else "✅"
        summary = f"{component_name} ({total} tests, {failed_count} failures) {status_icon}"
        
        # Build Table
        rows = []
        for report in reports:
            # Use specific CSS for status to make it pop
            color = "#28a745" if report.passed else "#dc3545"
            status_text = f'<span style="color:{color}; font-weight:bold;">{"Pass" if report.passed else "Fail"}</span>'
            
            rows.append(
                f"| {status_text} | **{report.test_name}** | {report.description} |"
            )
            
        table_md = "\n".join([
            "| Status | Test | Test Condition |",
            "|:---:|:---|:---|",
            *rows,
        ])

        sections.append(
            mo.accordion({summary: mo.md(table_md)})
        )

    return mo.vstack(sections)

# ___________________________________________________________________
# Diagnostics Display

def run_simulation(stages, signal: SpectrumSignal, analysis_freq=None, noise_floor=None):
    noise_floor = THERMAL_NOISE_FLOOR if noise_floor is None else noise_floor
    reference_noise_floor = None

    diagnostics = {}
    results = []
    noise_budges = []
    for stage in stages:

        signal, reports = stage.process(signal)
        results.append({
            "Stage": stage.name,
            "Part Number": stage.part_number,
            "Signal": signal,
            "Total Power [dBm]": signal.total_power_dbm(),
        })

        diagnostics[stage.name] = reports

        if analysis_freq is not None:
            noise_floor, analysis_freq = stage.get_noise_budget(
                noise_floor,
                analysis_freq,
                reference_noise_floor=reference_noise_floor,
            )
            if reference_noise_floor is None:
                reference_noise_floor = noise_floor
            noise_budges.append({
                "Stage": stage.name,
                "Analysis Frequency [GHz]": analysis_freq / 1e9,
                "Tone Power [dBm]": signal.power_at(analysis_freq),
                "Noise Floor [dBm]": noise_floor,
                "SNR [dB]": signal.get_snr(freq=analysis_freq, noise_floor_dbm=noise_floor)
            })

    results_df = pd.DataFrame(results).set_index("Stage")
    noise_budget_df = pd.DataFrame(noise_budges).round(2)
    
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
