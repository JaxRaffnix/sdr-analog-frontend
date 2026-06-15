# Oszillatorwahl für das SDR-Frontend

Ziel ist die Erzeugung eines Sinussignals bei 1,9 GHz ohne Gleichanteil und ?? V Ausgangsamplitude. Dieses Signal wird als Local Oscillator zum Mischen am Ein- und Ausgang des SDR verwendet.

Die Platine mit dem Oszillator soll möglichst autark sein, um die Komplexität der Ansteuerung zu reduzieren. Eine Datenverbindung zum SDR, um den Oszillator zu steuern, ist nicht erwünscht.

Das Abweichen der Zielfrequenz von 2,4 GHz auf z.B. 2,0 Ghz (1,5 GHz Mischfrequenz) ist abzuraten. Diese Frequenzbereiche sind bereits stark belegt, der SDR beeinflusst damit möglicherweise andere Geräte und umgekehrt.

## Bewertete Optionen

| Option | Vorteil | Nachteil / Risiko | Einschätzung |
|---|---|---|---|
| Custom Crystal Oscillator | Sehr gute Frequenzstabilität und einfacher Aufbau | Liefert meist nur ein digitales Ausgangssignal; für ein Sinussignal sind Zusatzschaltungen nötig | Nur mit RF-Balun und Bandpassfilter sinnvoll, ansonsten nicht direkt passend |
| Voltage-Controlled Oscillator (VCO) | Direkte Erzeugung im GHz-Bereich, analog regelbar | Empfindlich gegenüber Temperatur und Versorgung; TX und RX können auseinanderlaufen | Technisch möglich, aber wegen Drift nur bedingt geeignet |
| Temperature-Compensated Crystal Oscillator (TCXO) | Bessere Stabilität als ein einfacher XO | In diesem Frequenzbereich meist nicht direkt verfügbar | Eher als Referenzquelle geeignet, nicht als Endlösung |
| Phase-Locked-Loop mit externer SPI-Steuerung | Frei einstellbar und präzise | Externe Konfiguration ist nicht gewünscht | Technisch stark, aber für das Konzept zu aufwendig |
| Phase-Locked-Loop mit fester Frequenz | Kein laufender Steueraufwand | In der Ziel-Frequenz 1,9 GHz bisher kein passendes Bauteil gefunden | Ideale Lösung, falls ein passender Typ verfügbar ist |
| Phase-Locked-Loop mit einmaligem Setup | Nach der Initialisierung autonom | Zusätzlicher Mikrocontroller oder EEPROM für das Setup erforderlich | Einer der besten Kompromisse zwischen Aufwand und Autarkie |
| Phase-Locked-Loop mit Pin-Strapping | Keine serielle Konfiguration nötig | Keine passenden Bausteine mit ausreichendem Frequenzbereich gefunden | Nur dann interessant, wenn ein passender 1,9-GHz-Typ existiert |
| Dielectric Resonator Oscillator (DRO) | Gute Hochfrequenz-Eigenschaften und oft niedriges Phasenrauschen | Beschaffung und Abstimmung sind aufwendig | Mögliche Alternative, falls ein passendes 1,9-GHz-Modul verfügbar ist |
| Direct Digital Synthesis (DDS) | Hohe Flexibilität und präzise Phasensteuerung | Für 1,9 GHz nur indirekt nutzbar und sehr aufwendig | Für dieses Projekt eher nicht sinnvoll |
| SAW-Oszillator | Kompakt und stabil | Meist nur bis etwa 1 GHz verfügbar | Für 1,9 GHz nur mit Frequenzumsetzung nutzbar |
| Eigener Phase-Locked-Loop mit diskreten Komponenten | Vollständig anpassbar | Hohe Komplexität, hoher Abgleichaufwand und viele Anforderungen an die Stabilität | Für dieses Projekt zu aufwendig |

## Optionen

### Custom Crystal Oscillator

