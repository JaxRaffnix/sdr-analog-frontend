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
    def __init__(self, tones=None, analysis_freq=None, noise_power_dbm=THERMAL_NOISE_FLOOR):
        self.tones = tones.copy() if tones is not None else {}
        self.analysis_freq = analysis_freq
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

    def get_snr(self, freq_hz: float, default: float = -np.inf) -> float:
        """Returns the SNR in dB for a specific tone."""
        tone_power = self.power_at(freq_hz, default=default)
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
            "Stage": self.name,
            "Part Number": self.part_number,
            "Voltage [V]": rail.voltage,
            "Current typ [A]": rail.current_typ,
            "Current max [A]": rail.current_max,
            "Power typ [W]": round(rail.voltage * rail.current_typ, 6),
            "Power max [W]": round(rail.voltage * rail.current_max, 6),
        }

    def process(self, signal):
        raise NotImplementedError(f"{self.__class__.__name__} must implement the process() method.")

    def gain_db(self, freq_hz=None):
        raise NotImplementedError(f"{self.__class__.__name__} must implement the gain_db() method.")

    def noise_figure_db(self, freq_hz=None):
        raise NotImplementedError(f"{self.__class__.__name__} must implement the noise_figure_db() method.")

    def calc_output_noise(self, input_noise_dbm: float, gain_db: float, noise_figure_db: float) -> float:
        return input_noise_dbm + gain_db + noise_figure_db


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

    def check_compression(self, signal, analysis_freq):
        if signal is None or not signal.tones:
            return

        pout = signal.total_power_dbm()
        p1db = self._get_p1db(analysis_freq)
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

        analysis_freq = signal.analysis_freq 

        nom_gain = self.gain_db(analysis_freq)
        nom_nf = self.noise_figure_db(analysis_freq)
        new_noise = self.calc_output_noise(signal.noise_power_dbm, nom_gain, nom_nf)

        out_signal = SpectrumSignal(noise_power_dbm=new_noise, analysis_freq=analysis_freq)

        for f, p in signal.tones.items():
            out_signal.add_tone(f, p + self._get_gain(f))

        self.check_compression(out_signal, analysis_freq)
        self.check_output_power(out_signal)

        oip3 = self._get_oip3(analysis_freq) if analysis_freq is not None else None
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

        # 2. Look up loss at that exact frequency
        analysis_freq = signal.analysis_freq if signal.analysis_freq is not None else self.center_freq_hz
        if analysis_freq is None:
            raise ValueError(f"{self.name}: analysis frequency is required to process a filter stage")

        loss_at_carrier = self._get_loss(analysis_freq)
        
        # 3. Calculate noise using the loss at the carrier
        new_noise = self.calc_output_noise(
            input_noise_dbm=signal.noise_power_dbm, 
            gain_db=-abs(loss_at_carrier), 
            noise_figure_db=abs(loss_at_carrier)
        )

        out_signal = SpectrumSignal(noise_power_dbm=new_noise, analysis_freq=signal.analysis_freq)
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
        lo_if_iso_db=30.0, 
        required_lo_power_dbm=None,
        max_lo_power_dbm=None,
        noise_figure_db=None,
        **kwargs,
    ):
        super().__init__(name, part_number, **kwargs)
        self.conversion_loss_db = abs(conversion_loss_db)
        self.lo_rf_iso = abs(lo_rf_iso_db)
        self.rf_if_iso = abs(rf_if_iso_db)
        self.lo_if_iso = abs(lo_if_iso_db)
        self.required_lo_power_dbm = required_lo_power_dbm
        self.max_lo_power_dbm = max_lo_power_dbm
        self.nf_db = noise_figure_db if noise_figure_db is not None else self.conversion_loss_db
        self.lo_signal = None
        self.lo_freq = None

    def gain_db(self, freq_hz=None):
        return -self.conversion_loss_db

    def noise_figure_db(self, freq_hz=None):
        return self.nf_db

    def set_lo_signal(self, signal, lo_freq_hz):
        self.lo_signal = signal
        self.lo_freq = lo_freq_hz

        lo_power = signal.power_at(lo_freq_hz)
        if self.required_lo_power_dbm and lo_power < self.required_lo_power_dbm:
            print(f"[{self.name}] LO drive {lo_power:.1f} dBm low (req: {self.required_lo_power_dbm})")
        if self.max_lo_power_dbm and lo_power > self.max_lo_power_dbm:
            print(f"[{self.name}] LO drive {lo_power:.1f} dBm high (max: {self.max_lo_power_dbm})")

    def process(self, signal, mode="RX"):
        """
        mode: "RX" (RF to IF downconversion) or "TX" (IF to RF upconversion)
        """
        self.check_limits(signal)

        if self.lo_signal is None:
            raise ValueError(f"Mixer {self.name} missing LO signal")
            
        mode = mode.upper()
        if mode not in ["RX", "TX"]:
            raise ValueError("Mixer mode must be 'RX' or 'TX'")

        # --- 1. ROUTE ISOLATION & NOISE PHYSICS BASED ON MODE ---
        if mode == "RX":
            # Broadband noise folds down (+3 dB)
            folded_input_noise_mw = 2 * (10 ** (signal.noise_power_dbm / 10))
            effective_input_noise_dbm = 10 * math.log10(folded_input_noise_mw)
            
            lo_leakage_iso = self.lo_if_iso
            signal_leakage_iso = self.rf_if_iso 

            analysis_freq = abs(signal.analysis_freq - self.lo_freq)
        else:
            # TX: IF upconverts, no foldover accumulation
            effective_input_noise_dbm = signal.noise_power_dbm
            
            lo_leakage_iso = self.lo_rf_iso
            signal_leakage_iso = self.rf_if_iso # IF-to-RF isolation is symmetric to RF-to-IF

            analysis_freq = abs(signal.analysis_freq + self.lo_freq)
            
        # Calculate signal noise transfer + internal mixer thermal noise
        converted_noise_dbm = self.calc_output_noise(
            effective_input_noise_dbm, 
            gain_db=self.gain_db(), 
            noise_figure_db=self.noise_figure_db()
        )

        # --- 2. LO NOISE LEAKAGE ---
        lo_to_output_noise_dbm = self.lo_signal.noise_power_dbm - lo_leakage_iso

        # Sum the noise powers linearly (in mW)
        total_noise_mw = (10 ** (converted_noise_dbm / 10)) + (10 ** (lo_to_output_noise_dbm / 10))
        total_noise_dbm = 10 * math.log10(total_noise_mw)

        out_signal = SpectrumSignal(noise_power_dbm=total_noise_dbm, analysis_freq=analysis_freq)
        
        # --- 3. SIGNAL TONE CONVERSION & LEAKAGE ---
        
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

    def gain_db(self, freq_hz=None):
        # Small-signal gain is simply the negative insertion loss
        return -self.il_db

    def noise_figure_db(self, freq_hz=None):
        # For passive components, NF equals insertion loss
        return self.il_db

    def process(self, signal):
        self.check_limits(signal)

        # 1. Determine total input power
        pin_total = signal.total_power_dbm()
        
        # 2. Calculate ideal linear output power
        pout_linear = pin_total - self.il_db
        
        # 3. Apply limiting logic
        if pout_linear <= self.threshold_dbm:
            pout_actual = pout_linear
            effective_loss_db = self.il_db
        else:
            # Clamp the output power to the flat leakage spec
            pout_actual = min(pout_linear, self.flat_leakage_dbm)
            effective_loss_db = pin_total - pout_actual
            print(f"[{self.name}] LIMITING ACTIVE: Pin={pin_total:.1f} dBm, Pout clamped to {pout_actual:.1f} dBm (Eff. Loss: {effective_loss_db:.1f} dB)")

        # 4. Calculate noise (using dynamic effective loss)
        new_noise = self.calc_output_noise(
            input_noise_dbm=signal.noise_power_dbm, 
            gain_db=-effective_loss_db, 
            noise_figure_db=self.il_db
        )

        out_signal = SpectrumSignal(
            noise_power_dbm=new_noise,
            analysis_freq=signal.analysis_freq,
        )
        
        # 5. Apply the effective loss to all incoming tones
        for freq, power in signal.tones.items():
            out_signal.add_tone(freq, power - effective_loss_db)
            
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
        out_signal = SpectrumSignal(
            noise_power_dbm=total_noise_dbm,
            analysis_freq=signal.analysis_freq,
        )

        for freq, power in signal.tones.items():
            if freq > self.sample_rate_hz / 2:
                alias_freq = abs(freq - self.sample_rate_hz * round(freq / self.sample_rate_hz))
                out_signal.add_tone(alias_freq, power)
            else:
                out_signal.add_tone(freq, power)

        self.nyquist_freq = self.sample_rate_hz / 2

        pout = out_signal.total_power_dbm()
        if pout > self.full_scale_dbm:
            print(f"[{self.name}] Clipping! {pout:.1f} dBm > FS {self.full_scale_dbm} dBm")
        elif pout > self.full_scale_dbm - 3:
            print(f"[{self.name}] Low Headroom: {self.full_scale_dbm - pout:.1f} dB")
        for freq in signal.tones:
            if freq > self.bandwidth_hz:
                print(f"[{self.name}] Warning: Frequency exceeds ADC bandwidth: {freq / 1e6:.1f} MHz > {self.bandwidth_hz / 1e6:.1f} MHz")
            if freq > self.nyquist_freq:
                    print(f"Signal at {freq / 1e6:.1f} MHz is above Nyquist frequency {self.nyquist_freq / 1e6:.1f} MHz and discarded")

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
            minimum_mhz = "-inf" if self.freq_range.minimum is None else f"{self.freq_range.minimum / 1e6:.1f}"
            maximum_mhz = "inf" if self.freq_range.maximum is None else f"{self.freq_range.maximum / 1e6:.1f}"
            print(
                f"Frequency {self.freq_hz / 1e6:.1f} MHz outside "
                f"range {minimum_mhz}-"
                f"{maximum_mhz} MHz"
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
        return SpectrumSignal(
            tones,
            analysis_freq=signal.analysis_freq,
            noise_power_dbm=signal.noise_power_dbm,
        )


    def _apply_images(self, signal: SpectrumSignal, fs_hz: float) -> SpectrumSignal:
        # 1. Initialize the new output signal with the incoming tones and noise floor
        out_signal = SpectrumSignal(
            tones=signal.tones, 
            noise_power_dbm=signal.noise_power_dbm,
            analysis_freq=signal.analysis_freq,
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
            analysis_freq=signal.analysis_freq,
            noise_power_dbm=signal.noise_power_dbm,
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

        return SpectrumSignal(
            tones,
            analysis_freq=signal.analysis_freq,
            noise_power_dbm=signal.noise_power_dbm,
        )

    def process(self, signal=None):
        self.check_limits(signal)
        self.check_range()

        signal = SpectrumSignal(
            {self.freq_hz: self.output_power_dbm},
            analysis_freq=self.freq_hz,
        )
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
            analysis_freq: float,
            **kwargs,
        ):
        super().__init__(name, part_number, **kwargs)
        self.bandwidth_hz = bandwidth_hz
        self.signal = SpectrumSignal(analysis_freq=analysis_freq)

    def add_signal(self, freq_hz: float, power_dbm: float):
        self.signal.add_tone(freq_hz, power_dbm)
        return self

    def process(self, signal = None) -> SpectrumSignal:
        # add thermal noise
        noise_floor_dbm = -174.0 + 10 * math.log10(self.bandwidth_hz)
        self.signal.noise_power_dbm = noise_floor_dbm
        
        return SpectrumSignal(
            tones=self.signal.tones, 
            noise_power_dbm=self.signal.noise_power_dbm,
            analysis_freq=self.signal.analysis_freq
        )

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
def run_simulation(stages, signal: SpectrumSignal) -> pd.DataFrame:
    results = []
    for stage in stages:
        signal = stage.process(signal)

        def get_power_safely(sig, freq):
            try:
                return sig.power_at(freq)
            except ValueError:
                return pd.NA
            
        f_a = signal.analysis_freq

        results.append({
            "Stage": stage.name,
            "Part Number": stage.part_number,
            "Signal": signal,
            "Total Power [dBm]": signal.total_power_dbm(),
            "Analysis Frequency [GHz]": f_a / 1e9 if f_a else pd.NA,
            "Noise Floor [dBm]": signal.noise_power_dbm,
            "Tone Power [dBm]": signal.power_at(f_a, default=pd.NA),
            "SNR [dB]": signal.get_snr(f_a, default=pd.NA)
        })
    
    return pd.DataFrame(results).set_index("Stage")


# ___________________________________________________________________
# table formatting
PLOT_POWER_MIN = -130
PLOT_POWER_MAX = 30


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
        .background_gradient(cmap="viridis", axis=None, vmin=PLOT_POWER_MIN, vmax=PLOT_POWER_MAX)
        .format("{:.2f}", na_rep="")              
        .format_index("{:.3f}", axis=0) 
    )
    

