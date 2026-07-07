import marimo

__generated_with = "0.23.9"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    import models as md

    return md, mo


@app.cell
def _(mo):
    mo.md("""
    # RF Link Budget, Frequency and Power Analysis
    Calculates the link budget for a chain of RF components, including mixers, filters, and amplifiers. Frequency behavior is roughly modeled.

    Additionally, the total DC power draw is estimated.
    """)
    return


@app.cell
def _(md):
    mixer =  md.Mixer("Mixer ", "RMS-30+", conversion_loss_db=7.5)

    bandpass = md.Filter("Bandpass", "2450BP", loss_model=1.2, passband_min=2400.0, passband_max=2500.0, rejection_db=40.0)
    return bandpass, mixer


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
def _(md, mixer, mo, ox_freq, ox_power):
    mixer.lo_freq = ox_freq.value 
    mixer.lo_power = ox_power.value

    lpf_model = md.TableModel([
        [100.0, 0.07], [500.0, 0.21], [1000.0, 0.41], [1500.0, 0.62], 
        [1850.0, 0.86], [2000.0, 1.21], [2450.0, 32.51], [9000.0, 19.80]
    ])
    psa4_model = md.AmplifierModel(
        gain_data=[[0.05, 25.4], [0.5, 22.1], [1.0, 18.4], [2.0, 13.3], [3.0, 10.2], [4.0, 8.0]],
        oip3_data=[[0.05, 31.0], [0.5, 32.1], [1.0, 33.5], [2.0, 32.7], [3.0, 33.6], [4.0, 32.6]],
        p1db_data=[[0.05, 18.9], [0.5, 19.3], [1.0, 19.8], [2.0, 20.7], [3.0, 21.2], [4.0, 21.5]]
    )

    path = [
        md.PLLADF4351("PLL", "ADF4351", freq_mhz=ox_freq.value, output_power_dbm=ox_power.value),
        md.Filter("Balun", "XMB0220K1", loss_model=-5.0),
        md.Filter("Low Pass","LFCN-1800+", loss_model=lpf_model),
        md.Filter("Power Splitter", "PD0922J5050D2HF", loss_model=-3.71),
        md.Amplifier("Amp", "PSA4-5043+", psa4_model, voltage=5.0, current_typ_ma=58.0, current_max_ma=66.0),
        # mixer
    ]
    results_ox = md.run_simulation(path, md.SpectrumSignal())

    md.print_system_health(results_ox)

    df_matrix_ox = md.create_frequency_matrix(results_ox)


    comp_names_ox = [c["name"] for c in results_ox]
    selected_comp_ox = mo.ui.dropdown(options=comp_names_ox, value=comp_names_ox[0], label="Select Stage:")

    # if lo_final_power < 6.5 or lo_final_power > 10.0:
    #     mixer_warning = f"\n> <span style='color:orange;'>⚠️ **LO POWER WARNUNG:** Der RMS-30+ Mixer benötigt +7 dBm. Aktuell liefert der Pfad **{lo_final_power:.2f} dBm**.</span>\n"
    return df_matrix_ox, results_ox, selected_comp_ox


@app.cell
def _(df_matrix_ox, md, mo, results_ox, selected_comp_ox):
    mo.vstack([
        md.style_rf_matrix(df_matrix_ox),
        selected_comp_ox,
        md.plot_spectrum(results_ox, selected_comp_ox.value),
    ])
    return


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
def _(bandpass, md, mixer, mo, tx_freq, tx_power):
    tx_path = [ 
        md.RFSoC_SDR("Tx DAC", "RFSoC_SDR",freq_mhz=tx_freq.value,output_power_dbm=tx_power.value),
        mixer,
        bandpass,
        md.Amplifier("PA", "SE2576L-R", model=28.0, p1db_dbm=32.0, oip3_dbm=40.0, voltage=3.3, current_typ_ma=450)
    ]

    tx_results = md.run_simulation(tx_path, md.SpectrumSignal())

    md.print_system_health(tx_results)

    df_matrix_tx = md.create_frequency_matrix(tx_results)


    comp_names_tx = [c["name"] for c in tx_results]
    selected_comp_tx = mo.ui.dropdown(options=comp_names_tx, value=comp_names_tx[0], label="Select Stage:")
    return df_matrix_tx, selected_comp_tx, tx_results


@app.cell
def _(df_matrix_tx, md, mo, selected_comp_tx, tx_results):
    mo.vstack([
        md.style_rf_matrix(df_matrix_tx),
        selected_comp_tx,
        md.plot_spectrum(tx_results, selected_comp_tx.value),
    ])
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
def _(bandpass, md, mixer, mo, rx_f1, rx_f2, rx_p1, rx_p2):
    rx_input = md.AntennaSource("Antenna")
    rx_input.add_signal(rx_f1.value, rx_p1.value)    # Wanted signal at -90 dBm
    rx_input.add_signal(rx_f2.value, rx_p2.value)    # Strong interferer (blocker) at 2460 MHz
    rx_input.add_thermal_noise(bandwidth_mhz=20.0)


    path_rx = [
        rx_input,
        bandpass,
        md.Amplifier("LNA", "HMC374", model=9.0, voltage=5.0, current_typ_ma=90.0, current_max_ma=110.0, 
                  max_input_dbm=13.0, p1db_dbm=22.0, oip3_dbm=37.0),
       mixer,
        md.Filter("Bandpass ", "SYBP-92+", passband_min=800.0, passband_max=1000.0, loss_model=-2.24, rejection_db=40.0)
    ]

    results_rx = md.run_simulation(path_rx, md.SpectrumSignal())

    md.print_system_health(results_rx)

    df_matrix_rx = md.create_frequency_matrix(results_rx)


    comp_names_rx = [c["name"] for c in results_rx]
    selected_comp_rx = mo.ui.dropdown(options=comp_names_rx, value=comp_names_rx[0], label="Select Stage:")
    return df_matrix_rx, results_rx, selected_comp_rx


@app.cell
def _(df_matrix_rx, md, mo, results_rx, selected_comp_rx):
    mo.vstack([
        md.style_rf_matrix(df_matrix_rx),
        selected_comp_rx,
        md.plot_spectrum(results_rx, selected_comp_rx.value),
    ])
    return


if __name__ == "__main__":
    app.run()
