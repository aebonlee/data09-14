#!/usr/bin/env python3
"""진동·각속도 데이터 분석 결과 DB화 도구 — 명령 모음 (폐쇄망용, 인터넷 불필요).

사용 예:
  python tool.py init                      DB·폴더 만들기
  python tool.py columns 파일.csv          CSV 열과 설정의 열 매핑 대조
  python tool.py equipment import 장비.csv 장비 정보 가져오기
  python tool.py equipment set --id EQ-A01 회전수_rpm=1800   장비 파라미터 고치기
  python tool.py run                       입력 폴더의 새 CSV 처리 (start)
  python tool.py status                    측정 건·판정 목록
  python tool.py report --from 2026-09-01 --to 2026-09-30
  python tool.py demo                      예시 데이터 불러오기 (별도 예시 DB)
"""
import argparse
import glob
import json
import os
import shutil
import sys

from vibtool import db as dbm
from vibtool.config import ROOT, load_settings
from vibtool.ingest import column_report, parse_file_name, read_csv
from vibtool.pipeline import rejudge, run_inbox
from vibtool.report import make_report

SAMPLES = os.path.join(ROOT, "samples")


def open_db(s):
    return dbm.connect(s["db_path"])


def cmd_init(s, a):
    os.makedirs(s["inbox_dir"], exist_ok=True)
    os.makedirs(s["report_dir"], exist_ok=True)
    open_db(s).close()
    print("준비했습니다.\n  DB: %s\n  입력 폴더: %s\n  보고서 폴더: %s" % (s["db_path"], s["inbox_dir"], s["report_dir"]))


def cmd_columns(s, a):
    name = os.path.basename(a.file)
    sensor = a.sensor
    info = parse_file_name(name, s)
    if not sensor:
        sensor = info["sensor"] if info else None
    if info:
        print("파일 이름 해석: 장비 %(equipment_id)s · 측정 일시 %(measured_at)s · 센서 %(sensor)s" % info)
    else:
        print("파일 이름이 규칙(file_name_pattern)에 맞지 않습니다. 설정의 규칙을 고치거나 파일 이름을 바꾸십시오.")
    header, rows = read_csv(a.file, s["csv_encodings"])
    print("파일의 열(%d개): %s" % (len(header), ", ".join(header)))
    print("데이터 행: %d" % len(rows))
    if not sensor:
        print("센서를 알 수 없어 매핑을 대조하지 않았습니다. --sensor vib 또는 --sensor gyro 를 붙이십시오.")
        return 1
    print("\n[%s] 설정의 열 매핑 대조" % s["sensors"][sensor]["label"])
    ok = True
    for label, col, found in column_report(header, s["sensors"][sensor]):
        print("  %-6s → %-12s %s" % (label, col, "있음" if found else "없음 — settings.json 에서 열 이름을 고치십시오"))
        ok = ok and found
    return 0 if ok else 1


def cmd_equipment(s, a):
    conn = open_db(s)
    if a.action == "import":
        header, rows = read_csv(a.file, s["csv_encodings"])
        idc, nmc = s["equipment_file"]["id_column"], s["equipment_file"].get("name_column")
        if idc not in header:
            print("장비 ID 열 「%s」이 없습니다. 파일의 열: %s" % (idc, ", ".join(header)))
            return 1
        n = 0
        for row in rows:
            rec = dict(zip(header, [c.strip() for c in row]))
            eid = rec.pop(idc, "")
            if not eid:
                continue
            name = rec.pop(nmc, None) if nmc else None
            dbm.upsert_equipment(conn, eid, name, {k: v for k, v in rec.items() if k and v != ""})
            n += 1
        conn.commit()
        print("장비 %d건을 가져왔습니다." % n)
    elif a.action == "set":
        params = {}
        for kv in a.params:
            if "=" not in kv:
                print("항목=값 형식으로 적으십시오: %s" % kv)
                return 1
            k, v = kv.split("=", 1)
            params[k.strip()] = v.strip()
        dbm.upsert_equipment(conn, a.id, a.name, params)
        conn.commit()
        print("저장했습니다: %s" % a.id)
    else:
        for e in dbm.list_equipment(conn):
            print("%s  %s  %s" % (e["equipment_id"], e["name"] or "(장비명 없음)",
                                  json.dumps(e["params"], ensure_ascii=False)))
    return 0


def print_run(r):
    print("실행 #%d 완료 — 알고리즘 %s · 판정 기준 %s" % (r["run_id"], r["algorithm_version"], r["thresholds_version"]))
    print("  파일: 확인 %(files_seen)d · 등록 %(files_registered)d · 건너뜀 %(files_skipped)d · 실패 %(files_failed)d" % r)
    print("  계산·판정한 측정 건: %d" % r["measurements_done"])
    for m in r["messages"]:
        print("  [%s] %s %s" % (m["구분"], m["파일"], m["내용"]))


def cmd_run(s, a):
    conn = open_db(s)
    r = run_inbox(conn, s, a.inbox)
    print_run(r)
    return 0


def cmd_status(s, a):
    conn = open_db(s)
    q = ("SELECT m.measured_at, m.equipment_id, m.status, m.status_note, j.grade, j.basis "
         "FROM measurement m LEFT JOIN judgement j USING (measurement_id) ORDER BY m.measured_at, m.equipment_id")
    rows = conn.execute(q).fetchall()
    if not rows:
        print("등록된 측정 건이 없습니다.")
    for r in rows:
        if a.grade and r["grade"] != a.grade:
            continue
        tail = r["grade"] + ("  " + r["basis"] if r["grade"] not in ("정상",) else "") if r["status"] == "완료" \
            else "%s — %s" % (r["status"], r["status_note"] or "")
        print("%s  %-8s %s" % (r["measured_at"], r["equipment_id"], tail))
    return 0


