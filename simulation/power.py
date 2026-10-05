# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "jinja2==3.1.6",
#     "marimo>=0.23.3",
#     "matplotlib==3.11.1",
#     "numpy==2.5.2",
#     "pandas==3.0.5",
#     "plotly==7.0.0",
# ]
# ///

import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    import jinja2

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
    mixer = md.Mixer("Mixer", "RMS-30+", conversion_loss_db=7.5, lo_rf_iso_db=27.0, lo_if_iso_db=20.0, rf_if_iso_db=25.0, required_lo_power_dbm=7.0, max_lo_power_dbm=10.0, nf_model=8.0)
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
        [100e6, 0.07],
        [500e6, 0.21],
        [1e9, 0.41],
        [1.5e9, 0.62],
        [1.85e9, 0.86],
        [2e9, 1.21],
        [2.45e9, 32.51],
        [9e9, 19.80],
    ])
    psa4_gain = md.TableModel([
        [50e6, 25.4],
        [500e6, 22.1],
        [1e9, 18.4],
        [2e9, 13.3],
        [3e9, 10.2],
        [4e9, 8.0],
    ])
    psa4_op3 = md.TableModel([
        [50e6, 31.0],
        [500e6, 32.1],
        [1e9, 33.5],
        [2e9, 32.7],
        [3e9, 33.6],
        [4e9, 32.6],
    ])
    psda4_p1db = md.TableModel([
        [50e6, 18.9],
        [500e6, 19.3],
        [1e9, 19.8],
        [2e9, 20.7],
        [3e9, 21.2],
        [4e9, 21.5],
    ])
    pd09_model = md.TableModel([
        [500e6, 3.01 + 0.7],
        [1e9, 3.01 + 0.7],
        [1.6e9, 3.01 + 0.6],
        [2e9, 3.01 + 0.55],
        [2.2e9, 3.01 + 0.6],
        [2.6e9, 3.01 + 0.9],
        [3.5e9, 3.01 + 1.7],
        [4.5e9, 3.01 + 2.7],
        [5.5e9, 3.01 + 2.7],
        [6.5e9, 3.01 + 1.2],
        [7.5e9, 3.01 + 2.1],
        [8.5e9, 3.01 + 3.6],
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
        md.Amplifier("Amp", "PSA4-5043+", gain_model=psa4_gain, p1db_model=psda4_p1db, oip3_model=psa4_op3, nf_model=4.0, power_rail=md.PowerRail(5.0, 0.058, 0.066)),
    ]
    results_ox, diags_ox, _ = md.run_simulation(path_ox, md.SpectrumSignal())

    reports_mixer = mixer.set_lo_signal(
        results_ox.iloc[-1]["Signal"],
        lo_freq_hz=ox_freq_hz.value,
    )
    diags_mixer = {mixer.name: reports_mixer}
    all_diags_ox = {
            **diags_ox,
            **diags_mixer,
        }

    ui_stage_ox = mo.ui.dropdown(
        options=results_ox.index.tolist(), 
        value=results_ox.index[-1], 
        label="Select Oscillator Stage:"
    )
    return all_diags_ox, path_ox, results_ox, ui_stage_ox


@app.cell
def _(all_diags_ox, md, mo, results_ox, ui_stage_ox):
    mo.vstack([
        md.diagnostics_to_ui(all_diags_ox),
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
        md.Amplifier("PA", "SE2576L-R", gain_model=28.0, p1db_model=32.0, oip3_model=40.0, power_rail=md.PowerRail(voltage=5.0, current_typ=0.5, current_max=0.65), nf_model=None)
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
        md.diagnostics_to_ui(diags_tx),
        md.show_frequency_matrix(results_tx),
        ui_stage_tx,
        md.plot_spectrum(results_tx, ui_stage_tx.value),
    ])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Receiver Calculation

    Expected values for the receiver signal strength with maximum transmitter strength 25.5 dBm:
    - 1m distance: -15 dBm
    - 10m distance: -35 dBm
    - 100m distance: -55 dBm
    - 1km distance: -75 dBm
    """)
    return


@app.cell
def _(mo):
    rx_f1_hz = mo.ui.slider(start=2400e6, stop=2500e6, step=1e6, value=2450e6, label="Rx Nutzsignal Freq (Hz)", show_value=True)
    rx_p1 = mo.ui.slider(start=-100.0, stop=50.0, step=1.0, value=-55.0, label="Rx Nutzsignal Power (dBm)", show_value=True)

    rx_f2_hz = mo.ui.slider(start=2400e6, stop=2500e6, step=1e6, value=2470e6, label="Rx Störsignal Freq (Hz)", show_value=True)
    rx_p2 = mo.ui.slider(start=-100.0, stop=20.0, step=1.0, value=-30.0, label="Rx Störsignal Power (dBm)", show_value=True)

    rx_bw = mo.ui.slider(start=500e5, stop=500e6, step=100e5, value=100e6, label="Rx Bandbreite (Hz)", show_value=True)
    mo.vstack([rx_f1_hz, rx_p1, rx_f2_hz, rx_p2, rx_bw])
    return rx_bw, rx_f1_hz, rx_f2_hz, rx_p1, rx_p2


@app.cell
def _(bandpass, md, mixer, mo, rx_bw, rx_f1_hz, rx_f2_hz, rx_p1, rx_p2):
    rx_input = md.AntennaSource("Antenna", "ANT-001", bandwidth_hz=rx_bw.value, analysis_freq=rx_f1_hz.value)
    rx_input.add_signal(rx_f1_hz.value, rx_p1.value)    # Wanted signal at -90 dBm
    rx_input.add_signal(rx_f2_hz.value, rx_p2.value)    # Strong interferer (blocker) at 2460 MHz

    hmc_gain = md.TableModel([
        [500e6, 14.0],
        [1e9, 14.0],
        [1.5e9, 13.0],
        [2e9, 12.0],
        [2.5e9, 10.0],
        [3e9, 8.0],
        [3.5e9, 7.0],
        [4e9, 4.0],
    ])
    hmc_oip3 = md.TableModel([
        [300e6, 37.0],
        [1e9, 37.0],
        [2e9, 37.0],
        [3e9, 37.0],
    ])
    hmc_p1db = md.TableModel([
        [300e6, 22.0],
        [1e9, 22.0],
        [2e9, 22.0],
        [3e9, 22.0],
    ])

    sybp_model = md.TableModel([
        [1e6, 95.93],
        [10e6, 76.37],
        [50e6, 62.61],
        [100e6, 57.95],
        [150e6, 56.80],
        [200e6, 57.87],
        [250e6, 60.40],
        [300e6, 57.43],
        [350e6, 50.79],
        [400e6, 44.24],
        [450e6, 37.39],
        [500e6, 30.07],
        [510e6, 28.57],
        [520e6, 27.05],
        [530e6, 25.54],
        [540e6, 24.03],
        [550e6, 22.53],
        [600e6, 15.26],
        [650e6, 8.93],
        [700e6, 4.73],
        [750e6, 2.88],
        [800e6, 2.24],
        [810e6, 2.16],
        [820e6, 2.11],
        [830e6, 2.06],
        [840e6, 2.02],
        [850e6, 1.99],
        [860e6, 1.97],
        [870e6, 1.95],
        [880e6, 1.94],
        [890e6, 1.93],
        [900e6, 1.92],
        [910e6, 1.91],
        [920e6, 1.91],
        [930e6, 1.92],
        [940e6, 1.93],
        [950e6, 1.94],
        [960e6, 1.95],
        [970e6, 1.97],
        [980e6, 1.99],
        [990e6, 2.00],
        [1e9, 2.02],
        [1.05e9, 2.13],
        [1.1e9, 2.26],
        [1.15e9, 2.35],
        [1.2e9, 2.53],
        [1.25e9, 2.90],
        [1.3e9, 3.71],
        [1.35e9, 5.51],
        [1.4e9, 9.22],
        [1.45e9, 15.04],
        [1.5e9, 21.98],
        [1.55e9, 28.43],
        [1.6e9, 33.34],
        [1.7e9, 37.69],
        [1.8e9, 38.24],
        [1.85e9, 37.91],
        [1.9e9, 37.43],
        [1.95e9, 36.94],
        [2e9, 36.48],
        [2.1e9, 36.36],
        [2.2e9, 37.52],
        [2.3e9, 40.02],
        [2.4e9, 44.04],
        [2.5e9, 52.46],
        [2.6e9, 52.71],
        [2.7e9, 43.78],
        [2.8e9, 39.29],
        [2.9e9, 36.11],
        [3e9, 33.80],
    ])

    pga_gain = md.TableModel([
        [50e6, 26.5],
        [400e6, 22.1],
        [1e9, 16.2],
        [2e9, 11.0],
        [3e9, 8.1],
        [4e9, 6.2],
    ])
    pga_p1db = md.TableModel([
        [50e6, 20.0],
        [400e6, 21.5],
        [1e9, 22.5],
        [2e9, 22.5],
        [3e9, 22.9],
        [4e9, 23.2],
    ])
    pga_oip3 = md.TableModel([
        [50e6, 36.7],
        [400e6, 39.0],
        [1e9, 41.9],
        [2e9, 44.6],
        [3e9, 44.3],
        [4e9, 45.4],
    ])
    pga_nf = md.TableModel([
        [50e6, 0.5],
        [400e6, 0.5],
        [1e9, 0.6],
        [2e9, 0.9],
        [3e9, 1.2],
        [4e9, 1.5],
    ])


    # todo check hmc max ratings for:
    # RF Input Power (RFIN)(Vdd = +5.0 Vdc) 15 

    # todo: add check for ADC resolution.

    path_rx = [
        rx_input,
        bandpass,
        md.Amplifier("LNA", "HMC374", gain_model=hmc_gain, oip3_model=hmc_oip3, p1db_model=hmc_p1db, power_rail=md.PowerRail(voltage=5.0, current_typ=90e-3), max_input_power_dbm=13.0, nf_model=2.2),
        mixer,
        md.Filter("Bandpass Low ", "SYBP-92+", insertion_loss=sybp_model, center_freq_hz=950e6),
        md.Amplifier("Amplifier IF", "PGA-103+", gain_model=pga_gain, oip3_model=pga_oip3, p1db_model=pga_p1db, nf_model=pga_nf, freq_range=md.Range(0.05e9, 4e9) , power_rail=md.PowerRail(voltage=5.0, current_typ =0.097, current_max=0.12)),
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
        md.diagnostics_to_ui(diags_rx),
        md.show_frequency_matrix(results_rx),
        ui_stage_rx,
        md.plot_spectrum(results_rx, ui_stage_rx.value),
    ])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Noise Budget

    For now, we manually specify the frequency of the desired signal in the Antenna initialization. The Mixer will update the frequency by calculating ox_freq_hz.value and rx_f1_hz.value.
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
