"""Hourly PV, load and battery simulation for SolarSmart.

This is a quasi-static energy-balance model. It is not an electromagnetic
transient or inverter-control simulator.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# Relative hourly profiles. Each is normalized to sum to 1.0.
_LOAD_PROFILES = {
    "Rumah tangga": np.array([
        0.026, 0.022, 0.020, 0.019, 0.020, 0.024,
        0.030, 0.036, 0.038, 0.036, 0.034, 0.035,
        0.040, 0.039, 0.036, 0.036, 0.040, 0.052,
        0.070, 0.082, 0.085, 0.075, 0.060, 0.045,
    ], dtype=float),
    "UMKM / toko": np.array([
        0.012, 0.010, 0.009, 0.009, 0.010, 0.014,
        0.025, 0.055, 0.075, 0.078, 0.078, 0.078,
        0.078, 0.075, 0.073, 0.070, 0.067, 0.060,
        0.045, 0.030, 0.022, 0.018, 0.015, 0.012,
    ], dtype=float),
    "Kantor": np.array([
        0.012, 0.010, 0.009, 0.009, 0.010, 0.015,
        0.035, 0.060, 0.075, 0.080, 0.080, 0.080,
        0.080, 0.080, 0.078, 0.075, 0.070, 0.055,
        0.025, 0.015, 0.012, 0.010, 0.010, 0.010,
    ], dtype=float),
}
_LOAD_PROFILES = {name: profile / profile.sum() for name, profile in _LOAD_PROFILES.items()}

# Approximate daylight generation shape (hourly weights, 06:00–17:00).
_SOLAR_PROFILE = np.zeros(24, dtype=float)
_SOLAR_PROFILE[6:18] = np.array(
    [0.015, 0.045, 0.085, 0.125, 0.155, 0.165,
     0.155, 0.115, 0.075, 0.040, 0.018, 0.007], dtype=float
)
_SOLAR_PROFILE /= _SOLAR_PROFILE.sum()

# Illustrative monthly seasonality factors. Normalized to a 1.0 annual mean.
_MONTH_DAYS = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31], dtype=float)
_SOLAR_MONTHLY = np.array(
    [0.91, 0.92, 0.97, 1.00, 1.04, 1.07,
     1.10, 1.10, 1.07, 1.02, 0.93, 0.87], dtype=float
)
_SOLAR_MONTHLY /= np.average(_SOLAR_MONTHLY, weights=_MONTH_DAYS)
_LOAD_MONTHLY = np.array(
    [1.00, 0.98, 1.00, 0.99, 1.00, 1.01,
     1.02, 1.02, 1.00, 1.00, 0.99, 0.99], dtype=float
)
_LOAD_MONTHLY /= np.average(_LOAD_MONTHLY, weights=_MONTH_DAYS)


def simulate_year(
    daily_consumption_kwh: float,
    pv_capacity_kwp: float,
    specific_yield_kwh_kwp_day: float,
    profile_name: str = "Rumah tangga",
    battery_capacity_kwh: float = 0.0,
    battery_dod: float = 0.80,
    battery_roundtrip_efficiency: float = 0.90,
    battery_c_rate: float = 0.50,
    initial_soc_fraction: float = 0.0,
) -> pd.DataFrame:
    """Simulate a representative 365-day year at one-hour resolution.

    PV generation is distributed by a fixed daylight curve and monthly
    seasonality. Loads follow an editable high-level customer profile.
    Battery charging is PV-surplus-only; grid charging is not modeled.
    """
    if daily_consumption_kwh < 0 or pv_capacity_kwp < 0:
        raise ValueError("Konsumsi dan kapasitas PV tidak boleh negatif.")
    if specific_yield_kwh_kwp_day < 0:
        raise ValueError("Specific yield tidak boleh negatif.")
    if profile_name not in _LOAD_PROFILES:
        raise ValueError(f"Profil beban tidak dikenal: {profile_name}")

    idx = pd.date_range("2026-01-01 00:00", periods=365 * 24, freq="h")
    hours = idx.hour.to_numpy()
    months = idx.month.to_numpy() - 1
    days = idx.dayofyear.to_numpy()

    load_shape = _LOAD_PROFILES[profile_name]
    load = daily_consumption_kwh * _LOAD_MONTHLY[months] * load_shape[hours]
    pv = (
        pv_capacity_kwp
        * specific_yield_kwh_kwp_day
        * _SOLAR_MONTHLY[months]
        * _SOLAR_PROFILE[hours]
    )

    usable_capacity = max(0.0, battery_capacity_kwh * battery_dod)
    eta = float(np.sqrt(np.clip(battery_roundtrip_efficiency, 0.01, 1.0)))
    max_battery_power = max(0.0, battery_capacity_kwh * battery_c_rate)
    soc = usable_capacity * np.clip(initial_soc_fraction, 0.0, 1.0)

    n = len(idx)
    charge_from_pv = np.zeros(n)
    discharge_to_load = np.zeros(n)
    grid_import = np.zeros(n)
    grid_export = np.zeros(n)
    soc_series = np.zeros(n)
    direct_pv_to_load = np.minimum(load, pv)

    for i in range(n):
        surplus = max(0.0, pv[i] - load[i])
        deficit = max(0.0, load[i] - pv[i])

        if usable_capacity > 0 and max_battery_power > 0:
            # Charge input is limited by PV surplus, inverter power and free SOC.
            charge_input = min(
                surplus,
                max_battery_power,
                max(0.0, (usable_capacity - soc) / eta),
            )
            soc += charge_input * eta
            charge_from_pv[i] = charge_input
            surplus -= charge_input

            # Discharge output is limited by load deficit, power and stored energy.
            discharge_output = min(
                deficit,
                max_battery_power,
                soc * eta,
            )
            soc -= discharge_output / eta
            discharge_to_load[i] = discharge_output
            deficit -= discharge_output

        grid_import[i] = deficit
        grid_export[i] = surplus
        soc_series[i] = soc

    df = pd.DataFrame(
        {
            "load_kwh": load,
            "pv_kwh": pv,
            "pv_direct_to_load_kwh": direct_pv_to_load,
            "battery_charge_from_pv_kwh": charge_from_pv,
            "battery_discharge_to_load_kwh": discharge_to_load,
            "grid_import_kwh": grid_import,
            "grid_export_kwh": grid_export,
            "battery_soc_kwh": soc_series,
        },
        index=idx,
    )
    df.index.name = "timestamp"
    return df


def summarize_energy(df: pd.DataFrame) -> dict[str, float]:
    """Return annual energy indicators in kWh and percentages."""
    load = float(df["load_kwh"].sum())
    pv = float(df["pv_kwh"].sum())
    grid_import = float(df["grid_import_kwh"].sum())
    grid_export = float(df["grid_export_kwh"].sum())
    solar_to_load = max(0.0, load - grid_import)
    return {
        "load_kwh": load,
        "pv_kwh": pv,
        "grid_import_kwh": grid_import,
        "grid_export_kwh": grid_export,
        "solar_to_load_kwh": solar_to_load,
        "self_sufficiency_pct": (solar_to_load / load * 100.0) if load else 0.0,
        "self_consumption_pct": ((pv - grid_export) / pv * 100.0) if pv else 0.0,
        "peak_import_kw": float(df["grid_import_kwh"].max()),
        "peak_export_kw": float(df["grid_export_kwh"].max()),
    }
