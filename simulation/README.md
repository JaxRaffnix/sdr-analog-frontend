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