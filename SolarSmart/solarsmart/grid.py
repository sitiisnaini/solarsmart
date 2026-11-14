"""Pandapower low-voltage feeder model for SolarSmart.

The network is an illustrative 20 kV / 0.4 kV radial feeder. Replace its
parameters with surveyed utility data before relying on engineering results.
"""
from __future__ import annotations

import copy
import math
import pandas as pd


def _build_base_network(
    transformer_kva: float,
    feeder_length_km: float,
    r_ohm_per_km: float,
    x_ohm_per_km: float,
    feeder_max_current_ka: float,
    transformer_vk_percent: float,
    transformer_vkr_percent: float,
):
    try:
        import pandapower as pp
    except ImportError as exc:
        raise RuntimeError(
            "Pandapower belum terpasang. Jalankan `pip install -r requirements.txt`."
        ) from exc

    if transformer_vkr_percent >= transformer_vk_percent:
        raise ValueError("VkR trafo harus lebih kecil daripada Vk.")

    net = pp.create_empty_network(name="SolarSmart illustrative LV feeder")
    hv_bus = pp.create_bus(net, vn_kv=20.0, name="Jaringan MV (20 kV)")
    lv_bus = pp.create_bus(net, vn_kv=0.4, name="Bus LV Trafo (0.4 kV)")
    customer_bus = pp.create_bus(net, vn_kv=0.4, name="Bus Pelanggan")

    pp.create_ext_grid(net, bus=hv_bus, vm_pu=1.0, name="Sumber jaringan")
    sn_mva = max(0.025, transformer_kva / 1000.0)
    pp.create_transformer_from_parameters(
        net,
        hv_bus=hv_bus,
        lv_bus=lv_bus,
        sn_mva=sn_mva,
        vn_hv_kv=20.0,
        vn_lv_kv=0.4,
        vk_percent=transformer_vk_percent,
        vkr_percent=transformer_vkr_percent,
        pfe_kw=max(0.05, transformer_kva * 0.0025),
        i0_percent=0.2,
        shift_degree=150,
        name=f"Trafo {transformer_kva:.0f} kVA",
    )
    pp.create_line_from_parameters(
        net,
        from_bus=lv_bus,
        to_bus=customer_bus,
        length_km=max(0.001, feeder_length_km),
        r_ohm_per_km=max(0.001, r_ohm_per_km),
        x_ohm_per_km=max(0.001, x_ohm_per_km),
        c_nf_per_km=210.0,
        max_i_ka=max(0.01, feeder_max_current_ka),
        name="Saluran LV menuju pelanggan",
    )
    load_idx = pp.create_load(net, bus=customer_bus, p_mw=0.0, q_mvar=0.0, name="Beban pelanggan")
    pv_idx = pp.create_sgen(net, bus=customer_bus, p_mw=0.0, q_mvar=0.0, name="PLTS pelanggan")
    storage_idx = pp.create_storage(
        net, bus=customer_bus, p_mw=0.0, max_e_mwh=0.0,
        soc_percent=0.0, name="Baterai pelanggan",
    )
    return pp, net, load_idx, pv_idx, storage_idx