# ___________________________________________________________________
# plotting
def plot_spectrum(results: pd.DataFrame, stage: str):
    tones = results.loc[stage, "Signal"].tones
    
    freqs = [x for f in tones.keys() for x in (f / 1e9, f / 1e9, None)]
    powers = [x for p in tones.values() for x in (PLOT_POWER_MIN, p, None)]

    fig = go.Figure(
        data=go.Scatter(
            x=freqs, y=powers, 
            mode='lines',
        )
    )
    
    fig.update_layout(
        title=dict(text=f"Spectrum at Stage: {stage}", x=0.5),
        xaxis=dict(title="Frequency [GHz]", showgrid=True),
        yaxis=dict(title="Power [dBm]", range=[PLOT_POWER_MIN, PLOT_POWER_MAX], showgrid=True)
    )

    return fig


# ___________________________________________________________________
# Noise Budget Calculation
def build_noise_budget(results: pd.DataFrame, analysis_freq):
    df = results.copy()
    
    df["Stage NF [dB]"] = df["SNR [dB]"].shift(1) - df["SNR [dB]"]
    
    df["Cumulative NF [dB]"] = df["SNR [dB]"].iloc[0] - df["SNR [dB]"]
        
    df = df[["Analysis Frequency [GHz]", "Tone Power [dBm]", "Noise Floor [dBm]", "SNR [dB]", "Stage NF [dB]", "Cumulative NF [dB]"]]
    
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
