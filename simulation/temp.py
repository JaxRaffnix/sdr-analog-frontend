import math
import itertools
import numpy as np
import pandas as pd
import plotly.express as px
import pandas as pd


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
# Core Components
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


def _apply_harmonics(signal, harmonics_map):
    """
    Applies harmonics to an existing signal.
    """
    new_tones = signal.tones.copy()
    
    # We apply harmonics to all existing tones in the signal
    for f_fund, p_fund in signal.tones.items():
        for order, rel_level_dbc in harmonics_map.items():
            f_harm = f_fund * order
            p_harm = p_fund + rel_level_dbc
            
            # Use mW summation to merge with existing power if frequency overlaps
            total_mw = _dbm_to_mw(new_tones.get(f_harm, -999)) + _dbm_to_mw(p_harm)
            new_tones[f_harm] = _mw_to_dbm(total_mw)
            
    return new_tones


def _apply_spurs(signal, spur_spacing_mhz, spur_level_dbc, num_offsets=2):
    """
    Applies spurs to an existing signal.
    """
    new_tones = signal.tones.copy()
    
    for f_fund, p_fund in signal.tones.items():
        for n in range(1, num_offsets + 1):
            for sign in [-1, 1]:
                f_spur = f_fund + (sign * n * spur_spacing_mhz)
                p_spur = p_fund + spur_level_dbc
                
                # Merge with existing power using mW summation
                total_mw = _dbm_to_mw(new_tones.get(f_spur, -999)) + _dbm_to_mw(p_spur)
                new_tones[f_spur] = _mw_to_dbm(total_mw)
            
    return new_tones


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


class RFComponent:
    def __init__(self, name, part_number, voltage=0, current_typ_ma=0, max_input_power_dbm=20):
        self.name = name           
        self.part_number = part_number 
        self.voltage = voltage
        self.current_typ_ma = current_typ_ma
        self.max_input_power_dbm = max_input_power_dbm
        self.warnings = []

    def __repr__(self):
        return f"{self.name} ({self.part_number})"

    def check_limits(self, signal):
        """Standardized rating check."""
        pin = signal.total_power_dbm()
        if pin > self.max_input_power_dbm:
            self.warnings.append(f"Rating Exceeded: {pin:.1f} dBm > {self.max_input_power_dbm} dBm")
        return self.warnings

    def dc_power_mw(self):
        return self.voltage * self.current_typ_ma

    def process(self, signal):
        """Must be implemented by subclasses."""
        raise NotImplementedError


class Amplifier(RFComponent):
    def __init__(self, name, part_number, model, voltage=5.0, current_typ_ma=58.0, current_max_ma=66.0, **kwargs):
        super().__init__(name, part_number, **kwargs)
        self.model = model
        self.current_max_ma = current_max_ma

    def check_compression(self, signal, output_power_dbm):
        """Checks if output power is pushing the amp into saturation."""
        # Get P1dB at the signal frequency
        center_f = list(signal.tones.keys())[0] if signal.tones else 1000.0
        p1db = self.model.get_p1db(center_f / 1000.0) # convert MHz to GHz
        
        # Check against P1dB
        headroom = p1db - output_power_dbm
        
        if output_power_dbm >= p1db:
            self.warnings.append(f"CRITICAL: Amp in saturation! Pout ({output_power_dbm:.1f} dBm) >= P1dB ({p1db:.1f} dBm)")
        elif headroom < 1.0:
            self.warnings.append(f"WARNING: Compression! Pout is {headroom:.1f} dB from P1dB. Expect high distortion.")

    def process(self, signal: SpectrumSignal):
        self.warnings = []
        self.check_limits(signal)
        
        # 1. Apply Gain
        out_tones = {}
        for f, p in signal.tones.items():
            gain = self.model.get_gain(f)
            out_tones[f] = p + gain

        # 3. Compression Check
        pout = signal.total_power_dbm()
        self.check_compression(signal, pout)
            
        # 3. Apply Non-Linearity (IM3)
        # We assume OIP3 is roughly constant or taken at the center freq
        center_f = list(signal.tones.keys())[0] if signal.tones else 0
        oip3 = self.model.get_oip3(center_f)
        
        temp_signal = SpectrumSignal(out_tones)
        final_tones = _apply_im3(temp_signal, oip3)
        
        return SpectrumSignal(final_tones), self.warnings


