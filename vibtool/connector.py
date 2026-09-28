"""교체형 알고리즘 연결부 — 설정의 모듈을 불러 약속된 모양으로 결과를 받습니다."""
import importlib
import math


def load_algorithm(settings):
    cfg = settings["algorithm"]
    mod = importlib.import_module(cfg["module"])
    fn = getattr(mod, cfg.get("function", "run"))
    version = "%s@%s" % (cfg["module"], getattr(mod, "VERSION", "버전 미표기"))
    return fn, version


def call_algorithm(fn, measurement, params):
    """알고리즘을 부르고 결과 모양을 확인합니다. 잘못되면 ValueError."""
    results = fn(measurement, params)
    if not isinstance(results, list) or not results:
        raise ValueError("알고리즘 결과가 비어 있거나 목록이 아닙니다.")
    seen = set()
    clean = []
    for r in results:
        if not isinstance(r, dict) or "name" not in r or "value" not in r:
            raise ValueError("결과 항목에 name·value 가 없습니다: %r" % (r,))
        name = str(r["name"])
        if name in seen:
            raise ValueError("결과 항목 이름이 중복됩니다: %s" % name)
        seen.add(name)
        v = float(r["value"])
        if not math.isfinite(v):
            raise ValueError("결과 값이 숫자가 아닙니다: %s" % name)
        clean.append({"name": name, "value": v, "unit": str(r.get("unit", ""))})
    return clean
