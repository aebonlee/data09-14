#!/usr/bin/env python3
"""예시 데이터(가상) 만들기 — samples/ 에 진동·각속도 CSV 와 장비 정보 CSV 를 씁니다.

모두 시연용 가상 값입니다. 실제 장비·센서 값이 아닙니다.
같은 시드를 쓰므로 여러 번 실행해도 같은 파일이 나옵니다.
"""
import csv
import math
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "samples")
FS = 1000        # 가상 샘플링 주파수(Hz)
N = 1000         # 1초 분량
FREQ = 30.0      # 가상 회전 성분(Hz)

# (장비, 측정 일시, 진동 진폭 g, 각속도 진폭 deg/s, 충격 여부, 만들 센서, 결측 넣기)
CASES = [
    ("EQ-A01", "20260901-090000", 0.3, 2.0, False, ("vib", "gyro"), False),
    ("EQ-A01", "20260908-090000", 0.35, 2.2, False, ("vib", "gyro"), False),
    ("EQ-A01", "20260915-090000", 1.0, 3.0, False, ("vib", "gyro"), False),   # 주의가 나오도록
    ("EQ-A02", "20260901-100000", 0.3, 2.0, False, ("vib", "gyro"), False),
    ("EQ-A02", "20260915-100000", 2.0, 8.0, True, ("vib", "gyro"), False),    # 고장이 나오도록
    ("EQ-B01", "20260902-090000", 0.3, 2.0, False, ("vib",), False),          # 각속도 파일 없음 → 대기
    ("EQ-B01", "20260903-090000", 0.3, 2.0, False, ("vib", "gyro"), True),    # 진동 파일에 빈 값 → 오류
]
COLS = {"vib": ("ax", "ay", "az"), "gyro": ("gx", "gy", "gz")}
NOISE = {"vib": 0.02, "gyro": 0.2}


def signal(rng, amp, noise, impulse, axis_scale, phase):
    xs = []
    for i in range(N):
        t = i / FS
        v = amp * axis_scale * math.sin(2 * math.pi * FREQ * t + phase) + rng.gauss(0, noise)
        if impulse and i % 100 == 50:
            v += 3.5 * axis_scale
        xs.append(round(v, 5))
    return xs


def main():
    os.makedirs(OUT, exist_ok=True)
    for old in os.listdir(OUT):
        if old.startswith("예시데이터_") and old.endswith(".csv"):
            os.remove(os.path.join(OUT, old))
    rng = random.Random(20260928)
    for eq, dt, vamp, gamp, imp, sensors, hole in CASES:
        for sensor in sensors:
            amp = vamp if sensor == "vib" else gamp
            chans = [signal(rng, amp, NOISE[sensor], imp and sensor == "vib", sc, ph)
                     for sc, ph in ((1.0, 0.0), (0.7, 1.0), (0.5, 2.0))]
            path = os.path.join(OUT, "예시데이터_%s_%s_%s.csv" % (eq, dt, sensor))
            with open(path, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(("time_s",) + COLS[sensor])
                for i in range(N):
                    row = ["%.3f" % (i / FS)] + [c[i] for c in chans]
                    if hole and sensor == "vib" and i in (120, 121):
                        row[1] = ""
                    w.writerow(row)
    with open(os.path.join(OUT, "예시데이터_장비정보.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(("장비ID", "장비명", "회전수_rpm", "센서위치"))
        w.writerow(("EQ-A01", "예시 펌프 A-1", "1800", "모터측 베어링"))
        w.writerow(("EQ-A02", "예시 펌프 A-2", "1800", "모터측 베어링"))
        w.writerow(("EQ-B01", "예시 송풍기 B-1", "1200", "팬측 베어링"))
    print("예시 데이터를 %s 에 만들었습니다." % OUT)


if __name__ == "__main__":
    main()
