import marimo

__generated_with = "0.23.9"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    import models as md

    # todo: max_input_power_dbm gloablly for all components
    return md, mo


@app.cell
def _(mo):
    mo.md("""
    # RF Link Budget, Noise Budget, Frequency and DC Power Analysis
    Calculates the link budget for a chain of RF components, including mixers, filters, and amplifiers. Frequency behavior is roughly modeled.

    Noise Budget is calculated for the Receiver Path as well.

    Additionally, the total DC power draw is estimated.
    """)
    return


@app.cell
def _(md):
    mixer = md.Mixer("Mixer", "RMS-30+", conversion_loss_db=7.5, lo_rf_iso_db=27.0, lo_if_iso_db=20.0, rf_if_iso_db=25.0, required_lo_power_dbm=7.0, max_lo_power_dbm=10.0, nf_db=8.0)
    bandpass = md.Filter("Bandpass", "2450BP", insertion_loss=1.2, freq_range=md.Range(2_400e6, 2_500e6), rejection_db=40)
    return bandpass, mixer


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Oscillator Analysis

    The resulting signal of this chain is fed to the mixer and used for the Transmitter and receiver modelling.
    """)
    return


@app.cell
def _(mo):
    ox_freq_hz = mo.ui.slider(start=35e6, stop=4400e6, step=10e6, value=1500e6, label="PLL Freq (Hz)", show_value=True)
    ox_power = mo.ui.slider(start=-4.0, stop=5.0, step=0.1, value=1.0, label="PLL Power (dBm)", show_value=True)

    mo.vstack([ox_freq_hz, ox_power])
    return ox_freq_hz, ox_power


@app.cell
def _(md, mixer, mo, ox_freq_hz, ox_power):
    lfcn_model = md.TableModel([
        [freq_hz * 1e6, loss_db]
        for freq_hz, loss_db in [
            [100.0, 0.07], [500.0, 0.21], [1000.0, 0.41], [1500.0, 0.62],
            [1850.0, 0.86], [2000.0, 1.21], [2450.0, 32.51], [9000.0, 19.80],
        ]
    ])
    psa4_gain = md.TableModel([[freq_hz * 1e6, get_gain] for freq_hz, get_gain in [[50, 25.4], [500, 22.1], [1000, 18.4], [2000, 13.3], [3000, 10.2], [4000, 8.0]]])
    psa4_op3 = md.TableModel([[freq_hz * 1e6, oip3_dbm] for freq_hz, oip3_dbm in [[50, 31.0], [500, 32.1], [1000, 33.5], [2000, 32.7], [3000, 33.6], [4000, 32.6]]])
    psda4_p1db = md.TableModel([[freq_hz * 1e6, p1db_dbm] for freq_hz, p1db_dbm in [[50, 18.9], [500, 19.3], [1000, 19.8], [2000, 20.7], [3000, 21.2], [4000, 21.5]]])
    pd09_model = md.TableModel([
        [freq_hz * 1e6, 3.01 + loss_db]
        for freq_hz, loss_db in [
            [500, 0.7], [1000, 0.7], [1600, 0.6], [2000, 0.55], [2200, 0.6], [2600, 0.9],
            [3500, 1.7], [4500, 2.7], [5500, 2.7], [6500, 1.2], [7500, 2.1], [8500, 3.6],
        ]
    ])

    path_ox = [
        md.Source(
            "PLL", "ADF4351",
            freq_hz=ox_freq_hz.value, output_power_dbm=ox_power.value, freq_range=md.Range(35e6, 4_400e6), power_range=md.Range(-4.0, 5.0),
            harmonics={2: -20.0, 3: -10.0},
            pfd_freq_hz=32e6, spur_level_dbc=80,
            power_rail=md.PowerRail(3.3, 125e-3, 179e-3)
        ),
        md.Filter("Balun", "XMB0220K1", insertion_loss=5.0),
        md.Filter("Low Pass", "LFCN-1800+", insertion_loss=lfcn_model),
        md.Filter("Power Splitter", "PD0922J5050D2HF", insertion_loss=pd09_model),
        md.Amplifier("Amp", "PSA4-5043+", gain_model=psa4_gain, p1db_model=psda4_p1db, oip3_model=psa4_op3, nf_db=4.0, power_rail=md.PowerRail(5.0, 0.058, 0.066)),
    ]
    results_ox, diags_ox, _ = md.run_simulation(path_ox, md.SpectrumSignal())

    mixer.set_lo_signal(
        results_ox.iloc[-1]["Signal"],
        lo_freq_hz=ox_freq_hz.value,
    )

    ui_stage_ox = mo.ui.dropdown(
        options=results_ox.index.tolist(), 
        value=results_ox.index[-1], 
        label="Select Oscillator Stage:"
    )
    return diags_ox, path_ox, results_ox, ui_stage_ox


@app.cell
def _(diags_ox, md, mo, results_ox, ui_stage_ox):
    mo.vstack([
        diags_ox,
        md.show_frequency_matrix(results_ox),
        ui_stage_ox,
        md.plot_spectrum(results_ox, ui_stage_ox.value),
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
    tx_freq_hz = mo.ui.slider(start=800e6, stop=1100e6, step=1e6, value=950e6, label="Tx DAC Freq (Hz)", show_value=True)
    tx_power = mo.ui.slider(start=-18.5, stop=6.5, step=0.5, value=6.5, label="Tx DAC Power (dBm)", show_value=True)
    tx_sample_freq_hz = mo.ui.slider(start=500e6, stop=7000e6, step=500e6, value=6000e6, label="Tx DAC Sample Freq (Hz)", show_value=True)

    mo.vstack([tx_freq_hz, tx_power, tx_sample_freq_hz])
    return tx_freq_hz, tx_power, tx_sample_freq_hz


@app.cell
def _(bandpass, md, mixer, mo, tx_freq_hz, tx_power, tx_sample_freq_hz):
    path_tx = [ 
        md.Source("Tx DAC", "RFSoC_SDR",freq_hz=tx_freq_hz.value,output_power_dbm=tx_power.value, fs_hz=tx_sample_freq_hz.value, power_range=md.Range(-18.5, 6.5), freq_range=md.Range(800e6, 1_100e6)),
        mixer,
        bandpass,
        md.Amplifier("PA", "SE2576L-R", gain_model=28.0, p1db_dbm=32.0, oip3_dbm=40.0, power_rail=md.PowerRail(voltage=5.0, current_typ=0.5, current_max=0.65))
    ]
    results_tx, diags_tx, _ = md.run_simulation(path_tx, md.SpectrumSignal())

    ui_stage_tx = mo.ui.dropdown(
        options=results_tx.index.tolist(), 
        value=results_tx.index[-1], 
        label="Select Transmitter Stage:"
    )
    return diags_tx, path_tx, results_tx, ui_stage_tx


@app.cell
def _(diags_tx, md, mo, results_tx, ui_stage_tx):
    mo.vstack([
        diags_tx,
        md.show_frequency_matrix(results_tx),
        ui_stage_tx,
        md.plot_spectrum(results_tx, ui_stage_tx.value),
    ])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Receiver Calculation
    """)
    return