class Filter(RFComponent):
    def __init__(self, name, part_number, loss_model, **kwargs):
        super().__init__(name, part_number, **kwargs)
        self.loss_model = loss_model
    
    def process(self, signal: SpectrumSignal):
        self.warnings = []
        out_tones = {}
        
        for f, p in signal.tones.items():
            # Support both static float loss or a function/model
            loss = self.loss_model(f) if callable(self.loss_model) else self.loss_model
            out_tones[f] = p - abs(loss) # Assuming loss is positive input
            
        return SpectrumSignal(out_tones), self.warnings
    

class Mixer(RFComponent):
    def __init__(self, name, part_number, conversion_loss_db, lo_freq_mhz=None, lo_power_dbm=None, 
                 lo_rf_isolation=35, if_rf_isolation=25, **kwargs):
        # Pass kwargs to RFComponent for things like max_input_power_dbm
        super().__init__(name, part_number, **kwargs)
        self.conversion_loss_db = conversion_loss_db
        self.lo_freq = lo_freq_mhz
        self.lo_power = lo_power_dbm
        self.lo_rf_iso = lo_rf_isolation
        self.if_rf_iso = if_rf_isolation

    def process(self, signal: SpectrumSignal):
        warnings = []     
        if self.lo_freq is None or self.lo_power is None:
            raise ValueError(f"Mixer '{self.name}' LO freq or power not set!")   
        if not (7.0 <= self.lo_power <= 10.0):
            warnings.append(f"LO Drive {self.lo_power:.1f} dBm out of spec (Target: 7-10 dBm)")
            
        self.check_limits(signal)

        # Initialize output with LO Leakage
        out_tones = {self.lo_freq: self.lo_power - self.lo_rf_iso}
        
        print(f"--- Mixer Input ---")
        for f, p in signal.tones.items():
            print(f"Input Tone: {f} MHz @ {p:.2f} dBm")

        for f, p in signal.tones.items():
            # A. IF-RF Feedthrough (Original signal leakage)
            # Use mW summation to handle potential overlapping frequencies
            leakage_p = p - self.if_rf_iso
            _merge_tone(out_tones, f, leakage_p)
            
            # B. Conversion Products (f + LO and |f - LO|)
            # Corrected: Subtracting conversion loss
            conv_p = p - self.conversion_loss_db
            _merge_tone(out_tones, f + self.lo_freq, conv_p)
            _merge_tone(out_tones, abs(f - self.lo_freq), conv_p)

        print(f"--- Mixer Output ---")
        for f, p in out_tones.items():
            print(f"Output Tone: {f} MHz @ {p:.2f} dBm")
            
        return SpectrumSignal(out_tones), self.warnings


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
        self.gain_data = np.array(gain_data)
        self.oip3_data = np.array(oip3_data)
        self.p1db_data = np.array(p1db_data)

    def get_gain(self, freq_mhz):
        return np.interp(freq_mhz / 1000.0, self.gain_data[:, 0], self.gain_data[:, 1])

    def get_oip3(self, freq_ghz):
        return np.interp(freq_ghz, self.oip3_data[:, 0], self.oip3_data[:, 1])

    def get_p1db(self, freq_ghz):
        return np.interp(freq_ghz, self.p1db_data[:, 0], self.p1db_data[:, 1])
    

# ___________________________________________________________________
# Components
class PLLADF4351(RFComponent):
    MIN_FREQ = 35.0 # MHz
    MAX_FREQ = 4400.0
    MIN_POWER = -4.0 # dBm
    MAX_POWER = 5.0

    def __init__(self, name, part_number, freq_mhz=1500.0, output_power_dbm=3.0, 
                 spur_spacing_mhz=10.0, spur_level_dbc=-55.0, **kwargs):
        super().__init__(name, part_number, **kwargs)
        self.freq_mhz = freq_mhz
        self.output_power_dbm = output_power_dbm
        self.spur_spacing_mhz = spur_spacing_mhz
        self.spur_level_dbc = spur_level_dbc
        self.harmonics_map = {2: -20, 3: -30}

    def _validate_settings(self):
        """Checks if the PLL settings are within operating datasheet limits."""
        self.warnings = []
        if not (self.MIN_FREQ <= self.freq_mhz <= self.MAX_FREQ):
            self.warnings.append(f"Frequency out of range: {self.freq_mhz:.1f} MHz (Limit: {self.MIN_FREQ}-{self.MAX_FREQ} MHz)")
        
        if not (self.MIN_POWER <= self.output_power_dbm <= self.MAX_POWER):
            self.warnings.append(f"Power out of range: {self.output_power_dbm:.1f} dBm (Limit: {self.MIN_POWER}-{self.MAX_POWER} dBm)")

    def process(self, signal=None):
        # 1. Create base signal
        signal = SpectrumSignal({self.freq_mhz: self.output_power_dbm})
        
        # 2. Apply Imperfections
        signal = SpectrumSignal(_apply_harmonics(signal, self.harmonics_map))
        signal = SpectrumSignal(_apply_spurs(signal, self.spur_spacing_mhz, self.spur_level_dbc))
        
        return signal, []

