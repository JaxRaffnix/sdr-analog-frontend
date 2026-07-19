# Analog Fronted Design Documentation

## Goal
Transmit and recieve a Signal from an SDR. Convert the Frequency range of the signal from 0.9 to 1 GHz to 2.4 to 2.5 GHz and vice versa. The signal is amplified and filtered to reduce noise and interference.

please refer to the block diagram and schematic for the exact design.

## transmitter
The RFSoC dac outputs a signal with max 40.5 mA current, output power -18.5 to 6.5 dBm.

## receiver
the adc has maximum input power 14.6 dBm, input bandwidth 6 GHz and attenuation range 27 dB.