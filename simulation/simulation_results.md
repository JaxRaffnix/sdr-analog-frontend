# SDR Frontend Simulation Results

This report records the results produced by the marimo cells in `power.py` using the default widget values at the time of execution.

## Scope and Default Inputs

The notebook models three signal paths:

- Local oscillator path
- Transmitter path
- Receiver path, including noise and ADC checks
- DC power draw for all modeled components plus the TCXO

Default settings used by the cells:

| Parameter | Value |
| --- | ---: |
| LO frequency | 1,500 MHz |
| LO source power | 1.0 dBm |
| Tx DAC frequency | 950 MHz |
| Tx DAC power | 6.5 dBm |
| Tx DAC sample frequency | 6,000 MHz |
| Rx wanted signal | 2,450 MHz at -55 dBm |
| Rx interferer | 2,470 MHz at -30 dBm |
| Rx bandwidth | 100 MHz |
| Receiver analysis frequency | 2,450 MHz at the antenna, 950 MHz after down-conversion |

The receiver LO is 1,500 MHz, so the wanted 2,450 MHz RF signal is converted to a 950 MHz IF signal. The 2,470 MHz interferer is converted to 970 MHz.

## Executive Findings

- The oscillator chain produces 7.60 dBm at 1,500 MHz at the amplifier output.
- The mixer LO requirement is satisfied: 7.60 dBm is between the 7 dBm minimum and 10 dBm maximum.
- The transmitter produces 25.44 dBm at 2,450 MHz at the PA output.
- The transmitter PA remains below its 32 dBm P1dB and 40 dBm OIP3 limits.
- The receiver ADC input is -13.50 dBm for the default wanted signal and interferer.
- Receiver compression, limiter, ADC full-scale, bandwidth, and maximum-power checks pass.
- The receiver ADC Nyquist check fails because tones above the 2.5 GHz Nyquist frequency are present before aliasing.
- The receiver noise budget ends at 33.42 dB SNR and 5.58 dB cumulative noise figure at the ADC analysis point.
- Modeled DC power is 4.144 W typical and 5.229 W maximum, excluding the 5 V to 3.3 V LDO conversion loss.

## Local Oscillator Analysis

### Stage Results

| Stage | Part | Total power |
| --- | --- | ---: |
| PLL | ADF4351 | 1.45 dBm |
| Balun | XMB0220K1 | -3.55 dBm |
| Low Pass | LFCN-1800+ | -4.62 dBm |
| Power Splitter | PD0922J5050D2HF | -8.25 dBm |
| Amp | PSA4-5043+ | 7.60 dBm |

The primary LO tone remains at 1,500 MHz. The source model also creates harmonics at 3,000 MHz and 4,500 MHz; the low-pass filter attenuates these but does not eliminate them completely.

### Diagnostics

All reported oscillator diagnostics pass:

- PLL frequency: 1,500 MHz is within the 35 to 4,400 MHz range.
- PLL power: 1.0 dBm is within the -4 to 5 dBm range.
- Amplifier dominant frequency: 1,500 MHz.
- Amplifier compression: 7.6 dBm output is below the 20.2 dBm P1dB.
- Amplifier OIP3: 7.6 dBm output is below the 33.1 dBm OIP3.

## Transmitter Analysis

### Stage Results

| Stage | Part | Total power |
| --- | --- | ---: |
| Tx DAC | RFSoC_SDR | 6.14 dBm |
| Mixer | RMS-30+ | 1.85 dBm |
| Bandpass | 2450BP | -2.56 dBm |
| PA | SE2576L-R | 25.44 dBm |

The desired transmitter output is the 2,450 MHz mixer product from a 950 MHz DAC tone and the 1,500 MHz LO. The simulated PA output is 25.44 dBm.

### Diagnostics

All reported transmitter diagnostics pass:

- DAC frequency: 950 MHz is within the 800 to 1,100 MHz range.
- DAC power: 6.5 dBm is at the configured upper limit of -18.5 to 6.5 dBm.
- Mixer LO signal is present at 1,500 MHz.
- Mixer LO power: 7.60 dBm is above the 7 dBm minimum and below the 10 dBm maximum.
- PA dominant frequency: 2,450 MHz.
- PA compression: 25.4 dBm output is below the 32.0 dBm P1dB.
- PA OIP3: 25.4 dBm output is below the 40.0 dBm OIP3.

## Receiver Analysis

### Stage Results

| Stage | Part | Total power |
| --- | --- | ---: |
| Antenna | ANT-001 | -29.99 dBm |
| Bandpass | 2450BP | -31.19 dBm |
| LNA | HMC374 | -21.07 dBm |
| Mixer | RMS-30+ | -12.19 dBm |
| Bandpass Low | SYBP-92+ | -29.03 dBm |
| Amplifier IF | PGA-103+ | -13.20 dBm |
| Limiter | SKY16602-632LF | -13.50 dBm |
| ADC | RFSoC ADC | -13.50 dBm |

At the ADC, the wanted 950 MHz tone is -39.05 dBm and the converted 970 MHz interferer is -14.36 dBm. The interferer is therefore the dominant tone at the ADC input.

### Diagnostics