@app.cell
def _(mo):
    rx_f1_hz = mo.ui.slider(start=2400e6, stop=2500e6, step=1e6, value=2450e6, label="Rx Nutzsignal Freq (Hz)", show_value=True)
    rx_p1 = mo.ui.slider(start=-100.0, stop=0.0, step=1.0, value=-10.0, label="Rx Nutzsignal Power (dBm)", show_value=True)

    rx_f2_hz = mo.ui.slider(start=2400e6, stop=2500e6, step=1e6, value=2460e6, label="Rx Störsignal Freq (Hz)", show_value=True)
    rx_p2 = mo.ui.slider(start=-100.0, stop=0.0, step=1.0, value=-40.0, label="Rx Störsignal Power (dBm)", show_value=True)

    mo.vstack([rx_f1_hz, rx_p1, rx_f2_hz, rx_p2])
    return rx_f1_hz, rx_f2_hz, rx_p1, rx_p2


@app.cell
def _(rx_f1_hz):
    rx_f1_hz.value
    return


@app.cell
def _(bandpass, md, mixer, mo, rx_f1_hz, rx_f2_hz, rx_p1, rx_p2):
    rx_input = md.AntennaSource("Antenna", "ANT-001", bandwidth_hz=500e6, analysis_freq=rx_f1_hz.value)
    rx_input.add_signal(rx_f1_hz.value, rx_p1.value)    # Wanted signal at -90 dBm
    rx_input.add_signal(rx_f2_hz.value, rx_p2.value)    # Strong interferer (blocker) at 2460 MHz

    hmc_gain = md.TableModel([[freq_hz * 1e6, get_gain] for freq_hz, get_gain in [[500, 14.0], [1000, 14.0], [1500, 13.0], [2000, 12.0], [2500, 10.0], [3000, 8.0], [3500, 7.0], [4000, 4.0]]])
    hmc_oip3 = md.TableModel([[freq_hz * 1e6, oip3_dbm] for freq_hz, oip3_dbm in [[300, 37.0], [1000, 37.0], [2000, 37.0], [3000, 37.0]]])
    hmc_p1db = md.TableModel([[freq_hz * 1e6, p1db_dbm] for freq_hz, p1db_dbm in [[300, 22.0], [1000, 22.0], [2000, 22.0], [3000, 22.0]]])

    sybp_model = md.TableModel([
        [freq_hz * 1e6, loss_db]
        for freq_hz, loss_db in [
            [1.0, 95.93], [10.0, 76.37], [50.0, 62.61], [100.0, 57.95], [150.0, 56.80], [200.0, 57.87], [250.0, 60.40], [300.0, 57.43], [350.0, 50.79], [400.0, 44.24],
            [450.0, 37.39], [500.0, 30.07], [510.0, 28.57], [520.0, 27.05], [530.0, 25.54], [540.0, 24.03], [550.0, 22.53], [600.0, 15.26], [650.0, 8.93], [700.0, 4.73], [750.0, 2.88], [800.0, 2.24], [810.0, 2.16], [820.0, 2.11], [830.0, 2.06], [840.0, 2.02], [850.0, 1.99], [860.0, 1.97], [870.0, 1.95], [880.0, 1.94], [890.0, 1.93], [900.0, 1.92], [910.0, 1.91], [920.0, 1.91], [930.0, 1.92], [940.0, 1.93], [950.0, 1.94], [960.0, 1.95], [970.0, 1.97], [980.0, 1.99], [990.0, 2.00], [1000.0, 2.02], [1050.0, 2.13], [1100.0, 2.26], [1150.0, 2.35], [1200.0, 2.53], [1250.0, 2.90], [1300.0, 3.71], [1350.0, 5.51], [1400.0, 9.22], [1450.0, 15.04], [1500.0, 21.98], [1550.0, 28.43], [1600.0, 33.34], [1700.0, 37.69], [1800.0, 38.24], [1850.0, 37.91], [1900.0, 37.43], [1950.0, 36.94], [2000.0, 36.48], [2100.0, 36.36], [2200.0, 37.52], [2300.0, 40.02], [2400.0, 44.04], [2500.0, 52.46], [2600.0, 52.71], [2700.0, 43.78], [2800.0, 39.29], [2900.0, 36.11], [3000.0, 33.80],
        ]
    ])

    # todo check hmc max ratings for:
    # RF Input Power (RFIN)(Vdd = +5.0 Vdc) 15 

    path_rx = [
        rx_input,
        bandpass,
        md.Amplifier("LNA", "HMC374", gain_model=hmc_gain, oip3_model=hmc_oip3, p1db_model=hmc_p1db, power_rail=md.PowerRail(voltage=5.0, current_typ=90e-3), max_input_power_dbm=13.0, nf_db=2.2),
        mixer,
        md.Filter("Bandpass Low ", "SYBP-92+", insertion_loss=sybp_model, center_freq_hz=950e6),
        md.Limiter(
            name="Limiter",
            part_number="SKY16602-632LF",
            insertion_loss_db=0.3,           # Typical small-signal IL at 2 GHz
            limiting_threshold_dbm=6.0,     # Typical P1dB limiting threshold
            flat_leakage_dbm=6.0,           # Maximum clamped output power
            max_input_power_dbm=md._mw_to_dbm(12e3),
            freq_range=(200e6, 4e9)
        ),
        md.ADC(name="ADC", part_number="RFSoC ADC", sample_rate_hz=5_000e6, bandwidth_hz=6_000e6, resolution_bits=14, full_scale_dbm=1.0, max_input_power_dbm=14.6)
    ]
    results_rx, diags_rx, noise_powers_rx = md.run_simulation(path_rx, md.SpectrumSignal(), analysis_freq=rx_f1_hz.value)


    ui_stage_rx = mo.ui.dropdown(
        options=results_rx.index.tolist(), 
        value=results_rx.index[-1], 
        label="Select Receiver Stage:"
    )
    return diags_rx, noise_powers_rx, path_rx, results_rx, ui_stage_rx


