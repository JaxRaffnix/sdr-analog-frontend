# Layout Documentation

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

## Traces

### High Speed Data Tracks

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

Clearance 3xW = 0.9 mm

### Track Width & Clearance

Power, GND
wire width 0,381 mm
clearance 0,2032 mm

default
rack width 0,2032 mm
clearance 0,1524 mm

## Vias

via size 0.6096 mm
via hole 0.3048 mm

### Pours and Via Stitching

On layer 1, a ground pour is used. For via stitching, the plugin `kicad-action-scripts` was used. Distance between vias should be less than lambda/20. At 2.4 GHz, lambda = 125 mm. The distance between vias should therefore be less than 6.25 mm. Selected value is:
- Spacing: 4 mm

The vias size is used from the vias gnd definition, see section above.

CAVE: some vias of the plugin might get assigned to a power rail net class. Manually highlight them on the board and change their net to GND. 