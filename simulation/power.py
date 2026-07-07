import marimo

__generated_with = "0.23.9"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    import temp as temp
    # import components as components
    return mo, temp


@app.cell
def _(mo):
    mo.md("""
    # RF Link Budget, Frequency and Power Analysis
    Calculates the link budget for a chain of RF components, including mixers, filters, and amplifiers. Frequency behavior is roughly modeled.

    Additionally, the total DC power draw is estimated.
    """)
    return


@app.cell
def _(temp):
    mixer =  temp.Mixer("Mixer ", "RMS-30+", conversion_loss_db=7.5)
    return (mixer,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Oscillator Analysis
    """)
    return


@app.cell
def _(mo):
    ox_freq = mo.ui.slider(start=35.0, stop=4400.0, step=10.0, value=1500.0, label="PLL Freq (MHz)", show_value=True)
    ox_power = mo.ui.slider(start=-4.0, stop=5.0, step=0.1, value=3.0, label="PLL Power (dBm)", show_value=True)

    mo.vstack([ox_freq, ox_power])
    return ox_freq, ox_power


@app.cell
def _(mixer, mo, ox_freq, ox_power, temp):
    mixer.lo_freq = ox_freq.value 
    mixer.lo_power = ox_power.value

    lpf_model = temp.TableModel([
        [100.0, 0.07], [500.0, 0.21], [1000.0, 0.41], [1500.0, 0.62], 
        [1850.0, 0.86], [2000.0, 1.21], [2450.0, 32.51], [9000.0, 19.80]
    ])
    psa4_model = temp.AmplifierModel(
        gain_data=[[0.05, 25.4], [0.5, 22.1], [1.0, 18.4], [2.0, 13.3], [3.0, 10.2], [4.0, 8.0]],
        oip3_data=[[0.05, 31.0], [0.5, 32.1], [1.0, 33.5], [2.0, 32.7], [3.0, 33.6], [4.0, 32.6]],
        p1db_data=[[0.05, 18.9], [0.5, 19.3], [1.0, 19.8], [2.0, 20.7], [3.0, 21.2], [4.0, 21.5]]
    )

    path = [
        temp.PLLADF4351("PLL", "ADF4351", freq_mhz=ox_freq.value, output_power_dbm=ox_power.value),
        temp.Filter("Balun", "XMB0220K1", loss_model=-5.0),
        temp.Filter("Low Pass","LFCN-1800+", loss_model=lpf_model),
        temp.Filter("Power Splitter", "PD0922J5050D2HF", loss_model=-3.71),
        temp.Amplifier("Amp", "PSA4-5043+", psa4_model, voltage=5.0, current_typ_ma=58.0, current_max_ma=66.0),
        mixer
    ]
    results = temp.run_simulation(path, temp.SpectrumSignal())

    temp.print_system_health(results)

    df_matrix = temp.create_frequency_matrix(results)


    comp_names = [c["name"] for c in results]
    selected_comp = mo.ui.dropdown(options=comp_names, value=comp_names[0], label="Select Stage:")
    return df_matrix, results, selected_comp


@app.cell
def _(df_matrix, temp):
    temp.style_rf_matrix(df_matrix)
    return


@app.cell
def _(df_matrix, mo, results, selected_comp, temp):
    mo.vstack([
        temp.style_rf_matrix(df_matrix),
        selected_comp,
        temp.plot_spectrum(results, selected_comp.value),
    ])
    return


@app.cell
def _(
    amplifier_ox,
    balun,
    components,
    low_pass_ox,
    mo,
    ox_freq,
    ox_power,
    splitter,
):
    ox_signal = components.SpectrumSignal(tones={ox_freq.value: ox_power.value})

    ox_components = [
        balun,
        low_pass_ox,
        splitter,
        amplifier_ox
    ]

    osc_md, final_lo_signal = components.analyze_system("Oszillator Pfad", ox_signal, ox_components)
    lo_final_power = final_lo_signal.total_power_dbm()

    mixer_warning = ""
    if lo_final_power < 6.5 or lo_final_power > 10.0:
        mixer_warning = f"\n> <span style='color:orange;'>⚠️ **LO POWER WARNUNG:** Der RMS-30+ Mixer benötigt +7 dBm. Aktuell liefert der Pfad **{lo_final_power:.2f} dBm**.</span>\n"

    mo.md(osc_md)
    return


@app.cell
def _(components):

    bandpass = components.Filter("Bandpass", "2450BP", passband_min=2400.0, passband_max=2500.0, insertion_loss_db=-1.2, rejection_db=40.0),
    return (bandpass,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Transmitter Calculation
    """)
    return


