"""판정 규칙 — 결과 항목별 주의·고장 임계값, 가장 나쁜 항목 기준."""
from fnmatch import fnmatchcase

GRADES = ["정상", "주의", "고장"]
NO_GRADE = "판정 불가"


def find_threshold(item, thresholds):
    """정확히 같은 이름을 먼저, 없으면 * 패턴을 설정 순서대로 찾습니다."""
    items = thresholds.get("items", {})
    if item in items:
        return items[item]
    for pattern, t in items.items():
        if "*" in pattern or "?" in pattern:
            if fnmatchcase(item, pattern):
                return t
    return None


def grade_value(value, t, higher_is_worse=True):
    warn, fault = t.get("warn"), t.get("fault")
    if higher_is_worse:
        if fault is not None and value >= fault:
            return "고장"
        if warn is not None and value >= warn:
            return "주의"
    else:
        if fault is not None and value <= fault:
            return "고장"
        if warn is not None and value <= warn:
            return "주의"
    return "정상"


def judge(results, thresholds):
    """results: [{"name","value","unit"}] → (등급, 근거 목록, 항목별 등급 dict)."""
    hiw = thresholds.get("higher_is_worse", True)
    per_item = {}
    for r in results:
        t = find_threshold(r["name"], thresholds)
        if t is None:
            continue
        per_item[r["name"]] = grade_value(r["value"], t, hiw)
    if not per_item:
        return NO_GRADE, [], per_item
    worst = max(per_item.values(), key=GRADES.index)
    if worst == "정상":
        basis = ["판정 항목 %d개 모두 주의 기준 미만" % len(per_item)]
    else:
        vals = {r["name"]: r for r in results}
        basis = []
        for name, g in per_item.items():
            if g == worst:
                t = find_threshold(name, thresholds)
                lim = t["fault"] if worst == "고장" else t["warn"]
                basis.append("%s = %s (%s 기준 %s)" % (name, fmt(vals[name]["value"]), worst, fmt(lim)))
    return worst, basis, per_item


def fmt(v):
    return ("%.4g" % v) if isinstance(v, float) else str(v)
