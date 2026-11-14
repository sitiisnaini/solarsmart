"""Financial model for SolarSmart (editable assumptions, not a quotation)."""
from __future__ import annotations

import numpy as np
import numpy_financial as npf
import pandas as pd

from .energy import simulate_year, summarize_energy


def calculate_capex(
    pv_kwp: float,
    battery_kwh: float,
    pv_module_cost_per_kwp: float,
    inverter_cost_per_kw: float,
    bos_cost_per_kwp: float,
    installation_cost_per_kwp: float,
    battery_cost_per_kwh: float,
    fixed_soft_cost: float,
) -> dict[str, float]:
    items = {
        "Modul PV": pv_kwp * pv_module_cost_per_kwp,
        "Inverter": pv_kwp * inverter_cost_per_kw,
        "Balance of System": pv_kwp * bos_cost_per_kwp,
        "Instalasi": pv_kwp * installation_cost_per_kwp,
        "Baterai": battery_kwh * battery_cost_per_kwh,
        "Survei / desain / biaya tetap": fixed_soft_cost,
    }
    items["Total investasi"] = float(sum(items.values()))
    return items


def _payback_year(cashflows: list[float], discounted: bool = False, discount_rate: float = 0.0) -> float | None:
    cumulative = float(cashflows[0])
    if cumulative >= 0:
        return 0.0
    for year, cf in enumerate(cashflows[1:], start=1):
        contribution = cf / ((1.0 + discount_rate) ** year) if discounted else cf
        previous = cumulative
        cumulative += contribution
        if cumulative >= 0 and contribution > 0:
            fraction = (0.0 - previous) / contribution
            return (year - 1) + float(np.clip(fraction, 0.0, 1.0))
    return None


def financial_projection(
    df,
    tariff_rp_kwh: float,
    export_credit_rp_kwh: float,
    capex_items: dict[str, float],
    analysis_years: int = 25,
    annual_pv_degradation_pct: float = 0.50,
    tariff_escalation_pct: float = 3.0,
    annual_om_pct_of_capex: float = 1.0,
    discount_rate_pct: float = 8.0,
    battery_replacement_year: int = 10,
    battery_replacement_fraction: float = 0.80,
    inverter_replacement_year: int = 12,
    inverter_replacement_fraction: float = 0.30,
) -> dict:
    """Build a simple annual cash-flow projection.

    Annual generation-related savings are adjusted with PV degradation and
    tariff escalation. This is a planning-level approximation; it does not
    recalculate the hourly dispatch for every future year.
    """
    metrics = summarize_energy(df)
    capex = float(capex_items.get("Total investasi", 0.0))
    pv_savings_kwh = metrics["solar_to_load_kwh"]
    export_kwh = metrics["grid_export_kwh"]
    annual_om = capex * annual_om_pct_of_capex / 100.0
    degradation = np.clip(annual_pv_degradation_pct / 100.0, 0.0, 0.10)
    tariff_growth = max(-0.99, tariff_escalation_pct / 100.0)
    discount = max(-0.99, discount_rate_pct / 100.0)

    # Year 1 savings: electricity purchases displaced plus any explicitly
    # configured export credit. Indonesia's default is zero export credit.
    year1_gross_savings = pv_savings_kwh * tariff_rp_kwh + export_kwh * export_credit_rp_kwh
    cashflows = [-capex]
    rows = []
    cumulative = -capex

    battery_cost = float(capex_items.get("Baterai", 0.0))
    inverter_cost = float(capex_items.get("Inverter", 0.0))

    for year in range(1, analysis_years + 1):
        pv_factor = (1.0 - degradation) ** (year - 1)
        tariff_factor = (1.0 + tariff_growth) ** (year - 1)
        gross_savings = year1_gross_savings * pv_factor * tariff_factor
        om_cost = annual_om * (1.0 + max(0.0, tariff_growth)) ** (year - 1)
        battery_replacement = (
            battery_cost * battery_replacement_fraction
            if battery_cost > 0 and battery_replacement_year > 0 and year == battery_replacement_year
            else 0.0
        )
        inverter_replacement = (
            inverter_cost * inverter_replacement_fraction
            if inverter_cost > 0 and inverter_replacement_year > 0 and year == inverter_replacement_year
            else 0.0
        )
        net_cash = gross_savings - om_cost - battery_replacement - inverter_replacement
        cashflows.append(net_cash)
        cumulative += net_cash
        rows.append(
            {
                "Tahun": year,
                "Penghematan bruto (Rp)": gross_savings,
                "O&M (Rp)": om_cost,
                "Penggantian baterai (Rp)": battery_replacement,
                "Penggantian inverter (Rp)": inverter_replacement,
                "Arus kas bersih (Rp)": net_cash,
                "Akumulasi arus kas (Rp)": cumulative,
            }
        )

    npv = float(npf.npv(discount, cashflows))
    try:
        irr = float(npf.irr(cashflows))
        if not np.isfinite(irr):
            irr = None
    except (ValueError, ZeroDivisionError):
        irr = None

    total_net_benefit = float(sum(cashflows[1:]))
    roi_pct = ((total_net_benefit - capex) / capex * 100.0) if capex > 0 else None
    simple_payback = _payback_year(cashflows)
    discounted_payback = _payback_year(cashflows, discounted=True, discount_rate=discount)

    return {
        "capex": capex,
        "year1_gross_savings": year1_gross_savings,
        "year1_om": annual_om,
        "year1_net_savings": year1_gross_savings - annual_om,
        "npv": npv,
        "irr": irr,
        "roi_pct": roi_pct,
        "simple_payback_years": simple_payback,
        "discounted_payback_years": discounted_payback,
        "cashflows": cashflows,
        "projection": rows,
        "cumulative_net_cash_after_capex": cumulative,
        "metrics": metrics,
    }


