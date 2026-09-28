"""CSV 가져오기 — 파일 이름 해석, 읽기, 형식 확인."""
import csv
import hashlib
import math
import re
from datetime import datetime


def parse_file_name(file_name, settings):
    """파일 이름에서 장비·측정 일시·센서를 꺼냅니다. 규칙에 안 맞으면 None."""
    m = re.match(settings["file_name_pattern"], file_name)
    if not m:
        return None
    try:
        dt = datetime.strptime(m.group("datetime"), settings["datetime_format"])
    except ValueError:
        return None
    sensor = m.group("sensor")
    if sensor not in settings["sensors"]:
        return None
    return {
        "equipment_id": m.group("equipment"),
        "measured_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "sensor": sensor,
        "is_sample": file_name.startswith("예시데이터_"),
    }


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path, encodings=("utf-8-sig", "cp949")):
    """(머리행, 행 목록)을 돌려줍니다. 인코딩은 순서대로 시도합니다."""
    last = None
    for enc in encodings:
        try:
            with open(path, encoding=enc, newline="") as f:
                rows = list(csv.reader(f))
            break
        except UnicodeDecodeError as e:
            last = e
    else:
        raise ValueError("파일 인코딩을 읽지 못했습니다: %s" % last)
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("빈 파일입니다.")
    header = [c.strip() for c in rows[0]]
    return header, rows[1:]


def _num(text):
    text = (text or "").strip()
    if text == "":
        return None
    try:
        v = float(text)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def validate(header, rows, sensor_cfg, missing_policy="reject"):
    """열 매핑에 따라 값을 꺼내고 확인합니다.

    돌려주는 값: (data, errors, warnings)
    data = {"time": [...], "channels": {"X": [...], ...}} — errors 가 있으면 None
    """
    errors, warnings = [], []
    needed = {"시각": sensor_cfg["time_column"]}
    for axis, col in sensor_cfg["channels"].items():
        needed[axis] = col
    idx = {}
    for label, col in needed.items():
        if col not in header:
            errors.append("필수 열 「%s」(%s)이 없습니다. 파일의 열: %s"
                          % (col, label, ", ".join(header)))
        else:
            idx[label] = header.index(col)
    if errors:
        return None, errors, warnings

    time, chans = [], {a: [] for a in sensor_cfg["channels"]}
    missing_rows = []
    for n, row in enumerate(rows, start=2):  # 2 = 머리행 다음 줄
        vals = {}
        for label, i in idx.items():
            vals[label] = _num(row[i]) if i < len(row) else None
        if any(v is None for v in vals.values()):
            missing_rows.append(n)
            continue
        time.append(vals["시각"])
        for a in chans:
            chans[a].append(vals[a])

    if missing_rows:
        msg = "빈 값·숫자가 아닌 값이 있는 행 %d개 (첫 행: %s)" % (
            len(missing_rows), ", ".join(str(r) for r in missing_rows[:5]))
        if missing_policy == "drop_rows":
            warnings.append(msg + " — 해당 행을 빼고 계산했습니다.")
        else:
            errors.append(msg)
    if len(time) < 2:
        errors.append("계산할 수 있는 데이터 행이 2개 미만입니다.")
    for k in range(1, len(time)):
        if time[k] <= time[k - 1]:
            errors.append("시각이 증가하지 않는 행이 있습니다 (데이터 %d번째 행)." % (k + 1))
            break
    if errors:
        return None, errors, warnings
    return {"time": time, "channels": chans}, errors, warnings


def column_report(header, sensor_cfg):
    """열 매핑 확인용 — 설정의 각 열이 파일에 있는지 표로 돌려줍니다."""
    out = [("시각", sensor_cfg["time_column"], sensor_cfg["time_column"] in header)]
    for axis, col in sensor_cfg["channels"].items():
        out.append((axis + "축", col, col in header))
    return out
