from dataclasses import dataclass
import math
import itertools
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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


def calculate_snr(signal: SpectrumSignal, target_freq):
        if target_freq not in signal.tones:
            raise ValueError(f"Target frequency {target_freq} Hz not found in signal tones.")
            
        signal_power = signal.tones[target_freq]
        return signal_power - signal.noise_power_dbm
    

class SpectrumSignal:
    ZERO_POWER = -999.0  # dBm, represents no signal
    DEFAULT_NOISE_FLOOR = -174.0  # dBm/Hz, thermal noise floor
    def __init__(self, tones=None, noise_power_dbm=DEFAULT_NOISE_FLOOR):
        self.tones = tones or {}
        self.noise_power_dbm = noise_power_dbm

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




# ___________________________________________________________________
# Core Components
class PowerRail:
    def __init__(self, voltage, current_typ_a, current_max_a):
        self.voltage = voltage
        self.current_typ_a = current_typ_a
        self.current_max_a = current_max_a


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
            "current_typ_a": rail.current_typ_a,
            "current_max_a": rail.current_max_a,
            "power_typ_w": round(rail.voltage * rail.current_typ_a, 6),
            "power_max_w": round(rail.voltage * rail.current_max_a, 6),
        }

    def process(self, signal):
        raise NotImplementedError(f"{self.__class__.__name__} must implement the process() method.")

    def gain_db(self, freq_hz=None):
        return 0.0

    def noise_figure_db(self, freq_hz=None):
        return 0.0


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
        super().__init__(name, part_number,  **kwargs)
        self.gain_model = gain_model
        self.p1db_dbm = p1db_dbm
        self.oip3_dbm = oip3_dbm
        self.noise_figure_db_value = noise_figure_db
        self.max_output_power_dbm = max_output_power_dbm

    def _get_gain(self, freq):
        return self.gain_model.get_gain(freq) if hasattr(self.gain_model, "get_gain") else self.gain_model
    def _get_p1db(self, freq):
        return self.gain_model.get_p1db(freq) if hasattr(self.gain_model, "get_p1db") else self.p1db_dbm
    def _get_oip3(self, freq):
        return self.gain_model.get_oip3(freq) if hasattr(self.gain_model, "get_oip3") else self.oip3_dbm

    def gain_db(self, freq_hz=None):
        if freq_hz is None:
            freq_hz = 0.0
        return self._get_gain(freq_hz)

    def noise_figure_db(self, freq_hz=None):
        return self.noise_figure_db_value if self.noise_figure_db_value is not None else 0.0
    
    def _apply_im3(self, signal, oip3_dbm, threshold_dbm=-60):
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

    def check_compression(self, signal):
        if signal is None or not signal.tones:
            return

        center_f = signal.center_frequency()
        if center_f is None:
            return

        pout = signal.total_power_dbm()
        p1db = self._get_p1db(center_f)
        if p1db is None:
            return

        if pout >= p1db:
            print(
                f"CRITICAL: {self.name} saturated "
                f"(Pout={pout:.1f} dBm, P1dB={p1db:.1f} dBm)"
            )
        headroom = p1db - pout
        if headroom < 1.0:
            print(f"Compression! Pout is {headroom:.1f} dB from P1dB. Expect high distortion.")

    def check_output_power(self, signal):
        if self.max_output_power_dbm is None or signal is None or not signal.tones:
            return

        pout = signal.total_power_dbm()
        if pout > self.max_output_power_dbm:
            print(f"{self.name} output exceeds limit: {pout:.1f} dBm > {self.max_output_power_dbm:.1f} dBm")

    def process(self, signal: SpectrumSignal):
        self.check_limits(signal)
        
        # 1. Apply Gain
        out_tones = {}
        for f, p in signal.tones.items():
            gain = self._get_gain(f)
            out_tones[f] = p + gain

        amplified = SpectrumSignal(out_tones)
        model_freq = amplified.center_frequency()
        oip3 = self._get_oip3(model_freq) if model_freq is not None else None

        # 2. Compression Check
        self.check_compression(amplified)
        self.check_output_power(amplified)
            
        # 3. Apply Non-Linearity (IM3)
        if oip3 is not None:
            final_tones = self._apply_im3(amplified, oip3)
        else:
            final_tones = amplified.tones
        
        return SpectrumSignal(final_tones)


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

    def _get_loss(self, freq):
        if isinstance(self.insertion_loss, (int, float)):
            return self.insertion_loss
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
        noise_figure_db=None,
        max_rf_input_power_dbm=None,
        max_if_output_power_dbm=None,
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
        self.noise_figure_db_value = noise_figure_db if noise_figure_db is not None else conversion_loss_db
        self.max_rf_input_power_dbm = max_rf_input_power_dbm
        self.max_if_output_power_dbm = max_if_output_power_dbm

    def gain_db(self, freq_hz=None):
        return -abs(self.conversion_loss_db)

    def noise_figure_db(self, freq_hz=None):
        return self.noise_figure_db_value

    def _check_lo_drive(self, lo_power):
        if lo_power is None:
            return

        if self.required_lo_power_dbm is not None and lo_power < self.required_lo_power_dbm:
            print(f"LO drive {lo_power:.1f} dBm below required {self.required_lo_power_dbm:.1f} dBm")

        if self.max_lo_power_dbm is not None and lo_power > self.max_lo_power_dbm:
            print(f"LO drive {lo_power:.1f} dBm above maximum {self.max_lo_power_dbm:.1f} dBm")

    def set_lo_signal(self, signal: SpectrumSignal, lo_freq_hz):
        self.lo_signal = signal
        self.lo_freq = lo_freq_hz

        lo_power = self.lo_signal.tones.get(self.lo_freq)

        if lo_power is None:
            print(f"LO signal has no carrier at {self.lo_freq / 1e6:.3f} MHz")
            return

        self._check_lo_drive(lo_power)


    def process(self, rf_signal: SpectrumSignal):
        self.check_limits(rf_signal)

        if self.lo_signal is None or self.lo_freq is None:
            raise ValueError(
                f"{self.name}: LO signal not configured"
            )

        lo_power = self.lo_signal.tones.get(self.lo_freq)

        if lo_power is None:
            return SpectrumSignal({})

        self._check_lo_drive(lo_power)

        self.check_limits(rf_signal)

        rf_input_power = rf_signal.total_power_dbm()
        if self.max_rf_input_power_dbm is not None and rf_input_power > self.max_rf_input_power_dbm:
            print(f"{self.name} RF input exceeds limit: {rf_input_power:.1f} dBm > {self.max_rf_input_power_dbm:.1f} dBm")

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

        output_signal = SpectrumSignal(out_tones)
        if self.max_if_output_power_dbm is not None:
            if output_signal.total_power_dbm() > self.max_if_output_power_dbm:
                print(
                    f"{self.name} IF output exceeds limit: "
                    f"{output_signal.total_power_dbm():.1f} dBm > {self.max_if_output_power_dbm:.1f} dBm"
                )

        return output_signal

