---
title: Readme
marimo-version: 0.23.14
---

# SDR Frontend Simulation

The simulation covers:
- Link Budget
- Noise Budget
- DC Power Draw

The signal paths for the oscillator, transmitter, and receiver are modeled and analyzed separately. Only the mixer stage combines the oscillator path on its LO input with either Tx or Rx path to generate the output.

The signal paths are copied from the PCB design. Please see the [block diagram](../docs/Blockschaltbild.png) and the [schematic](../pcb/main_v2/main_v2.pdf) for reference.

All component data has been collected from the relevant datasheets.

## Requirements

- [Python](https://www.python.org/downloads/) => 3.12
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

## Install

Navigate to the `simulation` folder and execute the following commands:

```bash
# generates a virtual environment, downloads python dependencies
uv sync

# activates the virtual environment on windows
.venv/scripts/activate

# activates the virtual environment on linux
source .venv/bin/activate
```

## Usage

To view the simulation results, run the following command. This opens the marimo notebook in a new browser window.
```bash
uv run marimo run power.py
```

If you want to inspect the code and make changes, run:
```bash
uv run marimo edit power.py
```

## Simulation Results

### Oscillator

the LO frequency for mixing with a IF signal f_c = 0.95 GHz, f_b = 100 MHz and RF signal f_c = 2.45 GHz f_b = 100 MHz is:
f_LO = f_RF - f_IF = 2.45 GHz - 0.95 GHz = 1.5 GHz

From the simulation, the PLL can safely be opertated between 0.4 dBm and 3.3 dBm output power. This ensures the minimum LO power of 7 dBm at the LO port of the mixer.

### Transmitter

The DAC of the RFSoC can output up to 6.5 dBm output power, which will result in a output signal with 25.54 dBm at f_RF without compromising the amplfier. with -18.5 dBm output power, the signal at 2.45 GHz will be 0.54 dBm. 

All of this assumesa a DAC sample frequency of 7 GHz.

### Receiver

The power limiter ensures a maximum output power of 6 dBm, even when a very strong Rx signal of 50 dBm is present.

To keep the ADC below the full scale power of 1 dBm, the total input power must not exceed -15 dBm. The resulting SNR is 54.77 dB.

for a signal with -100 dBm input power, the receiver boosts it to -84.05 dBm, which is an increase of 15.95 dB. The resulting SNR is -30.23 dB.

### DC Power

THe 3.3 V rail requires 0.419 W typically and maximum 0.599 W.
The 5V rail uses 3.725 W typically and maximum 4.63 W.

So the total power draw is 4.144 W typically and 5.229 W maximum.

The 3.3V LDO can supply up to 200 mA, the maximum current is 181 mA with a typical value of 127 mA, which is inside the limits.

