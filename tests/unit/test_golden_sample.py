from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class GoldenSampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sample = json.loads((ROOT / "reference/fw309_anlage21.json").read_text())

    def test_controller(self) -> None:
        controller = self.sample["controller"]
        self.assertEqual(controller["model"], "TROVIS 5573-1")
        self.assertEqual(controller["firmware"], "03.09.00")
        self.assertEqual(controller["system_code"], "2.1")
        self.assertEqual(controller["modbus_unit_id"], 247)

    def test_required_co1_functions(self) -> None:
        states = {
            item["function"]: item["state"]
            for item in self.sample["configuration_options"]["CO1"]["functions"]
        }
        self.assertEqual(
            {key: states[key] for key in ("F01", "F02", "F03", "F12")},
            {"F01": "OFF", "F02": "ON", "F03": "ON", "F12": "ON"},
        )

    def test_controller_and_heating_parameters(self) -> None:
        f12 = next(
            item
            for item in self.sample["configuration_options"]["CO1"]["functions"]
            if item["function"] == "F12"
        )["parameters"]
        self.assertEqual(
            f12,
            {
                "kp": 0.2,
                "tn_s": 130,
                "tv_s": 0,
                "ty_s": 25,
                "hysteresis_c": 5.0,
                "minimum_on_minutes": 2,
                "minimum_off_minutes": 2,
            },
        )
        rk1 = self.sample["parameters"]["RK1"]
        expected = {
            "heating_curve_slope": 1.0,
            "heating_curve_level_c": 0.0,
            "minimum_flow_c": 30.0,
            "maximum_flow_c": 70.0,
            "room_day_c": 19.5,
            "room_night_c": 17.0,
        }
        self.assertEqual({key: rk1[key] for key in expected}, expected)

    def test_dhw_and_time_programs(self) -> None:
        self.assertEqual(self.sample["parameters"]["DHW"]["setpoint_day_c"], 54.0)
        self.assertEqual(self.sample["parameters"]["DHW"]["setpoint_night_c"], 40.0)
        programs = self.sample["time_programs"]
        self.assertEqual(programs["RK1"]["intervals"], [{"start": "06:15", "end": "22:45"}])
        self.assertEqual(programs["DHW"]["intervals"], [{"start": "05:00", "end": "06:30"}])
        self.assertEqual(programs["circulation"]["intervals"], [{"start": "00:00", "end": "24:00"}])
