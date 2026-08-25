# Notes on Assembly

## lessons learned

- zweite Power supply option über banaanenstecker o.ä. ermöglichen. einfacher aufbau im labor

## Power supply

5V dc 2A Barrel Jack

muss kompatibel sein mit [PJ-063AH](https://www.mouser.de/de/ProductDetail/Same-Sky/PJ-063AH?qs=WyjlAZoYn51bQfA53nMcVA%3D%3D).
- Durchmesser Innenkontakt 2 mm
- Durchmesser Außenkontakt 6.5 mm
- Max 8 A, 24 V
- Jack Male Pin

## Mouser Nachbestellung

Lieferung expected überlicherweise in 3 Tagen. Aufgegeben am 19.08.26.

- R211: 33.2k 0603. Alternative: 71-CRCW060333K2FKEAC. ist nachbestellt
- Q201: DMP3068L-7. Alternative: DMP3068L-13. ist nachbestellt
- L403: 620 nH, 0402. ist nachbestellt mit 640 nH.
- L401: 27 nH 0603. ist nachbestellt

## Missing Components

- FL402: SYBP-92+. ist im lieferrückstand, expected Lagerbestand am 24.08.26. Alternativ bei [win-source](https://www.win-source.net/products/detail/mini-circuits/sybp-92.html) auf Lager.
- R502, R504: DNI
- U401: TCCH 80+. wird über municom geliefert. Liefernachricht erhalten am 19 Aug 2026.

## Nacharbeiten

- C605: kaum Lötpaste auf 1 Pad. **FIXED**
- C530: nur 1 bein . **FIXED**
- IC401: footprint zu groß für tatsächliches Bauteil **FIXED**
- Fl401: package liegt schräg auf. Pads unklar