Beispiele:
- [Si560](https://www.mouser.de/datasheet/3/564/1/si560_datasheet.pdf) (nicht vorrätig, 8 Wochen Vorlaufzeit)
- [AX5PBF1-1800.0000C](https://www.digikey.de/de/products/detail/abracon-llc/AX5PBF1-1800-0000C/9818179) (nur im 10er Stück, insgesamt 106€)
- [ASG-D-X-A-1.500GHZ](https://www.digikey.de/de/products/detail/abracon-llc/ASG-D-X-A-1-500GHZ/3315186) (unzureichende Frequenz)

Liefern ein digitales Ausgangssignal, zum Beispiel LVPECL, LVDS, CML, HCSL oder CMOS. Weitere Schaltungen sind notwendig, um daraus ein sauberes Sinussignal zu erzeugen.
Ggf. sind bei aktiven Mischern auch digitale Signale ausreichend. 

*Kompromiss: RF-Balun → Bandpassfilter zur Unterdrückung von Oberwellen*

### Voltage-Controlled Oscillator (VCO)

Beispiel:
- [CVCO55CC-2000-2000](https://www.mouser.de/ProductDetail/Crystek-Corporation/CVCO55CC-2000-2000?qs=4zFPArRKzl6bUiT9O3Za5w%3D%3D)

Reagieren empfindlich auf Temperatur, Versorgungsspannung und Bauteiltoleranzen. Ohne Regelung können Sendepfad und Empfangspfad auseinanderlaufen. 

*Kompromiss: Frequenzverschiebun im SDR detektieren und ausgleichen.*

### Temperature-Compensated Crystal Oscillator (TCXO)

Beispiel:
- [SiT8008](https://www.mouser.de/datasheet/2/564/1/sit8008_datasheet.pdf)

Nicht direkt bei 1,9 GHz verfügbar, maximal 1.5 Ghz.

*Kompromiss: Frequenzvervielfacher → Bandpassfilter*

### Phase-Locked-Loop (PLL) mit externer SPI-Steuerung über RFSoC

Beispiel:
- [ADF4351](https://www.analog.com/media/en/technical-documentation/data-sheets/adf4351.pdf)

Extene Steuerung über SPI nicht gewünscht.

*Kompormiss: SPI Schnittstelle über RFSoC*

### Phase-Locked-Loop mit fester Frequenz

Nicht auffindbar.

### Phase-Locked-Loop mit einmaligen Setup

Beispiel für den Initialisierer:
- [ATtiny202](https://www.microchip.com/en-us/product/attiny202)

Setup über SPI-Schnittstellen-Mikrocontroller oder EEPROM

*Kompromiss: Einmalige Initialisierung mit einem Mikrocontroller, danach autark.*

### Phase-Locked-Loop mit Pin-Strapping

Beispiel:
- [AD9552](https://www.mouser.de/ProductDetail/Analog-Devices/AD9552BCPZ?qs=%2FtpEQrCGXCyMFaCeTojWlA%3D%3D)

Keine Geräte mit ausreichendem Frequenzbereich für 1,9 GHz gefunden. Das Beispiel liegt im MHz Bereich.

### Dielectric Resonator Oscillator (DRO)

Beipsiel:
- [digikey](https://www.digikey.de/en/products/filter/resonators/174?s=N4IgjCBcoLQExVAYygFwE4FcCmAaEA9lANogCsIAugL74wBsiIKkGO%2BRkpAzFdbSEbQQASwAmUEHDBkADCHwAHVJICqAOxGoA8gDMAstgCGAZ0zpsCkKgCeiy5BBiTKfkA)

Nicht in 1.9 Ghz auffinbar.

*Kompromiss: Frequenzvervielfacher → Bandpassfilter*

### Direct Digital Synthesis (DDS)

Beispiel: [AD9914S](https://www.analog.com/en/products/ad9914s.html)

Enormer Aufwand.

### SAW-Oszillator

Beispiel:
- [Mouser](https://www.mouser.de/c/passive-components/frequency-control-timing-devices/oscillators/saw-oscillators/?instock=y&sort=frequency%7C1)

Maximal mit 1 Ghz verfügbar.

*Kompromiss: Frequenzvervielfacher → Bandpassfilter*

### Eigener Phase-Locked-Loop mit diskreten Komponenten

Hoher Aufwand, große Komplexität und hohe Anforderungen.

## Schlussfolgerung

Diese Lösungen sind sinvoll umsetzbar:

1. Phase-Locked-Loop mit einmaligen Setup
2. Custom Crystal Oscillator mit RF-Balun und Bandpassfilter

Um den Arbeits- und Testaufwand zu reduzieren, wird auf einen weiteren Mikrocontroller zum PLL-Setup verzichtet.

**Vielleicht lässt sich die Mittenfrequenz des SDR Outputs erhöhen auf 900 MHz? Dann wären 1,5 Ghz Mischfrequenzen möglich!**