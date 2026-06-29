# Dokumentation Schematic


[Aisler PCB](https://aisler.net/p/YPFMCLNO)

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


### SE2576L-R

Enable Pin max. 3,6 V

### RMS-30+

max RF Power 200mW
max IF Current 40mA

