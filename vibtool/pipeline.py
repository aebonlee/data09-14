"""실행(start) — 입력 폴더의 새 CSV 를 등록하고, 짝이 갖춰진 측정 건을 계산·판정해 DB 에 저장."""
import json
import os

from . import db as dbm
from .connector import call_algorithm, load_algorithm
from .ingest import file_sha256, parse_file_name, read_csv, validate
from .judge import judge


def _load_sensor(path, sensor, settings):
    header, rows = read_csv(path, settings["csv_encodings"])
    return validate(header, rows, settings["sensors"][sensor], settings["missing_policy"])


def run_inbox(conn, settings, inbox=None, trigger="수동(start)"):
    inbox = inbox or settings["inbox_dir"]
    fn, algo_version = load_algorithm(settings)
    th = settings["thresholds"]
    th_version = th.get("version", "버전 미표기")
    started = dbm.now()
    cur = conn.execute(
        "INSERT INTO run_log (started_at, trigger, inbox, algorithm_version, thresholds_version) "
        "VALUES (?,?,?,?,?)", (started, trigger, inbox, algo_version, th_version))
    run_id = cur.lastrowid
    conn.commit()

    stat = {"files_seen": 0, "files_registered": 0, "files_skipped": 0,
            "files_failed": 0, "measurements_done": 0}
    messages = []
    cache = {}

    def note(kind, name, text):
        messages.append({"구분": kind, "파일": name, "내용": text})

    names = sorted(n for n in os.listdir(inbox) if n.lower().endswith(".csv")) \
        if os.path.isdir(inbox) else []
    if not os.path.isdir(inbox):
        note("오류", "", "입력 폴더가 없습니다: %s" % inbox)
    elif not names:
        note("안내", "", "입력 폴더에 CSV 파일이 없습니다: %s" % inbox)

    for name in names:
        path = os.path.join(inbox, name)
        stat["files_seen"] += 1
        info = parse_file_name(name, settings)
        if info is None:
            stat["files_failed"] += 1
            note("오류", name, "파일 이름이 규칙(file_name_pattern)에 맞지 않습니다.")
            continue
        digest = file_sha256(path)
        eq = info["equipment_id"]
        m = conn.execute("SELECT measurement_id FROM measurement WHERE equipment_id=? AND measured_at=?",
                         (eq, info["measured_at"])).fetchone()
        if m is not None:
            prev = conn.execute("SELECT sha256 FROM source_file WHERE measurement_id=? AND sensor=?",
                                (m["measurement_id"], info["sensor"])).fetchone()
            if prev is not None:
                if prev["sha256"] == digest:
                    stat["files_skipped"] += 1
                    note("건너뜀", name, "이미 처리한 파일입니다.")
                else:
                    stat["files_failed"] += 1
                    note("오류", name, "같은 측정 건·센서의 다른 파일이 이미 등록되어 있습니다(내용이 다름). 덮어쓰지 않았습니다.")
                continue
        try:
            data, errors, warnings = _load_sensor(path, info["sensor"], settings)
        except ValueError as e:
            data, errors, warnings = None, [str(e)], []
        for w in warnings:
            note("경고", name, w)
        if errors:
            stat["files_failed"] += 1
            for e in errors:
                note("오류", name, e)
            continue
        if conn.execute("SELECT 1 FROM source_file WHERE sha256=?", (digest,)).fetchone():
            note("경고", name, "내용이 똑같은 파일이 다른 측정 건에 이미 있습니다. 파일을 잘못 복사하지 않았는지 확인하십시오.")

        if not conn.execute("SELECT 1 FROM equipment WHERE equipment_id=?", (eq,)).fetchone():
            dbm.upsert_equipment(conn, eq, None, {})
            note("경고", name, "미등록 장비 %s 를 파라미터 없이 등록했습니다. 장비 정보를 가져오십시오." % eq)
        if m is None:
            mid = conn.execute(
                "INSERT INTO measurement (equipment_id, measured_at, status, is_sample, created_at) "
                "VALUES (?,?,?,?,?)", (eq, info["measured_at"], "대기", int(info["is_sample"]), dbm.now())).lastrowid
        else:
            mid = m["measurement_id"]
        conn.execute("INSERT INTO source_file (measurement_id, sensor, path, sha256, row_count, registered_at) "
                     "VALUES (?,?,?,?,?,?)", (mid, info["sensor"], os.path.abspath(path), digest,
                                              len(data["time"]), dbm.now()))
        conn.commit()
        cache[os.path.abspath(path)] = data
        stat["files_registered"] += 1

    # 짝이 갖춰진 측정 건 계산 (대기·오류 건은 매 실행마다 다시 봄)
    required = settings["required_sensors"]
    pending = conn.execute("SELECT * FROM measurement WHERE status IN ('대기','오류') "
                           "ORDER BY measured_at, equipment_id").fetchall()
    for m in pending:
        mid = m["measurement_id"]
        files = {r["sensor"]: r for r in conn.execute(
            "SELECT * FROM source_file WHERE measurement_id=?", (mid,))}
        lack = [s for s in required if s not in files]
        label = "%s %s" % (m["equipment_id"], m["measured_at"])
        if lack:
            txt = "짝 파일 대기: " + ", ".join(settings["sensors"][s]["label"] for s in lack)
            conn.execute("UPDATE measurement SET status='대기', status_note=? WHERE measurement_id=?", (txt, mid))
            conn.commit()
            note("대기", label, txt)
            continue
        try:
            sensors = {}
            for s, f in files.items():
                data = cache.get(f["path"])
                if data is None:
                    if not os.path.exists(f["path"]):
                        raise ValueError("원본 파일을 찾을 수 없습니다: %s" % f["path"])
                    data, errors, _ = _load_sensor(f["path"], s, settings)
                    if errors:
                        raise ValueError("; ".join(errors))
                sensors[s] = {"unit": settings["sensors"][s]["unit"],
                              "time": data["time"], "channels": data["channels"]}
            measurement = {"equipment_id": m["equipment_id"], "measured_at": m["measured_at"],
                           "sensors": sensors}
            results = call_algorithm(fn, measurement, dbm.get_params(conn, m["equipment_id"]))
            grade, basis, _ = judge(results, th)
            conn.execute("DELETE FROM result WHERE measurement_id=?", (mid,))
            conn.executemany("INSERT INTO result VALUES (?,?,?,?,?)",
                             [(mid, r["name"], r["value"], r["unit"], algo_version) for r in results])
            conn.execute("INSERT OR REPLACE INTO judgement VALUES (?,?,?,?,?,?)",
                         (mid, grade, "; ".join(basis), th_version, algo_version, dbm.now()))
            conn.execute("UPDATE measurement SET status='완료', status_note=NULL WHERE measurement_id=?", (mid,))
            conn.commit()
            stat["measurements_done"] += 1
        except Exception as e:  # 알고리즘 오류는 이 측정 건만 오류로 두고 계속 진행
            conn.rollback()
            conn.execute("UPDATE measurement SET status='오류', status_note=? WHERE measurement_id=?",
                         (str(e)[:500], mid))
            conn.commit()
            note("오류", label, "계산 실패: %s" % e)

    conn.execute("UPDATE run_log SET finished_at=?, files_seen=?, files_registered=?, files_skipped=?, "
                 "files_failed=?, measurements_done=?, messages=? WHERE run_id=?",
                 (dbm.now(), stat["files_seen"], stat["files_registered"], stat["files_skipped"],
                  stat["files_failed"], stat["measurements_done"],
                  json.dumps(messages, ensure_ascii=False), run_id))
    conn.commit()
    stat.update(run_id=run_id, messages=messages, algorithm_version=algo_version,
                thresholds_version=th_version)
    return stat


def rejudge(conn, settings):
    """저장된 결과 값에 현재 설정의 판정 기준을 다시 적용합니다(기준 변경 시)."""
    th = settings["thresholds"]
    th_version = th.get("version", "버전 미표기")
    started = dbm.now()
    n = 0
    for m in conn.execute("SELECT measurement_id FROM measurement WHERE status='완료'").fetchall():
        mid = m["measurement_id"]
        rows = conn.execute("SELECT item, value, unit, algorithm_version FROM result WHERE measurement_id=?",
                            (mid,)).fetchall()
        results = [{"name": r["item"], "value": r["value"], "unit": r["unit"]} for r in rows]
        grade, basis, _ = judge(results, th)
        conn.execute("INSERT OR REPLACE INTO judgement VALUES (?,?,?,?,?,?)",
                     (mid, grade, "; ".join(basis), th_version, rows[0]["algorithm_version"], dbm.now()))
        n += 1
    conn.execute("INSERT INTO run_log (started_at, finished_at, trigger, thresholds_version, measurements_done, messages) "
                 "VALUES (?,?,?,?,?,?)", (started, dbm.now(), "재판정", th_version, n, "[]"))
    conn.commit()
    return n
