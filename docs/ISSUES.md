# Offene Fragen

## 1. Detection Pin des Power Amplifiers
- **Problem:** Der Power Amplifier liefert ein analoges Ausgangssignal (0,3 V bis 1,2 V). Der RFSoC besitzt ausschließlich digitale Eingänge. Als Lösung wurde ein PWM-Wandler verwendet: LTC6992CS6-4
- **Fragen:** Ist dies Lösung ausreichend?

## 2. PLL-Evaluierungsboard
- **Problem** Der PLL (ADF4351) wird über ein SPI programmiert, entsprechendes I/O ist auf der Platine bereits vorhanden. Der passende Master dafür muss erst noch implementiert werden. Alternativ kann das [Evaluation Board](https://www.analog.com/media/en/technical-documentation/user-guides/UG-435.pdf) verwendet werden. Dieses hat eine USB-Verbindung und eine Windows-Software, um den PLL zu programmieren. Das Oszillatror-Signal wird über einen SMA-Anschluss ausgegeben.
- **Fragen:** Evaluation Board verwenden, um Programmierung deutlich zu vereinfachen? Auswirkungen auf Signalintegrität lassen sich nicht vorhersagen.
  
## 3. Receiver-Pfad Performance
- **Status:** Die effektive Verstärkung des Receiver liegt bei $-0,3\text{ dB}$. Für ein SNR $> 50$ wird ein Eingangspegel von mindestens $-10\text{ dBm}$ benötigt.
- **Fragen:** Ist die Perfomance verkraftbar? Überarbeitung wird vermutlich etwas Zeit erfordern.
  
## 4. Aisler Netlist Deviation
- **Problem:** Laut Aisler ist ein GND-Pad nicht verbunden. Es ist nicht klar, welches. In KiCad ist kein Fehler zu erkennen.
- **Fragen:** Wie kann der Fehler behoben werden?