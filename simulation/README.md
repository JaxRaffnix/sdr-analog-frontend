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

The signal paths are copied from the PCB design. Please see the [block diagram](../docs/Blockschaltbild.png) and the [schematic](../pcb/documents/schematic.pdf) for reference.

All component data has been collected from the relevant datasheets.

## Requirements

- [Python](https://www.python.org/downloads/) => 3.12
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

## Install

Navigate to the `simulation` folder and execute the following commands:

```bash
# generates a virtual environment, downloads python dependencies
uv sync

# Activate the environment
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate
```

If you are working with Visual Studio Code and are prompted to to select a Kernel. choose

```
marimo/sandbox
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

### Local Oscillator
The LO frequency is calculated to support down-conversion of the RF signal ($f_{RF} = 2.45 \text{ GHz}$) to an IF signal ($f_{IF} = 0.95 \text{ GHz}$) with a bandwidth ($f_b = 500 \text{ MHz}$):

$$f_{LO} = f_{RF} - f_{IF} = 1.5 \text{ GHz}$$

*   **Operating Range:** The PLL is stable with an output power between 0.4 dBm and 3.3 dBm.
*   **Mixer Requirement:** This configuration ensures the required 7 dBm LO input power is achieved at the mixer port.

### Transmitter
Analysis assumes a DAC sample frequency of 7 GHz.

*   **Maximum Output:** The RFSoC DAC outputs up to 6.5 dBm, resulting in a system output of 25.54 dBm at the antenna port without exceeding amplifier compression limits.
*   **Target Output:** At an input power of -18.5 dBm, the system produces 0.54 dBm at 2.45 GHz.

### Receiver
*   **Protection:** The integrated power limiter clamps the output to a maximum of 6 dBm, protecting the ADC (max 14.6 dBm) against input signals. This has been tested with signals up to 50 dBm.
*   **ADC Constraints:** To keep the ADC below the full-scale limit (1 dBm), input power must remain below -15 dBm (resulting in an SNR of 54.77 dB).
*   **Sensitivity:** At -100 dBm input, the receiver provides a gain of 15.95 dB (-84.05 dBm output), resulting in an SNR of -30.23 dB.

### Power Analysis
The frontend operates on 3.3 V and 5 V rails. 

| Rail | Typical Power | Maximum Power |
| :--- | :--- | :--- |
| **3.3 V** | 0.419 W | 0.599 W |
| **5.0 V** | 3.725 W | 4.630 W |
| **Total** | **4.144 W** | **5.229 W** |

*   **LDO Integrity:** The 3.3 V LDO (200 mA capacity) operates well within limits, drawing 127 mA (typical) and 181 mA (maximum).