# ___________________________________________________________________
# Models

class TableModel:
    """For filters (LPF, BPF) with datasheet lookup tables."""
    def __init__(self, data_table):
        # data_table expects [freq_hz, loss_db]
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

        if self.resolution_bits is not None:
            quant_snr_db = 6.02 * self.resolution_bits + 1.76
            effective_snr_db = quant_snr_db + (input_power - self.full_scale_dbm)
            print(
                f"ADC theoretical quantization SNR: {quant_snr_db:.1f} dB, "
                f"estimated at this input: {effective_snr_db:.1f} dB"
            )



        # Check frequency range
        for freq in signal.tones:
            if freq > self.bandwidth_hz:
                print(
                    f"ADC bandwidth exceeded: "
                    f"{freq / 1e6:.1f} MHz > "
                    f"{self.bandwidth_hz / 1e6:.1f} MHz"
                )
            if freq > self.sample_rate_hz / 2:
                print(
                    f"Signal at {freq / 1e6:.1f} MHz "
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
        freq_hz,
        output_power_dbm,
        freq_range: Range|None = None,
        power_range: Range|None = None,
        harmonics=None,
        pfd_freq_hz=None,
        spur_level_dbc=None,
        fs_hz=None,
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

    def check_range(self):
        if self.freq_range is not None and not self.freq_range.contains(self.freq_hz):
            print(
                f"Frequency {self.freq_hz / 1e6:.1f} MHz outside "
                f"range {self.freq_range.minimum / 1e6:.1f}-"
                f"{self.freq_range.maximum / 1e6:.1f} MHz"
            )
        if self.power_range is not None and not self.power_range.contains(self.output_power_dbm):
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


    def _apply_images(self, signal, fs_hz):
        tones = signal.tones.copy()
        carrier_power = signal.tones[self.freq_hz]
        
        # Typical DAC image suppression is 40-60 dBc depending on filtering
        image_suppression = -50 
        
        # First Nyquist zone images
        images = [fs_hz - self.freq_hz, fs_hz + self.freq_hz]
        for img_f in images:
            if img_f > 0:
                _merge_tone(tones, img_f, carrier_power + image_suppression)
        return SpectrumSignal(tones)
        
    def _apply_harmonics(self, signal):
        tones = signal.tones.copy()
        for f_fund, p_fund in signal.tones.items():
            for order, level_dbc in self.harmonics.items():
                f_harm = f_fund * order
                p_harm = p_fund - abs(level_dbc)

                _merge_tone(tones,f_harm,p_harm)

        return SpectrumSignal(tones)
    
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
    def __init__(self, name, temp_k=290.0):
        super().__init__(name, "Antenna")
        self.temp_k = temp_k # Kelvin
        self.tones = {}

    def add_signal(self, freq_hz, power_dbm):
        """Adds a wanted signal or an interferer."""
        self.tones[freq_hz] = power_dbm
        return self

    def add_thermal_noise(self, bandwidth_hz):
        """Adds thermal noise floor: -174 dBm/Hz + 10*log10(BW)."""
        noise_floor_dbm = -174 + 10 * math.log10(bandwidth_hz)
        self.tones[0.0] = noise_floor_dbm # Or apply to a range of frequencies
        return self

    def process(self, signal=None):
        # Returns the composite signal as the start of the RX path
        return SpectrumSignal(self.tones)

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
def calculate_noise_budget(components, signal_power_dbm, bandwidth_hz, signal_frequency_hz):
    noise_floor_dbm = -174 + 10 * math.log10(bandwidth_hz)
    cumulative_gain_db = 0.0
    cumulative_nf_linear = 1.0
    previous_gain_linear = 1.0

    rows = [
        {
            "Stage": "Input",
            "Gain [dB]": 0.0,
            "Noise Figure [dB]": 0.0,
            "Cumulative Gain [dB]": 0.0,
            "Cumulative NF [dB]": 0.0,
            "Signal [dBm]": signal_power_dbm,
            "Noise [dBm]": noise_floor_dbm,
            "SNR [dB]": signal_power_dbm - noise_floor_dbm,
        }
    ]

    for component in components:
        gain_db = component.gain_db(signal_frequency_hz) if hasattr(component, "gain_db") else 0.0
        noise_figure_db = component.noise_figure_db(signal_frequency_hz) if hasattr(component, "noise_figure_db") else 0.0

        gain_linear = 10 ** (gain_db / 10)
        noise_figure_linear = 10 ** (noise_figure_db / 10)

        cumulative_nf_linear = cumulative_nf_linear + (noise_figure_linear - 1.0) / previous_gain_linear
        previous_gain_linear *= gain_linear if gain_linear > 0 else 1.0
        cumulative_gain_db += gain_db

        output_signal_dbm = signal_power_dbm + cumulative_gain_db
        output_noise_dbm = noise_floor_dbm + cumulative_gain_db + 10 * math.log10(cumulative_nf_linear)

        rows.append(
            {
                "Stage": component.name,
                "Gain [dB]": round(gain_db, 2),
                "Noise Figure [dB]": round(noise_figure_db, 2),
                "Cumulative Gain [dB]": round(cumulative_gain_db, 2),
                "Cumulative NF [dB]": round(10 * math.log10(cumulative_nf_linear), 2),
                "Signal [dBm]": round(output_signal_dbm, 2),
                "Noise [dBm]": round(output_noise_dbm, 2),
                "SNR [dB]": round(output_signal_dbm - output_noise_dbm, 2),
            }
        )

    return pd.DataFrame(rows)