def run_financial_scenarios(
    *,
    daily_consumption_kwh: float,
    pv_capacity_kwp: float,
    specific_yield_kwh_kwp_day: float,
    profile_name: str,
    battery_capacity_kwh: float,
    battery_dod: float,
    battery_roundtrip_efficiency: float,
    battery_c_rate: float,
    tariff_rp_kwh: float,
    export_credit_rp_kwh: float,
    cost_inputs: dict,
    finance_inputs: dict,
) -> dict:
    common = dict(
        daily_consumption_kwh=daily_consumption_kwh,
        pv_capacity_kwp=pv_capacity_kwp,
        specific_yield_kwh_kwp_day=specific_yield_kwh_kwp_day,
        profile_name=profile_name,
        battery_dod=battery_dod,
        battery_roundtrip_efficiency=battery_roundtrip_efficiency,
        battery_c_rate=battery_c_rate,
    )
    pv_only_df = simulate_year(**common, battery_capacity_kwh=0.0)
    hybrid_df = simulate_year(**common, battery_capacity_kwh=battery_capacity_kwh)

    pv_capex = calculate_capex(
        pv_capacity_kwp, 0.0,
        cost_inputs["pv_module_cost_per_kwp"],
        cost_inputs["inverter_cost_per_kw"],
        cost_inputs["bos_cost_per_kwp"],
        cost_inputs["installation_cost_per_kwp"],
        cost_inputs["battery_cost_per_kwh"],
        cost_inputs["fixed_soft_cost"],
    )
    hybrid_capex = calculate_capex(
        pv_capacity_kwp, battery_capacity_kwh,
        cost_inputs["pv_module_cost_per_kwp"],
        cost_inputs["inverter_cost_per_kw"],
        cost_inputs["bos_cost_per_kwp"],
        cost_inputs["installation_cost_per_kwp"],
        cost_inputs["battery_cost_per_kwh"],
        cost_inputs["fixed_soft_cost"],
    )

    pv_finance = financial_projection(pv_only_df, tariff_rp_kwh, export_credit_rp_kwh, pv_capex, **finance_inputs)
    hybrid_finance = financial_projection(hybrid_df, tariff_rp_kwh, export_credit_rp_kwh, hybrid_capex, **finance_inputs)
    return {
        "pv_only": {"df": pv_only_df, "capex_items": pv_capex, "finance": pv_finance},
        "hybrid": {"df": hybrid_df, "capex_items": hybrid_capex, "finance": hybrid_finance},
    }


def scan_pv_sizes(
    *,
    daily_consumption_kwh: float,
    profile_name: str,
    roof_area_m2: float,
    specific_yield_kwh_kwp_day: float,
    battery_capacity_kwh: float,
    battery_dod: float,
    battery_roundtrip_efficiency: float,
    battery_c_rate: float,
    tariff_rp_kwh: float,
    export_credit_rp_kwh: float,
    cost_inputs: dict,
    finance_inputs: dict,
    current_pv_kwp: float = 0.0,
) -> pd.DataFrame:
    """Compare PV sizes that fit the estimated usable roof area.

    The scan holds battery size and all financial assumptions constant. It is
    a first-pass NPV comparison, not a formal global optimization.
    """
    roof_limit_kwp = max(0.1, roof_area_m2 / 5.5)
    upper = min(roof_limit_kwp, 50.0)
    count = max(3, min(14, int(np.ceil(upper / 0.5)) + 1))
    candidates = list(np.linspace(max(0.1, min(0.5, upper)), upper, count))
    if 0 < current_pv_kwp <= upper:
        candidates.append(float(current_pv_kwp))
    candidates = sorted({min(upper, max(0.1, round(float(x), 2))) for x in candidates})

    rows = []
    for pv_kwp in candidates:
        df = simulate_year(
            daily_consumption_kwh=daily_consumption_kwh,
            pv_capacity_kwp=pv_kwp,
            specific_yield_kwh_kwp_day=specific_yield_kwh_kwp_day,
            profile_name=profile_name,
            battery_capacity_kwh=battery_capacity_kwh,
            battery_dod=battery_dod,
            battery_roundtrip_efficiency=battery_roundtrip_efficiency,
            battery_c_rate=battery_c_rate,
        )
        capex_items = calculate_capex(
            pv_kwp, battery_capacity_kwh,
            cost_inputs["pv_module_cost_per_kwp"],
            cost_inputs["inverter_cost_per_kw"],
            cost_inputs["bos_cost_per_kwp"],
            cost_inputs["installation_cost_per_kwp"],
            cost_inputs["battery_cost_per_kwh"],
            cost_inputs["fixed_soft_cost"],
        )
        fin = financial_projection(df, tariff_rp_kwh, export_credit_rp_kwh, capex_items, **finance_inputs)
        met = summarize_energy(df)
        rows.append({
            "Kapasitas PV (kWp)": pv_kwp,
            "Kapasitas baterai (kWh)": battery_capacity_kwh,
            "CAPEX (Rp)": fin["capex"],
            "Impor PLN (kWh/tahun)": met["grid_import_kwh"],
            "Self-sufficiency (%)": met["self_sufficiency_pct"],
            "Penghematan bruto tahun 1 (Rp)": fin["year1_gross_savings"],
            "Payback (tahun)": fin["simple_payback_years"] if fin["simple_payback_years"] is not None else np.nan,
            "NPV (Rp)": fin["npv"],
            "IRR (%)": fin["irr"] * 100.0 if fin["irr"] is not None else np.nan,
        })
    return pd.DataFrame(rows).sort_values("Kapasitas PV (kWp)").reset_index(drop=True)