def analyze_grid(
    *,
    peak_load_kw: float,
    daytime_load_fraction: float,
    load_power_factor: float,
    pv_capacity_kwp: float,
    battery_capacity_kwh: float,
    battery_c_rate: float,
    transformer_kva: float = 250.0,
    feeder_length_km: float = 0.15,
    r_ohm_per_km: float = 0.32,
    x_ohm_per_km: float = 0.08,
    feeder_max_current_ka: float = 0.30,
    transformer_vk_percent: float = 4.0,
    transformer_vkr_percent: float = 1.2,
) -> pd.DataFrame:
    """Run three representative steady-state network snapshots using pandapower."""
    pp, base, load_idx, pv_idx, storage_idx = _build_base_network(
        transformer_kva, feeder_length_km, r_ohm_per_km, x_ohm_per_km,
        feeder_max_current_ka, transformer_vk_percent, transformer_vkr_percent,
    )
    pf = min(1.0, max(0.5, load_power_factor))
    peak = max(0.0, peak_load_kw)
    q_peak = (peak / 1000.0) * math.tan(math.acos(pf)) if peak else 0.0
    pv_peak_kw = max(0.0, pv_capacity_kwp) * 0.95
    batt_power_kw = max(0.0, battery_capacity_kwh * battery_c_rate)

    scenarios = [
        {
            "name": "Beban puncak malam (tanpa PV)",
            "load_kw": peak,
            "pv_kw": 0.0,
            "storage_kw": 0.0,
            "explanation": "Kondisi beban tinggi saat produksi PV dianggap nol.",
        },
        {
            "name": "Siang: PV maksimum + beban rendah",
            "load_kw": peak * max(0.0, min(1.0, daytime_load_fraction)),
            "pv_kw": pv_peak_kw,
            "storage_kw": min(batt_power_kw, max(0.0, pv_peak_kw - peak * daytime_load_fraction)),
            "explanation": "Menguji kemungkinan aliran daya balik; baterai diasumsikan menyerap surplus jika tersedia.",
        },
        {
            "name": "Siang: PV maksimum tanpa pengisian baterai",
            "load_kw": peak * max(0.0, min(1.0, daytime_load_fraction)),
            "pv_kw": pv_peak_kw,
            "storage_kw": 0.0,
            "explanation": "Skenario konservatif untuk melihat dampak ekspor maksimum ke jaringan.",
        },
    ]
    rows = []
    for scenario in scenarios:
        net = copy.deepcopy(base)
        load_kw = scenario["load_kw"]
        q_mvar = (load_kw / 1000.0) * math.tan(math.acos(pf)) if load_kw else 0.0
        net.load.at[load_idx, "p_mw"] = load_kw / 1000.0
        net.load.at[load_idx, "q_mvar"] = q_mvar
        net.sgen.at[pv_idx, "p_mw"] = scenario["pv_kw"] / 1000.0
        # Pandapower storage convention: positive p_mw = charging, negative = discharging.
        net.storage.at[storage_idx, "p_mw"] = scenario["storage_kw"] / 1000.0
        net.storage.at[storage_idx, "max_e_mwh"] = max(0.0, battery_capacity_kwh) / 1000.0
        net.storage.at[storage_idx, "soc_percent"] = 50.0 if battery_capacity_kwh > 0 else 0.0
        try:
            pp.runpp(net, algorithm="nr", max_iteration=30, tolerance_mva=1e-8)
            converged = bool(net.converged)
        except Exception as exc:  # Keep the dashboard alive and report the scenario failure.
            rows.append({
                "Skenario": scenario["name"],
                "Status": f"Gagal konvergen: {str(exc)[:100]}",
                "Tegangan pelanggan (pu)": float("nan"),
                "Loading trafo (%)": float("nan"),
                "Loading saluran (%)": float("nan"),
                "Daya dari jaringan (kW)": float("nan"),
                "Catatan": scenario["explanation"],
            })
            continue

        if not converged:
            rows.append({
                "Skenario": scenario["name"], "Status": "Tidak konvergen",
                "Tegangan pelanggan (pu)": float("nan"),
                "Loading trafo (%)": float("nan"),
                "Loading saluran (%)": float("nan"),
                "Daya dari jaringan (kW)": float("nan"),
                "Catatan": scenario["explanation"],
            })
            continue

        customer_vm = float(net.res_bus.vm_pu.loc[2])
        trafo_loading = float(net.res_trafo.loading_percent.max()) if len(net.res_trafo) else 0.0
        line_loading = float(net.res_line.loading_percent.max()) if len(net.res_line) else 0.0
        # Positive ext_grid p means import from upstream; negative means export/reverse flow.
        grid_p_kw = float(net.res_ext_grid.p_mw.sum() * 1000.0)
        rows.append({
            "Skenario": scenario["name"],
            "Status": "Konvergen",
            "Tegangan pelanggan (pu)": customer_vm,
            "Loading trafo (%)": trafo_loading,
            "Loading saluran (%)": line_loading,
            "Daya dari jaringan (kW)": grid_p_kw,
            "Catatan": scenario["explanation"],
        })
    return pd.DataFrame(rows)
