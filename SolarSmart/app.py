from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from solarsmart.energy import simulate_year, summarize_energy
from solarsmart.economics import run_financial_scenarios, scan_pv_sizes


st.set_page_config(
    page_title="SolarSmart | Solar PV Planner",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.4rem; padding-bottom: 2.5rem; max-width: 1500px;}
      .hero {padding: 1.35rem 1.5rem; border: 1px solid rgba(120,130,145,.22); border-radius: 18px;
              background: linear-gradient(115deg, rgba(245,183,55,.13), rgba(35,150,125,.07)); margin-bottom: 1rem;}
      .hero h1 {margin: 0 0 .2rem 0; font-size: 2.1rem;}
      .hero p {margin: 0; opacity: .78;}
      .small-note {font-size: .82rem; opacity: .72;}
      div[data-testid="stMetric"] {border: 1px solid rgba(120,130,145,.18); padding: .8rem .9rem; border-radius: 12px;}
      .section-note {padding: .7rem .9rem; border-left: 3px solid #d6a63b; background: rgba(214,166,59,.08); border-radius: 5px;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h1>☀️ SolarSmart</h1>
      <p>Solar PV Planning, Simulation & Investment Analysis</p>
      <p class="small-note">Rencanakan PLTS, simulasikan energi, analisis jaringan dengan pandapower, dan evaluasi kelayakan investasi.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.sidebar.title("Parameter proyek")
st.sidebar.caption("Ubah asumsi sesuai kondisi bangunan dan penawaran pemasang.")

with st.sidebar:
    st.subheader("1. Kebutuhan energi")
    profile_name = st.selectbox("Jenis profil pengguna", ["Rumah tangga", "UMKM / toko", "Kantor"])
    daily_consumption = st.number_input(
        "Konsumsi listrik rata-rata (kWh/hari)", min_value=0.1, max_value=10000.0,
        value=10.0, step=0.5, help="Bisa dihitung dari kWh pada tagihan bulanan dibagi jumlah hari.",
    )
    peak_load_kw = st.number_input(
        "Perkiraan beban puncak (kW)", min_value=0.1, max_value=100000.0,
        value=4.0, step=0.5, help="Digunakan untuk model jaringan pandapower, bukan untuk menghitung konsumsi tahunan.",
    )
    daytime_load_fraction = st.slider(
        "Beban siang dibanding beban puncak", min_value=0.10, max_value=1.00,
        value=0.45, step=0.05,
        help="Contoh 0,45 berarti beban siang diasumsikan 45% dari beban puncak.",
    )

    st.subheader("2. Rencana PLTS")
    roof_area = st.number_input("Luas atap efektif (m²)", min_value=1.0, max_value=100000.0, value=25.0, step=1.0)
    pv_capacity = st.number_input("Kapasitas panel surya (kWp)", min_value=0.0, max_value=10000.0, value=3.0, step=0.5)
    battery_capacity = st.number_input("Kapasitas baterai nominal (kWh)", min_value=0.0, max_value=100000.0, value=5.0, step=0.5)
    specific_yield = st.number_input(
        "Produksi spesifik surya (kWh/kWp/hari)", min_value=0.1, max_value=8.0,
        value=3.8, step=0.1,
        help="Nilai asumsi rata-rata harian di sisi AC setelah rugi sistem. Sesuaikan dengan lokasi, orientasi, kemiringan, bayangan, dan data cuaca.",
    )
    battery_dod = st.slider("Depth of Discharge baterai (%)", 10, 100, 80, 5) / 100.0
    battery_efficiency = st.slider("Efisiensi round-trip baterai (%)", 50, 100, 90, 1) / 100.0
    battery_c_rate = st.number_input("Daya charge/discharge baterai (C-rate)", min_value=0.05, max_value=2.0, value=0.50, step=0.05)

    st.subheader("3. Tarif dan kebijakan ekspor")
    tariff = st.number_input(
        "Tarif energi listrik (Rp/kWh)", min_value=0.0, max_value=100000.0,
        value=1444.70, step=10.0,
        help="Nilai awal mengacu pada tarif rumah tangga 1.300–2.200 VA; ubah sesuai golongan tarif aktual.",
    )
    export_credit = st.number_input(
        "Kredit energi ekspor (Rp/kWh)", min_value=0.0, max_value=100000.0,
        value=0.0, step=10.0,
        help="Default 0 untuk skema PLTS atap baru yang mengikuti Permen ESDM No. 2 Tahun 2024. Ubah hanya jika skema kontrak Anda memang memberi kredit ekspor.",
    )

    with st.expander("Asumsi harga komponen", expanded=True):
        st.caption("Seluruh angka berikut adalah nilai awal ilustratif, bukan harga pasar terverifikasi atau penawaran vendor.")
        pv_module_cost = st.number_input("Modul PV (Rp/kWp)", min_value=0, value=5_000_000, step=250_000)
        inverter_cost = st.number_input("Inverter (Rp/kW)", min_value=0, value=2_500_000, step=250_000)
        bos_cost = st.number_input("Balance of System (Rp/kWp)", min_value=0, value=2_000_000, step=250_000)
        installation_cost = st.number_input("Instalasi (Rp/kWp)", min_value=0, value=1_500_000, step=250_000)
        battery_cost = st.number_input("Baterai (Rp/kWh)", min_value=0, value=5_000_000, step=250_000)
        fixed_soft_cost = st.number_input("Survei/desain/biaya tetap (Rp)", min_value=0, value=1_500_000, step=250_000)

    with st.expander("Asumsi proyeksi keuangan", expanded=False):
        analysis_years = st.slider("Periode analisis (tahun)", min_value=5, max_value=30, value=25)
        annual_degradation = st.number_input("Degradasi PV (%/tahun)", min_value=0.0, max_value=3.0, value=0.50, step=0.05)
        tariff_escalation = st.number_input("Eskalasi tarif (%/tahun)", min_value=-10.0, max_value=20.0, value=3.0, step=0.5)
        annual_om = st.number_input("O&M (% CAPEX/tahun)", min_value=0.0, max_value=10.0, value=1.0, step=0.25)
        discount_rate = st.number_input("Discount rate (%/tahun)", min_value=0.0, max_value=30.0, value=8.0, step=0.5)
        battery_replacement_year = st.number_input("Tahun penggantian baterai (0 = tidak dihitung)", min_value=0, max_value=30, value=10, step=1)
        battery_replacement_fraction = st.slider("Biaya penggantian baterai (% harga awal)", 0, 150, 80, 5) / 100.0
        inverter_replacement_year = st.number_input("Tahun penggantian inverter (0 = tidak dihitung)", min_value=0, max_value=30, value=12, step=1)
        inverter_replacement_fraction = st.slider("Biaya penggantian inverter (% harga awal)", 0, 150, 30, 5) / 100.0

cost_inputs = {
    "pv_module_cost_per_kwp": float(pv_module_cost),
    "inverter_cost_per_kw": float(inverter_cost),
    "bos_cost_per_kwp": float(bos_cost),
    "installation_cost_per_kwp": float(installation_cost),
    "battery_cost_per_kwh": float(battery_cost),
    "fixed_soft_cost": float(fixed_soft_cost),
}
finance_inputs = {
    "analysis_years": int(analysis_years),
    "annual_pv_degradation_pct": float(annual_degradation),
    "tariff_escalation_pct": float(tariff_escalation),
    "annual_om_pct_of_capex": float(annual_om),
    "discount_rate_pct": float(discount_rate),
    "battery_replacement_year": int(battery_replacement_year),
    "battery_replacement_fraction": float(battery_replacement_fraction),
    "inverter_replacement_year": int(inverter_replacement_year),
    "inverter_replacement_fraction": float(inverter_replacement_fraction),
}

with st.spinner("Menghitung produksi energi, penggunaan baterai, dan proyeksi investasi..."):
    results = run_financial_scenarios(
        daily_consumption_kwh=float(daily_consumption),
        pv_capacity_kwp=float(pv_capacity),
        specific_yield_kwh_kwp_day=float(specific_yield),
        profile_name=profile_name,
        battery_capacity_kwh=float(battery_capacity),
        battery_dod=float(battery_dod),
        battery_roundtrip_efficiency=float(battery_efficiency),
        battery_c_rate=float(battery_c_rate),
        tariff_rp_kwh=float(tariff),
        export_credit_rp_kwh=float(export_credit),
        cost_inputs=cost_inputs,
        finance_inputs=finance_inputs,
    )

pv_result = results["pv_only"]
hybrid_result = results["hybrid"]
hybrid_df = hybrid_result["df"]
pv_df = pv_result["df"]
hybrid_metrics = summarize_energy(hybrid_df)
pv_metrics = summarize_energy(pv_df)
hybrid_fin = hybrid_result["finance"]
pv_fin = pv_result["finance"]

roof_capacity = roof_area / 5.5  # indicative roof area per kWp
if pv_capacity > roof_capacity:
    st.warning(
        f"Kapasitas PLTS ({pv_capacity:.1f} kWp) lebih besar daripada estimasi kapasitas atap ({roof_capacity:.1f} kWp). "
        "Periksa kembali luas efektif, modul yang dipilih, akses pemeliharaan, dan area bayangan."
    )
if pv_capacity == 0:
    st.info("Masukkan kapasitas PLTS lebih dari 0 kWp untuk melihat analisis pembangkit surya.")

# Tabs -----------------------------------------------------------------------
tab_overview, tab_energy, tab_finance, tab_grid, tab_guide = st.tabs(
    ["🏠 Ringkasan", "⚡ Simulasi Energi", "💰 Analisis Ekonomi", "🔌 Analisis Jaringan", "📘 Panduan"]
)

with tab_overview:
    st.subheader("Ringkasan hasil perencanaan")
    st.caption("Hasil dihitung dari asumsi yang Anda masukkan. Perbarui parameter agar sesuai dengan kondisi bangunan.")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Produksi PLTS / tahun", f"{hybrid_metrics['pv_kwh']:,.0f} kWh")
    col2.metric("Energi dari jaringan", f"{hybrid_metrics['grid_import_kwh']:,.0f} kWh", delta=f"{hybrid_metrics['self_sufficiency_pct']:.1f}% dipenuhi lokal")
    col3.metric("Penghematan bruto tahun 1", f"Rp{hybrid_fin['year1_gross_savings']:,.0f}")
    pb = hybrid_fin["simple_payback_years"]
    col4.metric("Simple payback", f"{pb:.1f} tahun" if pb is not None else "Belum tercapai")

    col_a, col_b = st.columns([1.1, 1])
    with col_a:
        st.markdown("#### Perbandingan sistem")
        comparison = pd.DataFrame([
            {
                "Konfigurasi": "PLTS tanpa baterai",
                "CAPEX (Rp)": pv_fin["capex"],
                "Impor PLN (kWh/tahun)": pv_metrics["grid_import_kwh"],
                "Penghematan bruto (Rp/tahun)": pv_fin["year1_gross_savings"],
                "Payback (tahun)": pv_fin["simple_payback_years"],
                "NPV (Rp)": pv_fin["npv"],
            },
            {
                "Konfigurasi": "PLTS + baterai",
                "CAPEX (Rp)": hybrid_fin["capex"],
                "Impor PLN (kWh/tahun)": hybrid_metrics["grid_import_kwh"],
                "Penghematan bruto (Rp/tahun)": hybrid_fin["year1_gross_savings"],
                "Payback (tahun)": hybrid_fin["simple_payback_years"],
                "NPV (Rp)": hybrid_fin["npv"],
            },
        ])
        st.dataframe(
            comparison.style.format({
                "CAPEX (Rp)": "Rp{:,.0f}",
                "Impor PLN (kWh/tahun)": "{:,.0f}",
                "Penghematan bruto (Rp/tahun)": "Rp{:,.0f}",
                "Payback (tahun)": "{:.1f}",
                "NPV (Rp)": "Rp{:,.0f}",
            }), use_container_width=True, hide_index=True,
        )
    with col_b:
        st.markdown("#### Kemandirian energi")
        fig = go.Figure(go.Indicator(
            mode="gauge+number", value=hybrid_metrics["self_sufficiency_pct"],
            number={"suffix": "%"},
            title={"text": "Kebutuhan beban dipenuhi PLTS/baterai"},
            gauge={"axis": {"range": [0, 100]}, "bar": {"thickness": 0.25},
                   "steps": [{"range": [0, 40]}, {"range": [40, 70]}, {"range": [70, 100]}]},
        ))
        fig.update_layout(height=280, margin=dict(l=25, r=25, t=65, b=15))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Aliran energi tahunan – konfigurasi PLTS + baterai")
    energy_bars = pd.DataFrame({
        "Kategori": ["Konsumsi beban", "Produksi PV", "Impor jaringan", "Ekspor jaringan", "Energi PV/baterai ke beban"],
        "Energi (kWh)": [
            hybrid_metrics["load_kwh"], hybrid_metrics["pv_kwh"],
            hybrid_metrics["grid_import_kwh"], hybrid_metrics["grid_export_kwh"],
            hybrid_metrics["solar_to_load_kwh"],
        ],
    })
    fig_energy = px.bar(energy_bars, x="Kategori", y="Energi (kWh)", text_auto=".0f")
    fig_energy.update_layout(height=330, margin=dict(l=15, r=15, t=25, b=15), yaxis_title="kWh/tahun")
    st.plotly_chart(fig_energy, use_container_width=True)

    st.markdown(
        '<div class="section-note"><b>Catatan keputusan:</b> Sistem dengan kapasitas terbesar tidak selalu paling ekonomis. '
        'Bandingkan penghematan energi yang benar-benar digunakan di lokasi, biaya baterai, dan arus kas sepanjang umur proyek.</div>',
        unsafe_allow_html=True,
    )

with tab_energy:
    st.subheader("Simulasi produksi dan konsumsi energi")
    st.markdown("#### Profil energi rata-rata per jam")
    hourly = hybrid_df.groupby(hybrid_df.index.hour).mean(numeric_only=True)
    fig_hour = go.Figure()
    fig_hour.add_trace(go.Scatter(x=hourly.index, y=hourly["load_kwh"], name="Beban", mode="lines+markers"))
    fig_hour.add_trace(go.Scatter(x=hourly.index, y=hourly["pv_kwh"], name="Produksi PV", mode="lines+markers"))
    fig_hour.add_trace(go.Scatter(x=hourly.index, y=hourly["grid_import_kwh"], name="Impor jaringan", mode="lines"))
    fig_hour.add_trace(go.Scatter(x=hourly.index, y=hourly["grid_export_kwh"], name="Ekspor jaringan", mode="lines"))
    fig_hour.add_trace(go.Scatter(x=hourly.index, y=hourly["battery_discharge_to_load_kwh"], name="Baterai ke beban", mode="lines"))
    fig_hour.update_layout(height=400, xaxis_title="Jam", yaxis_title="Energi per jam (kWh)", hovermode="x unified")
    st.plotly_chart(fig_hour, use_container_width=True)

    st.markdown("#### Ringkasan bulanan")
    monthly = hybrid_df.resample("MS").sum(numeric_only=True)
    monthly.index = monthly.index.strftime("%b")
    fig_month = go.Figure()
    fig_month.add_bar(x=monthly.index, y=monthly["load_kwh"], name="Konsumsi")
    fig_month.add_bar(x=monthly.index, y=monthly["pv_kwh"], name="Produksi PV")
    fig_month.add_bar(x=monthly.index, y=monthly["grid_import_kwh"], name="Impor PLN")
    fig_month.update_layout(barmode="group", height=370, yaxis_title="Energi (kWh)")
    st.plotly_chart(fig_month, use_container_width=True)

    st.markdown("#### Perbandingan tanpa baterai dan dengan baterai")
    rows = []
    for title, metrics in [("PLTS tanpa baterai", pv_metrics), ("PLTS + baterai", hybrid_metrics)]:
        rows.append({
            "Skenario": title,
            "Konsumsi (kWh)": metrics["load_kwh"],
            "Produksi PV (kWh)": metrics["pv_kwh"],
            "Impor PLN (kWh)": metrics["grid_import_kwh"],
            "Ekspor (kWh)": metrics["grid_export_kwh"],
            "Solar self-consumption (%)": metrics["self_consumption_pct"],
            "Self-sufficiency (%)": metrics["self_sufficiency_pct"],
        })
    st.dataframe(pd.DataFrame(rows).style.format({c: "{:,.1f}" for c in rows[0] if c != "Skenario"}), use_container_width=True, hide_index=True)

    csv_data = hybrid_df.to_csv().encode("utf-8")
    st.download_button("Unduh simulasi energi per jam (CSV)", data=csv_data,
                       file_name="solarsmart_simulasi_energi_per_jam.csv", mime="text/csv")
    st.caption("Model menggunakan profil beban dan kurva matahari representatif. Untuk studi rinci, gunakan data beban per jam dan data iradiasi lokal.")

with tab_finance:
    st.subheader("Analisis biaya dan kelayakan investasi")
    st.caption("Biaya komponen di sidebar dapat diganti dengan penawaran vendor. Angka awal bukan harga pasar terverifikasi.")
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("CAPEX PLTS + baterai", f"Rp{hybrid_fin['capex']:,.0f}")
    f2.metric("Penghematan bersih tahun 1", f"Rp{hybrid_fin['year1_net_savings']:,.0f}")
    f3.metric("NPV", f"Rp{hybrid_fin['npv']:,.0f}")
    irr_value = hybrid_fin["irr"]
    f4.metric("IRR", f"{irr_value * 100:.1f}%" if irr_value is not None else "Tidak terdefinisi")

    if hybrid_fin["npv"] > 0:
        st.success("NPV positif pada discount rate yang dipilih. Berdasarkan asumsi model, proyek menghasilkan nilai kini bersih positif.")
    else:
        st.warning("NPV nol atau negatif pada discount rate yang dipilih. Tinjau harga sistem, kapasitas, pola konsumsi, dan asumsi tarif.")

    ca, cb = st.columns([1, 1])
    with ca:
        st.markdown("#### Rincian estimasi investasi")
        cost_df = pd.DataFrame({"Komponen": list(hybrid_result["capex_items"].keys()), "Estimasi biaya (Rp)": list(hybrid_result["capex_items"].values())})
        st.dataframe(cost_df.style.format({"Estimasi biaya (Rp)": "Rp{:,.0f}"}), use_container_width=True, hide_index=True)
        fig_cost = px.pie(cost_df[cost_df["Komponen"] != "Total investasi"], values="Estimasi biaya (Rp)", names="Komponen", hole=0.45)
        fig_cost.update_layout(height=330, margin=dict(l=10, r=10, t=25, b=10))
        st.plotly_chart(fig_cost, use_container_width=True)
    with cb:
        st.markdown("#### Indikator pengembalian investasi")
        p1, p2 = st.columns(2)
        p1.metric("Simple payback", f"{hybrid_fin['simple_payback_years']:.1f} tahun" if hybrid_fin["simple_payback_years"] is not None else "Tidak tercapai")
        p2.metric("Discounted payback", f"{hybrid_fin['discounted_payback_years']:.1f} tahun" if hybrid_fin["discounted_payback_years"] is not None else "Tidak tercapai")
        p3, p4 = st.columns(2)
        p3.metric("ROI kumulatif", f"{hybrid_fin['roi_pct']:.1f}%" if hybrid_fin["roi_pct"] is not None else "—")
        p4.metric("Akumulasi kas akhir", f"Rp{hybrid_fin['cumulative_net_cash_after_capex']:,.0f}")
        st.markdown("#### Proyeksi arus kas")
        projection = pd.DataFrame(hybrid_fin["projection"])
        if not projection.empty:
            fig_cash = go.Figure()
            fig_cash.add_trace(go.Bar(x=projection["Tahun"], y=projection["Arus kas bersih (Rp)"], name="Arus kas bersih"))
            fig_cash.add_trace(go.Scatter(x=projection["Tahun"], y=projection["Akumulasi arus kas (Rp)"], name="Akumulasi setelah CAPEX", yaxis="y2", mode="lines+markers"))
            fig_cash.update_layout(height=390, yaxis_title="Arus kas tahunan (Rp)", yaxis2=dict(title="Akumulasi arus kas (Rp)", overlaying="y", side="right"), legend=dict(orientation="h", y=1.12))
            st.plotly_chart(fig_cash, use_container_width=True)

    st.markdown("#### Rekomendasi kapasitas PV otomatis")
    st.caption("Aplikasi membandingkan beberapa ukuran PV yang diperkirakan muat di atap. Kapasitas baterai mengikuti nilai yang sedang dipilih di sidebar.")
    if st.button("Cari ukuran PV paling layak", type="secondary"):
        with st.spinner("Membandingkan alternatif kapasitas PV..."):
            size_table = scan_pv_sizes(
                daily_consumption_kwh=float(daily_consumption),
                profile_name=profile_name,
                roof_area_m2=float(roof_area),
                specific_yield_kwh_kwp_day=float(specific_yield),
                battery_capacity_kwh=float(battery_capacity),
                battery_dod=float(battery_dod),
                battery_roundtrip_efficiency=float(battery_efficiency),
                battery_c_rate=float(battery_c_rate),
                tariff_rp_kwh=float(tariff),
                export_credit_rp_kwh=float(export_credit),
                cost_inputs=cost_inputs,
                finance_inputs=finance_inputs,
                current_pv_kwp=float(pv_capacity),
            )
            st.session_state["pv_size_scan"] = size_table
    if "pv_size_scan" in st.session_state:
        size_table = st.session_state["pv_size_scan"]
        best = size_table.loc[size_table["NPV (Rp)"].idxmax()]
        st.metric("Alternatif dengan NPV tertinggi", f"{best['Kapasitas PV (kWp)']:.2f} kWp", delta=f"NPV Rp{best['NPV (Rp)']:,.0f}")
        st.dataframe(size_table.style.format({
            "Kapasitas PV (kWp)": "{:.2f}",
            "Kapasitas baterai (kWh)": "{:.1f}",
            "CAPEX (Rp)": "Rp{:,.0f}",
            "Impor PLN (kWh/tahun)": "{:,.0f}",
            "Self-sufficiency (%)": "{:.1f}%",
            "Penghematan bruto tahun 1 (Rp)": "Rp{:,.0f}",
            "Payback (tahun)": "{:.1f}",
            "NPV (Rp)": "Rp{:,.0f}",
            "IRR (%)": "{:.1f}%",
        }), use_container_width=True, hide_index=True)
        st.caption("Rekomendasi dipilih berdasarkan NPV tertinggi dalam rentang kandidat. Jika seluruh NPV negatif, alternatif terbaik tetap belum tentu layak; evaluasi hasil dan asumsi sebelum mengambil keputusan.")

    st.markdown("#### Perbandingan kelayakan: PV saja vs PV + baterai")
    comparison_fin = pd.DataFrame([
        {"Skenario": "PV saja", "CAPEX (Rp)": pv_fin["capex"], "Penghematan tahun 1 (Rp)": pv_fin["year1_gross_savings"],
         "Payback (tahun)": pv_fin["simple_payback_years"], "NPV (Rp)": pv_fin["npv"], "IRR (%)": pv_fin["irr"] * 100 if pv_fin["irr"] is not None else np.nan},
        {"Skenario": "PV + baterai", "CAPEX (Rp)": hybrid_fin["capex"], "Penghematan tahun 1 (Rp)": hybrid_fin["year1_gross_savings"],
         "Payback (tahun)": hybrid_fin["simple_payback_years"], "NPV (Rp)": hybrid_fin["npv"], "IRR (%)": hybrid_fin["irr"] * 100 if hybrid_fin["irr"] is not None else np.nan},
    ])
    st.dataframe(comparison_fin.style.format({
        "CAPEX (Rp)": "Rp{:,.0f}", "Penghematan tahun 1 (Rp)": "Rp{:,.0f}",
        "Payback (tahun)": "{:.1f}", "NPV (Rp)": "Rp{:,.0f}", "IRR (%)": "{:.1f}%",
    }), use_container_width=True, hide_index=True)
    st.download_button("Unduh proyeksi keuangan (CSV)", data=projection.to_csv(index=False).encode("utf-8"),
                       file_name="solarsmart_proyeksi_keuangan.csv", mime="text/csv")

    st.info("Proyeksi masa depan menggunakan degradasi PV, eskalasi tarif, O&M, dan penggantian komponen sesuai asumsi. Dispatch energi tidak dihitung ulang satu per satu untuk setiap tahun proyeksi; hasil ini adalah estimasi kelayakan awal, bukan jaminan keuntungan.")

with tab_grid:
    st.subheader("Analisis dampak PLTS terhadap jaringan listrik")
    st.markdown(
        "Model ini memakai jaringan contoh radial **20 kV / 0,4 kV** dengan satu transformator, satu saluran tegangan rendah, dan satu pelanggan. "
        "Ubah parameternya agar mendekati data jaringan yang ingin dipelajari."
    )
    with st.expander("Parameter jaringan pandapower", expanded=True):
        g1, g2, g3 = st.columns(3)
        with g1:
            transformer_kva = st.number_input("Kapasitas trafo (kVA)", min_value=25.0, max_value=5000.0, value=250.0, step=25.0)
            transformer_vk = st.number_input("Impedansi trafo Vk (%)", min_value=1.0, max_value=15.0, value=4.0, step=0.1)
        with g2:
            feeder_length = st.number_input("Panjang saluran LV (km)", min_value=0.001, max_value=10.0, value=0.15, step=0.01, format="%.3f")
            feeder_r = st.number_input("Resistansi saluran (ohm/km)", min_value=0.001, max_value=10.0, value=0.32, step=0.01)
        with g3:
            feeder_x = st.number_input("Reaktansi saluran (ohm/km)", min_value=0.001, max_value=10.0, value=0.08, step=0.01)
            feeder_amp = st.number_input("Batas arus saluran (kA)", min_value=0.01, max_value=10.0, value=0.30, step=0.01)
        transformer_vkr = st.number_input("Rugi tembaga / VkR trafo (%)", min_value=0.1, max_value=10.0, value=1.2, step=0.1)
        load_pf = st.slider("Faktor daya beban", min_value=0.50, max_value=1.00, value=0.95, step=0.01)

    if st.button("Jalankan simulasi Pandapower", type="primary", use_container_width=False):
        try:
            from solarsmart.grid import analyze_grid
            grid_results = analyze_grid(
                peak_load_kw=float(peak_load_kw),
                daytime_load_fraction=float(daytime_load_fraction),
                load_power_factor=float(load_pf),
                pv_capacity_kwp=float(pv_capacity),
                battery_capacity_kwh=float(battery_capacity),
                battery_c_rate=float(battery_c_rate),
                transformer_kva=float(transformer_kva),
                feeder_length_km=float(feeder_length),
                r_ohm_per_km=float(feeder_r),
                x_ohm_per_km=float(feeder_x),
                feeder_max_current_ka=float(feeder_amp),
                transformer_vk_percent=float(transformer_vk),
                transformer_vkr_percent=float(transformer_vkr),
            )
            st.session_state["grid_results"] = grid_results
            st.session_state["grid_params"] = {
                "trafo_kva": transformer_kva, "feeder_km": feeder_length,
                "r_ohm_km": feeder_r, "x_ohm_km": feeder_x,
            }
        except Exception as exc:
            st.error(f"Simulasi jaringan belum berhasil: {exc}")
            st.caption("Pastikan pandapower terpasang melalui requirements.txt. Bila gagal konvergen, periksa kembali parameter jaringan.")

    if "grid_results" in st.session_state:
        grid_results = st.session_state["grid_results"]
        st.markdown("#### Hasil power flow")
        st.dataframe(grid_results.style.format({
            "Tegangan pelanggan (pu)": "{:.4f}",
            "Loading trafo (%)": "{:.1f}%",
            "Loading saluran (%)": "{:.1f}%",
            "Daya dari jaringan (kW)": "{:.2f}",
        }), use_container_width=True, hide_index=True)
        valid = grid_results[grid_results["Status"] == "Konvergen"]
        if not valid.empty:
            plot_df = valid.melt(id_vars="Skenario", value_vars=["Tegangan pelanggan (pu)", "Loading trafo (%)", "Loading saluran (%)"], var_name="Indikator", value_name="Nilai")
            fig_grid = px.bar(plot_df, x="Skenario", y="Nilai", color="Indikator", barmode="group")
            fig_grid.update_layout(height=400, xaxis_title="Skenario", yaxis_title="Nilai (satuan mengikuti indikator)")
            st.plotly_chart(fig_grid, use_container_width=True)
        st.download_button("Unduh hasil power flow (CSV)", data=grid_results.to_csv(index=False).encode("utf-8"),
                           file_name="solarsmart_hasil_pandapower.csv", mime="text/csv")
        st.caption("Konvensi daya: nilai positif pada 'Daya dari jaringan' berarti impor dari jaringan hulu; nilai negatif menunjukkan aliran balik/ekspor dari jaringan pelanggan.")
    else:
        st.info("Klik **Jalankan simulasi Pandapower** untuk membangun jaringan contoh dan menghitung power flow.")

    st.warning("Hasil ini hanya model jaringan contoh dan analisis aliran daya seimbang (balanced). Ini bukan studi sambungan resmi PLN, bukan pengaturan proteksi, dan tidak menggantikan survei teknis lokasi.")

with tab_guide:
    st.subheader("Cara kerja SolarSmart")
    st.markdown("""
    **Alur perhitungan aplikasi**

    1. Pengguna memasukkan konsumsi listrik, kapasitas PLTS, baterai, tarif, dan parameter biaya.
    2. Modul energi membentuk profil beban dan produksi PV per jam selama satu tahun.
    3. Pengendali baterai sederhana menyimpan surplus PV dan memasok beban ketika PV tidak mencukupi.
    4. Pandapower membangun feeder 20 kV/0,4 kV dan menjalankan power flow pada beberapa kondisi operasi.
    5. Modul ekonomi menghitung CAPEX, O&M, penggantian komponen, penghematan, NPV, IRR, ROI, dan payback.
    """)
    st.markdown("#### Rumus dasar yang digunakan")
    st.latex(r"E_{PV,annual} = P_{PV} \times Y_{specific,day} \times 365")
    st.latex(r"E_{grid} = \sum_{t=1}^{8760} P_{grid,t}\Delta t")
    st.latex(r"CAPEX = C_{PV}+C_{inverter}+C_{BOS}+C_{battery}+C_{installation}+C_{fixed}")
    st.latex(r"Payback \approx \frac{CAPEX}{Annual\ Net\ Savings}")
    st.latex(r"NPV = -CAPEX + \sum_{y=1}^{N}\frac{CashFlow_y}{(1+r)^y}")

    st.markdown("#### Batasan dan asumsi penting")
    st.markdown("""
    - Profil konsumsi dan produksi matahari merupakan profil representatif; unggah atau integrasikan data aktual untuk studi yang lebih akurat.
    - Model baterai menggunakan efisiensi round-trip, batas DoD, dan C-rate. Belum memodelkan temperatur, penuaan baterai, batas tegangan sel, atau kendali BMS secara rinci.
    - Modul pandapower memakai feeder radial contoh yang seimbang. Data trafo dan kabel harus diganti dengan data aktual sebelum hasil dipakai untuk keputusan teknik.
    - Biaya komponen adalah placeholder yang bisa diedit, bukan harga pasar yang dijamin.
    - Tagihan disederhanakan menjadi komponen energi (kWh × tarif). Pajak penerangan jalan, biaya administrasi, rekening minimum, dan aturan golongan khusus belum dimodelkan lengkap.
    - Ekspor listrik bernilai nol secara default. Periksa aturan, kuota, persetujuan, dan skema kontrak terbaru untuk lokasi serta tanggal pengajuan Anda.
    - Proyeksi arus kas mengasumsikan operasi tahunan serupa dan mengoreksi produksi melalui degradasi PV. Analisis finansial proyek nyata perlu penawaran vendor dan data lokasi.
    """)
    st.markdown("#### Sumber acuan")
    st.markdown("- [Dokumentasi Pandapower](https://pandapower.readthedocs.io/)")
    st.markdown("- [Permen ESDM No. 2 Tahun 2024 – PLTS Atap](https://peraturan.bpk.go.id/Details/288519/permen-esdm-no-2-tahun-2024)")
    st.markdown("- [Informasi tarif listrik PLN Triwulan IV 2026](https://www.pln.co.id/tarif-listrik-triwulan-iv-2026)")
    st.markdown("- [PVGIS – Photovoltaic Geographical Information System](https://re.jrc.ec.europa.eu/pvg_tools/en/)")

st.divider()
st.caption("SolarSmart prototype · Python + Streamlit + Pandapower · Hasil simulasi bersifat indikatif dan harus diverifikasi oleh tenaga teknik yang kompeten sebelum implementasi.")
