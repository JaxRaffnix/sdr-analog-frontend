# Schematic Documentation

We aim to use 

## Status LEDs

Every Power Rail has its own green status LED.
- 5 V
- 3.3 V

Also, digital Outputs for IC status get a red LED.
- Load Management Power Faulty
- 3.3 V LDO Faulty
- PLL Lock Detected

Some Input pins also get a LED:
- Load Management Enable
- Amplifier Enable

## Power Management

The PCB is designed for a 5V Barrel Jack with max 3A output current. The simulation in [power.py](../simulation/power.py) shows an expected power consumption of 3W and a maximum of 4.5W. So a maxmimal current of 1A is expected.

The LDO can output up to 200 mA. From simulation, the expected value is 130 mA and the peak is 180 mA.

On the input side, a ESD Protection, Revers Polarity Protection and Noise Reduction with Ferrite Bead and Capacitors is used.
The load management IC provides overcurrent and overtemperature protection. It is hot-plug capable.

**Both the Manual Switch and the GPIO Pin have to be active for the load management to work!**

## Input and Ouput Pins

Every GPIO Pin has a 100 Ohm current limiting resistor in series. Every IO pin on the PCb requires 3.3V or higher for digital HIgh.

There is one analog output signal, the Power Detection of the Power Amplifier for the Tx path. a PWM generator is used to convert it to a digitial signal.

Every digital I/O is passed trough a driver with 3.3 V. and then to pin header with 2,54 mm pitch.

For the input pins, a 3-pin-header is used. Using a jumper, the pin can be connected to GND or 3.3V to select High or Low. Alterantively, the pin can be connected to the GPIO pin of the RFSoC. 

The PLL uses a SPI connection. A level shifter is used to connect the pins to the SPI master. With a NMOS transistor, the level shifter is disabled when no Vcc is supplied by the SPI pin.

## Transmitter, Receiver, oscillator
the components can be checked in the block diagram and schematic.

## Ideen: 

25% weniger Kosten mit [Aisler Logo](https://community.aisler.net/t/looking-for-an-aisler-coupon-code-here-s-how-to-save-on-your-next-project/5495)