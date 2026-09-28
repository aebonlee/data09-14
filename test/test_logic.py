"""순수 로직 — 기대값은 손으로 계산한 값입니다."""
import unittest

from helpers import ROOT  # noqa: F401  (sys.path 설정)
from algorithms import placeholder as ph
from vibtool.connector import call_algorithm
from vibtool.config import load_settings
from vibtool.ingest import parse_file_name, validate
from vibtool.judge import find_threshold, judge

S = load_settings()
VIB = S["sensors"]["vib"]


class Stats(unittest.TestCase):
    def test_rms(self):
        self.assertAlmostEqual(ph.rms([3, 4]), 3.5355339, places=6)   # sqrt((9+16)/2)
        self.assertAlmostEqual(ph.rms([1, -1, 1, -1]), 1.0)

    def test_peak(self):
        self.assertEqual(ph.peak([-5, 2, 4]), 5)

    def test_kurtosis(self):
        # 평균 1, 편차 -1,-1,-1,3 → m2=12/4=3, m4=84/4=21 → 21/9
        self.assertAlmostEqual(ph.kurtosis([0, 0, 0, 4]), 21 / 9)
        self.assertAlmostEqual(ph.kurtosis([1, -1, 1, -1]), 1.0)
        self.assertEqual(ph.kurtosis([2, 2, 2]), 0.0)

    def test_run_names(self):
        m = {"sensors": {"vib": {"unit": "g", "time": [0, 1], "channels": {"X": [3, 4]}}}}
        out = {r["name"]: r for r in ph.run(m, {})}
        self.assertEqual(sorted(out), ["vib_X_kurtosis", "vib_X_peak", "vib_X_rms"])
        self.assertEqual(out["vib_X_peak"]["value"], 4)
        self.assertEqual(out["vib_X_rms"]["unit"], "g")
        self.assertEqual(out["vib_X_kurtosis"]["unit"], "-")


TH = {"version": "t1", "items": {
    "vib_X_rms": {"warn": 0.2, "fault": 0.4},
    "vib_*_rms": {"warn": 0.5, "fault": 1.0},
    "vib_*_peak": {"warn": 2.0, "fault": 3.0}}}


class Judge(unittest.TestCase):
    def r(self, **kv):
        return [{"name": k, "value": v, "unit": ""} for k, v in kv.items()]

    def test_exact_name_beats_pattern(self):
        self.assertEqual(find_threshold("vib_X_rms", TH)["warn"], 0.2)
        self.assertEqual(find_threshold("vib_Y_rms", TH)["warn"], 0.5)
        self.assertIsNone(find_threshold("gyro_X_rms", TH))

    def test_boundaries(self):
        self.assertEqual(judge(self.r(vib_Y_rms=0.49), TH)[0], "정상")
        self.assertEqual(judge(self.r(vib_Y_rms=0.5), TH)[0], "주의")   # 기준값과 같으면 해당 등급
        self.assertEqual(judge(self.r(vib_Y_rms=1.0), TH)[0], "고장")

    def test_worst_item_wins(self):
        g, basis, per = judge(self.r(vib_Y_rms=0.1, vib_Y_peak=2.5, vib_Z_rms=1.2), TH)
        self.assertEqual(g, "고장")
        self.assertEqual(per, {"vib_Y_rms": "정상", "vib_Y_peak": "주의", "vib_Z_rms": "고장"})
        self.assertEqual(basis, ["vib_Z_rms = 1.2 (고장 기준 1)"])

    def test_no_threshold(self):
        self.assertEqual(judge(self.r(gyro_X_rms=99.0), TH)[0], "판정 불가")

    def test_lower_is_worse(self):
        th = {"higher_is_worse": False, "items": {"margin": {"warn": 10, "fault": 5}}}
        self.assertEqual(judge(self.r(margin=12.0), th)[0], "정상")
        self.assertEqual(judge(self.r(margin=5.0), th)[0], "고장")


class FileName(unittest.TestCase):
    def test_ok(self):
        i = parse_file_name("EQ-A01_20260901-090000_vib.csv", S)
        self.assertEqual(i, {"equipment_id": "EQ-A01", "measured_at": "2026-09-01 09:00:00",
                             "sensor": "vib", "is_sample": False})
        self.assertTrue(parse_file_name("예시데이터_EQ-A01_20260901-090000_gyro.csv", S)["is_sample"])

    def test_bad(self):
        self.assertIsNone(parse_file_name("EQ-A01_20261301-090000_vib.csv", S))  # 13월
        self.assertIsNone(parse_file_name("EQ-A01_20260901-090000_temp.csv", S))
        self.assertIsNone(parse_file_name("memo.csv", S))


class Validate(unittest.TestCase):
    H = ["time_s", "ax", "ay", "az"]

    def test_ok(self):
        data, err, warn = validate(self.H, [["0", "1", "2", "3"], ["0.001", "4", "5", "6"]], VIB)
        self.assertEqual(err, [])
        self.assertEqual(data["channels"]["X"], [1.0, 4.0])
        self.assertEqual(data["time"], [0.0, 0.001])

    def test_missing_column(self):
        data, err, _ = validate(["time_s", "ax", "ay"], [["0", "1", "2"]], VIB)
        self.assertIsNone(data)
        self.assertIn("az", err[0])

    def test_missing_values_reject_or_drop(self):
        rows = [["0", "1", "1", "1"], ["0.001", "", "1", "1"], ["0.002", "x", "1", "1"], ["0.003", "2", "2", "2"]]
        data, err, _ = validate(self.H, rows, VIB, "reject")
        self.assertIsNone(data)
        self.assertIn("행 2개 (첫 행: 3, 4)", err[0])
        data, err, warn = validate(self.H, rows, VIB, "drop_rows")
        self.assertEqual(err, [])
        self.assertEqual(data["channels"]["X"], [1.0, 2.0])
        self.assertEqual(len(warn), 1)

    def test_time_order(self):
        data, err, _ = validate(self.H, [["0", "1", "1", "1"], ["0.002", "1", "1", "1"], ["0.001", "1", "1", "1"]], VIB)
        self.assertIsNone(data)
        self.assertIn("시각이 증가하지 않는", err[0])


class Connector(unittest.TestCase):
    def test_shape_checks(self):
        with self.assertRaises(ValueError):
            call_algorithm(lambda m, p: [], {}, {})
        with self.assertRaises(ValueError):
            call_algorithm(lambda m, p: [{"name": "a", "value": 1}, {"name": "a", "value": 2}], {}, {})
        with self.assertRaises(ValueError):
            call_algorithm(lambda m, p: [{"name": "a", "value": float("nan")}], {}, {})
        out = call_algorithm(lambda m, p: [{"name": "a", "value": "1.5"}], {}, {})
        self.assertEqual(out, [{"name": "a", "value": 1.5, "unit": ""}])


if __name__ == "__main__":
    unittest.main()