# ___________________________________________________________________
# Run Simulation Function
def calculate_system_budget(components):
    total_mw = sum(c.dc_power_mw() for c in components)
    return {"total_typ_mw": total_mw, "rails": {c.name: c.dc_power_mw() for c in components}}


def run_simulation(components, input_signal):
    current_signal = input_signal
    system_log = []

    for comp in components:
        current_signal, warnings = comp.process(current_signal)
        system_log.append({
            "name": comp.name,
            "part_number": comp.part_number, # Added this
            "tones": current_signal.tones,
            "warnings": warnings
        })
        
    return system_log


def print_system_health(system_log):
    for stage in system_log:
        if stage["warnings"]:
            for warning in stage["warnings"]:
                print(f"⚠️ [{stage['name']}]: {warning}")



def format_simulation_results(system_log):
    """Converts the system log into a readable DataFrame."""
    formatted_data = []
    
    for entry in system_log:
        # Create a string representation of the spectrum for this stage
        spectrum_str = ", ".join([f"{f:.0f}MHz: {p:.1f}dBm" for f, p in entry["tones"].items()])
        
        formatted_data.append({
            "Component": entry["name"],
            "Part Number": entry["part_number"],
            "Total P (dBm)": f"{entry['total_power']:.2f}",
            "Spectrum": spectrum_str,
            "Warnings": " | ".join(entry["warnings"]) if entry["warnings"] else "None"
        })
        
    return pd.DataFrame(formatted_data)



def plot_spectrum(system_log, selected_component_name):
    """Plots the spectrum for a specific component."""
    # Find the data for the selected component
    comp_data = next((item for item in system_log if item["name"] == selected_component_name), None)
    
    if not comp_data:
        return "Component not found."

    # Convert tones dict to DataFrame for plotting
    df = pd.DataFrame(list(comp_data["tones"].items()), columns=["Freq (MHz)", "Power (dBm)"])
    
    # Create a "stick" plot (Scatter plot with lines)
    fig = px.bar(df, x="Freq (MHz)", y="Power (dBm)", 
                 title=f"Spectrum at: {selected_component_name}",
                 range_y=[-120, 20]) # Lock Y-axis for consistent comparison
    
    # Style it to look like a Spectrum Analyzer
    fig.update_traces(width=2) # Thinner bars
    return fig

def create_frequency_matrix(system_log):
    # 1. Collect all unique frequencies found in the chain
    all_freqs = set()
    for stage in system_log:
        all_freqs.update(stage['tones'].keys())
    
    # 2. Build the matrix data
    data = {}
    sorted_freqs = sorted(list(all_freqs))
    
    for freq in sorted_freqs:
        row = {}
        for stage in system_log:
            # Store power, or -999 if the tone doesn't exist at this stage
            row[f"{stage['name']}"] = stage['tones'].get(freq, -999)
        data[freq] = row

    # 3. Create DataFrame
    df = pd.DataFrame.from_dict(data, orient='index')
    df.index.name = "Freq (MHz)"
    
    return df

def style_rf_matrix(df):
    """
    Highlights the power levels. 
    -999 is ignored to keep the background clean.
    """
    # Replace -999 with NaN so the gradient ignores it
    styled = df.replace(-999, float('nan'))
    
    return styled.style.background_gradient(
        cmap='viridis', 
        axis=None,  # Gradient across the whole table
        subset=None, 
        vmin=-80,   # Floor of your dynamic range
        vmax=10     # Ceiling of your dynamic range
    ).format("{:.1f} dBm", na_rep="-")