def cmd_log(s, a):
    conn = open_db(s)
    for r in conn.execute("SELECT * FROM run_log ORDER BY run_id DESC LIMIT ?", (a.limit,)):
        print("#%d %s [%s] 등록 %s · 건너뜀 %s · 실패 %s · 판정 %s · 알고리즘 %s · 기준 %s" % (
            r["run_id"], r["started_at"], r["trigger"], r["files_registered"], r["files_skipped"],
            r["files_failed"], r["measurements_done"], r["algorithm_version"] or "-", r["thresholds_version"]))
        for m in json.loads(r["messages"] or "[]"):
            print("     [%s] %s %s" % (m["구분"], m["파일"], m["내용"]))
    return 0


def cmd_rejudge(s, a):
    n = rejudge(open_db(s), s)
    print("측정 건 %d개를 판정 기준 「%s」로 다시 판정했습니다." % (n, s["thresholds"].get("version")))
    return 0


def cmd_report(s, a):
    data, h, x = make_report(open_db(s), s, a.date_from, a.date_to, a.equipment, a.out)
    print("보고서를 만들었습니다 (측정 건 %d · 주의·고장 %d).\n  HTML: %s" % (len(data["done"]), len(data["alerts"]), h))
    print("  엑셀: %s" % (x or "openpyxl 이 없어 만들지 않았습니다 — README 「실행 방법」 참고"))
    return 0


def cmd_demo(s, a):
    demo = os.path.join(ROOT, "data", "demo")
    if os.path.isdir(demo):
        shutil.rmtree(demo)
    s = dict(s, db_path=os.path.join(demo, "예시데이터.db"), inbox_dir=os.path.join(demo, "inbox"),
             report_dir=os.path.join(demo, "reports"))
    os.makedirs(s["inbox_dir"])
    for f in glob.glob(os.path.join(SAMPLES, "예시데이터_EQ-*.csv")):
        shutil.copy(f, s["inbox_dir"])
    print("예시 데이터 불러오기 — 가상 측정 파일로 전체 흐름을 한 번 돌립니다 (실제 DB 와 따로 %s 에 만듭니다)." % demo)
    a.file = os.path.join(SAMPLES, "예시데이터_장비정보.csv")
    a.action = "import"
    cmd_equipment(s, a)
    print_run(run_inbox(open_db(s), s))
    print()
    cmd_status(s, argparse.Namespace(grade=None))
    print()
    cmd_report(s, argparse.Namespace(date_from=None, date_to=None, equipment=None, out=None))
    return 0


def build_parser():
    p = argparse.ArgumentParser(description="진동·각속도 데이터 분석 결과 DB화 도구 (1단계)")
    p.add_argument("--config", help="설정 파일 경로 (기본: config/settings.json)")
    p.add_argument("--db", help="DB 파일 경로 (설정값 대신)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="DB·폴더 만들기")
    c = sub.add_parser("columns", help="CSV 열과 열 매핑 대조")
    c.add_argument("file")
    c.add_argument("--sensor", choices=["vib", "gyro"])
    e = sub.add_parser("equipment", help="장비 정보 (import/list/set)")
    e.add_argument("action", choices=["import", "list", "set"])
    e.add_argument("args", nargs="*", default=[], help="import: 장비 정보 CSV / set: 항목=값 ...")
    e.add_argument("--id", help="set: 장비 ID")
    e.add_argument("--name", help="set: 장비명")
    r = sub.add_parser("run", help="입력 폴더의 새 CSV 처리 (start)")
    r.add_argument("--inbox", help="입력 폴더 (설정값 대신)")
    st = sub.add_parser("status", help="측정 건·판정 목록")
    st.add_argument("--grade", choices=["정상", "주의", "고장", "판정 불가"])
    lg = sub.add_parser("log", help="실행 이력")
    lg.add_argument("--limit", type=int, default=10)
    sub.add_parser("rejudge", help="현재 판정 기준으로 다시 판정")
    rp = sub.add_parser("report", help="해석 결과보고서 (HTML·엑셀)")
    rp.add_argument("--from", dest="date_from", help="시작일 YYYY-MM-DD")
    rp.add_argument("--to", dest="date_to", help="종료일 YYYY-MM-DD")
    rp.add_argument("--equipment", help="장비 ID")
    rp.add_argument("--out", help="보고서 폴더 (설정값 대신)")
    sub.add_parser("demo", help="예시 데이터 불러오기 (별도 예시 DB)")
    return p


def main(argv=None):
    parser = build_parser()
    a, extra = parser.parse_known_args(argv)
    if extra:
        # equipment set --id X 항목=값 … 처럼 옵션 뒤에 온 항목=값 을 받아 줍니다
        if a.cmd == "equipment" and all("=" in x and not x.startswith("-") for x in extra):
            a.args = list(a.args) + extra
        else:
            parser.error("알 수 없는 인자: %s" % " ".join(extra))
    s = load_settings(a.config, {"db_path": a.db})
    if a.cmd == "equipment":
        a.file = a.args[0] if a.args else None
        a.params = a.args
        if a.action == "import" and not a.file:
            print("가져올 장비 정보 CSV 파일을 적으십시오.")
            return 1
        if a.action == "set":
            if not a.id:
                print("--id 로 장비 ID 를 적으십시오.")
                return 1
    fn = {"init": cmd_init, "columns": cmd_columns, "equipment": cmd_equipment, "run": cmd_run,
          "status": cmd_status, "log": cmd_log, "rejudge": cmd_rejudge, "report": cmd_report,
          "demo": cmd_demo}[a.cmd]
    return fn(s, a) or 0


if __name__ == "__main__":
    sys.exit(main())
