# Offene Fragen

## 1. Detection Pin des Power Amplifiers
- **Problem:** Der Power Amplifier liefert ein analoges Ausgangssignal (0,3 V bis 1,2 V). Der RFSoC besitzt ausschließlich digitale Eingänge. Als Lösung wurde ein PWM-Wandler verwendet: LTC6992CS6-4
- **Fragen:** Ist dies Lösung ausreichend?

## 2. PLL-Evaluierungsboard
- **Problem:** Der PLL (ADF4351) wird über ein SPI programmiert, entsprechendes I/O ist auf der Platine bereits vorhanden. Der passende Master dafür muss erst noch implementiert werden. Alternativ kann das [Evaluation Board](https://www.analog.com/media/en/technical-documentation/user-guides/UG-435.pdf) verwendet werden. Dieses hat eine USB-Verbindung und eine Windows-Software, um den PLL zu programmieren. Das Oszillator-Signal wird über einen SMA-Anschluss ausgegeben.
- **Fragen:** Evaluation Board verwenden, um Programmierung deutlich zu vereinfachen? Auswirkungen auf Signalintegrität lassen sich nicht vorhersagen.
  
## 3. Power Adjustment
- **Status:** Im Exposé wurde die Möglichkeit, die Eingangs- und Ausgangsleistung über GPIO zu steuern, gewünscht. Aufgrund der Komplexität wurde dies jedoch nicht umgesetzt. Lediglich die Leistung des PLL kann über SPI gesteuert werden.
- **Fragen:** Ist das ausreichend?

## 4. Power Limiter
- **Status:** Der Power Limiter im Rx Pfad liegt direkt vor der Connection zum ADC, um diesen zu schützen. Damit sind die Komponenten meiner Platine nicht geschützt.
- **Fragen:** Sollte der Power Limiter direkt zu Beginn liegen, um meine Komponenten ebenfalls zu schützen? Mit den maximal 6 dB am Ausgang des Limiters und 15 dB Verstärkung meiner Platine, kann der ADC aber wieder Schaden nehmen. Einen Limiter mit exakt passenden Wert zu finden, der sowohl meine Komponenten als auch den ADC schützt, ist sehr schwierig.

## 5. Thermal Vias
- **Fragen:** Wie werden thermal vias in KiCad platziert? Irgendwie stimmen die Erklärungen nicht mit der vorhandenen PCB überein.