@app.cell
def _(diags_rx, md, mo, results_rx, ui_stage_rx):
    mo.vstack([
        diags_rx,
        md.show_frequency_matrix(results_rx),
        ui_stage_rx,
        md.plot_spectrum(results_rx, ui_stage_rx.value),
    ])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Noise Budget

    For now, we manually specify the frequency of the desired signal in the Antenna initialization.
    """)
    return


@app.cell
def _(md, mo, noise_powers_rx, rx_f1_hz):
    noise_budget_rx = md.build_noise_budget(noise_powers_rx, analysis_freq=rx_f1_hz.value)

    mo.vstack([
        noise_budget_rx,
        md.plot_noise_budget(noise_budget_rx.data),
    ])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## DC Power Result
    The LDO for 5V to 3.3V conversion is not modeled. The current draw for the 5V rail is therefore only for its components, not the total expected current!

    You can add both Power values to get the total DC power draw for the system.
    """)
    return


@app.cell
def _(md, mo, path_ox, path_rx, path_tx):
    tcxo = md.RFComponent(name="TCXO", part_number="ATX-11-F-26.000MHZ-F05-T", power_rail=md.PowerRail(voltage=3.3, current_typ=2e-3, current_max=2.5e-3))
    path_additional = [tcxo]

    mo.vstack([
        md.calculate_dc_power(path_ox + path_tx + path_rx + path_additional),
    ])
    return


if __name__ == "__main__":
    app.run()
