import unittest

from solarsmart.energy import simulate_year, summarize_energy
from solarsmart.economics import calculate_capex, financial_projection, scan_pv_sizes


class EnergySimulationTests(unittest.TestCase):
    def test_energy_balance_without_pv(self):
        df = simulate_year(10.0, 0.0, 3.8, battery_capacity_kwh=0.0)
        summary = summarize_energy(df)
        self.assertAlmostEqual(summary["grid_import_kwh"], summary["load_kwh"], places=6)
        self.assertAlmostEqual(summary["grid_export_kwh"], 0.0, places=6)

    def test_pv_reduces_grid_import(self):
        base = simulate_year(10.0, 0.0, 3.8, battery_capacity_kwh=0.0)
        with_pv = simulate_year(10.0, 3.0, 3.8, battery_capacity_kwh=0.0)
        self.assertLess(summarize_energy(with_pv)["grid_import_kwh"], summarize_energy(base)["grid_import_kwh"])

    def test_battery_does_not_increase_grid_import_in_pv_case(self):
        pv_only = simulate_year(10.0, 3.0, 3.8, battery_capacity_kwh=0.0)
        pv_battery = simulate_year(10.0, 3.0, 3.8, battery_capacity_kwh=5.0)
        self.assertLessEqual(summarize_energy(pv_battery)["grid_import_kwh"], summarize_energy(pv_only)["grid_import_kwh"] + 1e-8)


    def test_financial_projection_returns_cashflow_indicators(self):
        df = simulate_year(10.0, 3.0, 3.8, battery_capacity_kwh=0.0)
        capex = calculate_capex(3.0, 0.0, 5_000_000, 2_500_000, 2_000_000, 1_500_000, 5_000_000, 1_500_000)
        result = financial_projection(
            df, 1444.7, 0.0, capex,
            analysis_years=10,
            annual_pv_degradation_pct=0.5,
            tariff_escalation_pct=3.0,
            annual_om_pct_of_capex=1.0,
            discount_rate_pct=8.0,
            battery_replacement_year=0,
            battery_replacement_fraction=0.8,
            inverter_replacement_year=0,
            inverter_replacement_fraction=0.3,
        )
        self.assertEqual(len(result["projection"]), 10)
        self.assertIn("npv", result)
        self.assertEqual(result["capex"], capex["Total investasi"])

    def test_pv_size_scan_respects_roof_limit(self):
        cost = {
            "pv_module_cost_per_kwp": 5_000_000,
            "inverter_cost_per_kw": 2_500_000,
            "bos_cost_per_kwp": 2_000_000,
            "installation_cost_per_kwp": 1_500_000,
            "battery_cost_per_kwh": 5_000_000,
            "fixed_soft_cost": 1_500_000,
        }
        finance = {
            "analysis_years": 5,
            "annual_pv_degradation_pct": 0.5,
            "tariff_escalation_pct": 3.0,
            "annual_om_pct_of_capex": 1.0,
            "discount_rate_pct": 8.0,
            "battery_replacement_year": 0,
            "battery_replacement_fraction": 0.8,
            "inverter_replacement_year": 0,
            "inverter_replacement_fraction": 0.3,
        }
        table = scan_pv_sizes(
            daily_consumption_kwh=5.0,
            profile_name="Rumah tangga",
            roof_area_m2=10.0,
            specific_yield_kwh_kwp_day=3.8,
            battery_capacity_kwh=0.0,
            battery_dod=0.8,
            battery_roundtrip_efficiency=0.9,
            battery_c_rate=0.5,
            tariff_rp_kwh=1444.7,
            export_credit_rp_kwh=0.0,
            cost_inputs=cost,
            finance_inputs=finance,
            current_pv_kwp=1.0,
        )
        self.assertGreater(len(table), 0)
        self.assertLessEqual(table["Kapasitas PV (kWp)"].max(), 10.0 / 5.5 + 1e-6)


if __name__ == "__main__":
    unittest.main()
