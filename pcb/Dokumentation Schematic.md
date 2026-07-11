# Documentation Schematic

The schematic and layout is designed with KiCad 10.0. The plugin `kicad-action-scripts` was used to generate via-stitching.

## Board Stack

[Aisler](https://aisler.net/de) was selected as the manufacturer. The following 4-layer stackup was chosen from the manufacturers' portfolio:
- 4 Layer
- 1.6 mm Thickness
- 35 µm ENIG Surface Finish
- FR4 TG 150°C Base material 

[Portfolio](https://community.aisler.net/t/pcb-portfolio/101)

[Relevant Stackup](https://community.aisler.net/t/4-layers-1-6mm-35-m-stackup/5457)

[Design Rules](https://community.aisler.net/t/4-layer-35-m-enig-design-rules/3733)

[KiCad Files](https://github.com/AislerHQ/aisler-support/tree/master/kicad/aisler-4-layer-hd-drc)

The layers were assigned as follows:
1. Signal Layer 1 (Top)
2. Ground Plane
3. Power Plane
4. Signal Layer 2 (Bottom)

## High Speed Data Tracks

High Frequency tracks are designed as microstrip lines. They are single ended with an impedance of 50 Ohm. frequencies of 0.9 Ghz, 1 GHz, 1.5 GHz, 2.4-2.5 GHz are used.

The manufacturer recommends 
**W = 295 um.**

With the KiCad calculator, this was the result:
- e_r = 4,3
- H = 0.14 mm
- T = 0,035 mm
- R = 50 OHm
- f =  0,9 Ghz, 1,5 Ghz, 2,5 Ghz
=> W  = 235,843 um

![Screenshot](<Transmission Line Calculation.png>)

## Power
Power good LEDs für 5V und 3,3 V Rails.

- grün für 3.3 V LDO output
- gelb für 5 V 
- rot für Flag output

### USB3_A_Receptacle_Wuerth_692122030100
Input mit USB A 3.0

### AP22811AW5-7
X7R or X5R between AP228 und Ground
Connect a minimum 100μF low ESR electrolytic or tantalum capacitor (or 10μF MLCC) between OUT and GND is also needed for hot-plug
applications.

Power Switch IC wird über DIP Schalter oder GPIO gesteuert: DIP und GPIO müssen aktiv sein. GPIO mit Jumper high setzen!

FLG LED zeigt Fehlerstatus: overcurrent, overtemperature an. Kann mit falling Edge an GPIO erkannt werden.

### LT3042

I out max 200 mA

## Power Budget
Ozillator: 0 dBm +. 5 dBm peak
Balun: -3 dB
Filter: -1 dB
Splitter: -0.5 dB

**Summe: -4.5 dB**

Amplifier: 13 dB

**Gesamt: 8.5 dB**



## GPIO

Pins mit 2,54 mm Pitch. Assignment ist dem Schematic zu entnehnen.

## Transmitter

Bandpass vor LNA verschlechtert dB um xx. Aber Unerwünschte Frequzenzen werden nicht verstärkt.


### SE2576L-R

Enable Pin max. 3,6 V

### RMS-30+

max RF Power 200mW
max IF Current 40mA


## ADF

max output power: 5 dBm


## Via Stitching

Abstand sollte lambda/20 betragen. Bei 2,4 GHz ist das lambda = 125 mm. Abstand der Vias sollte also kleiner als 6,25 mm sein.


## Ideen: 

25% weniger Kosten mit [Aisler Logo](https://community.aisler.net/t/looking-for-an-aisler-coupon-code-here-s-how-to-save-on-your-next-project/5495)