Receiver diagnostics that pass:

- LNA output is below its 13.0 dBm maximum-output threshold.
- LNA output remains below its 22.0 dBm P1dB and 37.0 dBm OIP3.
- Mixer LO signal and LO frequency are valid.
- Mixer LO input power is within the 7 to 10 dBm requirement.
- IF amplifier output remains below its P1dB and OIP3 limits.
- IF amplifier dominant frequency, 970 MHz, is within its 50 MHz to 4 GHz range.
- Limiter insertion-loss and clipping checks pass.
- ADC input is below the configured full-scale limit of 1.0 dBm.
- All tones are within the configured 6 GHz ADC bandwidth.
- ADC input is below the configured 14.6 dBm maximum input power.

Receiver diagnostic that fails:

- **ADC Nyquist:** the ADC Nyquist frequency is 2,500 MHz, but tones above this frequency are present in the modeled signal. The model reports aliasing of tones above Nyquist to lower frequencies. This is the only reported failed diagnostic in the default run.

## Receiver Noise Budget

The thermal starting point is modeled as -174 dBm/Hz and the receiver bandwidth is 100 MHz, giving an initial noise floor of -94.00 dBm.

| Stage | Analysis frequency | Tone power | Noise floor | SNR | Stage NF | Cumulative NF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Antenna | 2.45 GHz | -55.00 dBm | -94.00 dBm | 39.00 dB | - | 0.00 dB |
| Bandpass | 2.45 GHz | -56.20 dBm | -94.00 dBm | 37.80 dB | 1.20 dB | 1.20 dB |
| LNA | 2.45 GHz | -46.00 dBm | -81.60 dBm | 35.60 dB | 2.20 dB | 3.40 dB |
| Mixer | 0.95 GHz | -53.50 dBm | -87.94 dBm | 34.44 dB | 1.16 dB | 4.56 dB |
| Bandpass Low | 0.95 GHz | -55.44 dBm | -89.31 dBm | 33.87 dB | 0.57 dB | 5.13 dB |
| Amplifier IF | 0.95 GHz | -38.75 dBm | -72.41 dBm | 33.66 dB | 0.21 dB | 5.34 dB |
| Limiter | 0.95 GHz | -39.05 dBm | -72.71 dBm | 33.66 dB | 0.00 dB | 5.34 dB |
| ADC | 0.95 GHz | -39.05 dBm | -72.46 dBm | 33.42 dB | 0.24 dB | 5.58 dB |

The final modeled receiver SNR is 33.42 dB at the ADC analysis point, with 5.58 dB cumulative noise figure. The `Stage NF` column shows each stage's incremental cascade contribution, not its standalone datasheet noise figure. The mixer transforms the wanted signal from 2.45 GHz to 0.95 GHz and contributes 1.16 dB to the cascaded NF.

## DC Power Analysis

The component-level power report contains the following modeled loads:

| Stage | Part | Typical power | Maximum power |
| --- | --- | ---: | ---: |
| PLL | ADF4351 | 0.412 W | 0.591 W |
| TCXO | ATX-11-F-26.000MHZ-F05-T | 0.007 W | 0.008 W |
| PA | SE2576L-R | 2.500 W | 3.250 W |
| Amp | PSA4-5043+ | 0.290 W | 0.330 W |
| LNA | HMC374 | 0.450 W | 0.450 W |
| Amplifier IF | PGA-103+ | 0.485 W | 0.600 W |

Rail totals:

| Rail | Typical current | Maximum current | Typical power | Maximum power |
| --- | ---: | ---: | ---: | ---: |
| 3.3 V | 127 mA | 181 mA | 0.419 W | 0.599 W |
| 5.0 V | 745 mA | 926 mA | 3.725 W | 4.630 W |
| **Total** | - | - | **4.144 W** | **5.229 W** |

The 3.3 V and 5.0 V totals include the modeled components only. The 5 V to 3.3 V LDO is not modeled, so its conversion loss and input-side current are excluded from the total.

## Findings and Follow-up Items

1. The transmitter reaches the intended approximately 25.5 dBm output while remaining below PA compression and OIP3 limits.
2. The LO chain provides sufficient mixer drive with approximately 0.6 dB of margin above the 7 dBm minimum and 2.4 dB below the 10 dBm maximum.
3. In the default receiver case, the -30 dBm interferer is much stronger than the -55 dBm wanted signal and remains dominant at the ADC.
4. The ADC Nyquist failure should be resolved or explicitly accepted by the system design. Options include filtering unwanted tones before the ADC, changing the sample rate, or treating the reported aliases as intentional and verifying their impact.
5. The LNA and the RF input bandpass are the largest contributors to the modeled cascaded noise figure; improving the pre-mixer gain or reducing the RF input loss has more impact than reducing the mixer NF.
6. The simulation still needs an explicit ADC resolution check; the notebook contains a TODO for this item.
7. The HMC374 maximum RF input rating should be checked against the intended operating envelope; the notebook also contains a TODO for this item.

## Reproducibility Note

These values are a snapshot of the default marimo cell outputs. Changing any slider, especially LO frequency or power, Tx settings, receiver tones, or receiver bandwidth, will change the results and diagnostics.
