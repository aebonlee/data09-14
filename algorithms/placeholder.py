"""임시 알고리즘 — 1단계 흐름 확인용 기본 통계 (시험용, 판정용 아님).

[연결 약속] 실제 알고리즘도 같은 모양의 함수 하나만 있으면 됩니다.

    run(measurement, params) -> [{"name": 항목 이름, "value": 숫자, "unit": 단위}, ...]

measurement = {
    "equipment_id": "EQ-A01",
    "measured_at": "2026-09-01 09:00:00",
    "sensors": {
        "vib":  {"unit": "g",     "time": [...], "channels": {"X": [...], "Y": [...], "Z": [...]}},
        "gyro": {"unit": "deg/s", "time": [...], "channels": {"X": [...], ...}},
    },
}
params = 장비 정보(파라미터) dict — 예: {"회전수_rpm": "1800"}

모듈에 VERSION 문자열을 두면 결과·판정에 그 버전이 함께 기록됩니다.
"""
import math

NAME = "임시 기본 통계 (RMS·최대값·첨도)"
VERSION = "placeholder-0.1"


def rms(xs):
    """제곱평균제곱근. 평균(직류분)을 빼지 않은 원신호 기준입니다."""
    return math.sqrt(sum(x * x for x in xs) / len(xs))


def peak(xs):
    """절댓값 최대."""
    return max(abs(x) for x in xs)


def kurtosis(xs):
    """첨도(피어슨, 정규분포 = 3). 모든 값이 같으면 0."""
    n = len(xs)
    m = sum(xs) / n
    m2 = sum((x - m) ** 2 for x in xs) / n
    if m2 == 0:
        return 0.0
    m4 = sum((x - m) ** 4 for x in xs) / n
    return m4 / (m2 * m2)


STATS = (("rms", rms, True), ("peak", peak, True), ("kurtosis", kurtosis, False))


def run(measurement, params):
    out = []
    for sensor, data in measurement["sensors"].items():
        for axis, xs in data["channels"].items():
            for stat, fn, has_unit in STATS:
                out.append({
                    "name": "%s_%s_%s" % (sensor, axis, stat),
                    "value": round(fn(xs), 6),
                    "unit": data["unit"] if has_unit else "-",
                })
    return out