@app.cell
def _(mo):
    tx_freq = mo.ui.slider(start=800.0, stop=1100.0, step=1.0, value=950.0, label="Tx DAC Freq (MHz)", show_value=True)
    tx_power = mo.ui.slider(start=-18.5, stop=6.5, step=0.5, value=6.5, label="Tx DAC Power (dBm)", show_value=True)

    mo.vstack([tx_freq, tx_power])
    return tx_freq, tx_power


@app.cell
def _(components, mixer, mo, tx_freq, tx_power):
    # Tx Spektrum (inklusive einer simulierten 2. Harmonischen des DACs bei -40 dBc)
    tx_start = components.SpectrumSignal({tx_freq.value: tx_power.value, (tx_freq.value * 2): (tx_power.value - 40.0)})

    tx_components = [
        mixer,
        components.Filter("Bandpass "," 2450BP", passband_min=2400.0, passband_max=2500.0, insertion_loss_db=-1.2, rejection_db=45.0),
        components.Amplifier("PA", "SE2576L-R", gain_db=28.0, voltage_v=3.3, current_typ_ma=450.0, current_max_ma=600.0, 
                  max_input_dbm=12.0, p1db_dbm=32.0, oip3_dbm=40.0)
    ]

    tx_md, _ = components.analyze_system("Transmitter Pfad (Tx)", tx_start, tx_components)
    mo.md(tx_md)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Reciever Calculation
    """)
    return


@app.cell
def _(mo):
    rx_f1 = mo.ui.slider(start=2400.0, stop=2500.0, step=1.0, value=2450.0, label="Rx Nutzsignal Freq (MHz)", show_value=True)
    rx_p1 = mo.ui.slider(start=-100.0, stop=0.0, step=1.0, value=-60.0, label="Rx Nutzsignal Power (dBm)", show_value=True)

    rx_f2 = mo.ui.slider(start=2400.0, stop=2500.0, step=1.0, value=2460.0, label="Rx Störsignal Freq (MHz)", show_value=True)
    rx_p2 = mo.ui.slider(start=-100.0, stop=0.0, step=1.0, value=-40.0, label="Rx Störsignal Power (dBm)", show_value=True)

    mo.vstack([rx_f1, rx_p1, rx_f2, rx_p2])
    return rx_f1, rx_f2, rx_p1, rx_p2


@app.cell
def _(bandpass, components, mixer, mo, rx_f1, rx_f2, rx_p1, rx_p2):
    rx_start = components.SpectrumSignal({rx_f1.value: rx_p1.value, rx_f2.value: rx_p2.value})

    rx_components = [
        bandpass,
        components.Amplifier("LNA", "HMC374", gain_db=9.0, voltage_v=5.0, current_typ_ma=90.0, current_max_ma=110.0, 
                  max_input_dbm=13.0, p1db_dbm=22.0, oip3_dbm=37.0),
       mixer,
        components.Filter("Bandpass ", "SYBP-92+", passband_min=800.0, passband_max=1000.0, insertion_loss_db=-2.24, rejection_db=40.0)
    ]

    rx_md, _ = components.analyze_system("Receiver Pfad (Rx)", rx_start, rx_components)
    mo.md(rx_md)
    return


if __name__ == "__main__":
    app.run()
