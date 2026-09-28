"""교체형 연결부 시험용 가짜 알고리즘 — 진동 X 축 첫 값만 돌려줍니다."""
VERSION = "fake-9"


def run(measurement, params):
    x0 = measurement["sensors"]["vib"]["channels"]["X"][0]
    return [{"name": "custom_x0", "value": x0, "unit": "g"},
            {"name": "custom_rpm", "value": float(params.get("rpm", 0)), "unit": "rpm"}]
