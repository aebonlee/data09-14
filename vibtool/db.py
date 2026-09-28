"""로컬 파일형 DB(SQLite) — 장비·측정·원본 파일·결과·판정·실행 이력."""
import json
import os
import sqlite3
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS equipment (          -- 장비
  equipment_id TEXT PRIMARY KEY,                -- 장비 ID
  name         TEXT,                            -- 장비명
  params_json  TEXT NOT NULL DEFAULT '{}',      -- 파라미터(항목: 값)
  updated_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS measurement (        -- 측정
  measurement_id INTEGER PRIMARY KEY,
  equipment_id   TEXT NOT NULL REFERENCES equipment(equipment_id),
  measured_at    TEXT NOT NULL,                 -- 측정 일시
  status         TEXT NOT NULL,                 -- 대기(짝 파일 기다림) / 완료 / 오류
  status_note    TEXT,
  is_sample      INTEGER NOT NULL DEFAULT 0,    -- 예시 데이터 여부
  created_at     TEXT NOT NULL,
  UNIQUE (equipment_id, measured_at)
);
CREATE TABLE IF NOT EXISTS source_file (        -- 원본 파일(처리한 파일)
  file_id        INTEGER PRIMARY KEY,
  measurement_id INTEGER NOT NULL REFERENCES measurement(measurement_id),
  sensor         TEXT NOT NULL,                 -- vib / gyro
  path           TEXT NOT NULL,                 -- 원본 파일 경로
  sha256         TEXT NOT NULL,                 -- 파일 내용 지문(같은 파일 두 번 넣기 확인)
  row_count      INTEGER NOT NULL,
  registered_at  TEXT NOT NULL,
  UNIQUE (measurement_id, sensor)              -- 측정 건·센서마다 파일 하나
);
CREATE TABLE IF NOT EXISTS result (             -- 결과
  measurement_id    INTEGER NOT NULL REFERENCES measurement(measurement_id),
  item              TEXT NOT NULL,              -- 결과 항목 이름
  value             REAL NOT NULL,
  unit              TEXT,
  algorithm_version TEXT NOT NULL,
  PRIMARY KEY (measurement_id, item)
);
CREATE TABLE IF NOT EXISTS judgement (          -- 판정
  measurement_id     INTEGER PRIMARY KEY REFERENCES measurement(measurement_id),
  grade              TEXT NOT NULL,             -- 정상 / 주의 / 고장 / 판정 불가
  basis              TEXT NOT NULL,             -- 근거 항목
  thresholds_version TEXT NOT NULL,             -- 적용 기준 버전
  algorithm_version  TEXT NOT NULL,
  judged_at          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_log (            -- 실행 이력
  run_id             INTEGER PRIMARY KEY,
  started_at         TEXT NOT NULL,
  finished_at        TEXT,
  trigger            TEXT NOT NULL,             -- 수동(start) 등
  inbox              TEXT,
  algorithm_version  TEXT,
  thresholds_version TEXT,
  files_seen         INTEGER DEFAULT 0,
  files_registered   INTEGER DEFAULT 0,
  files_skipped      INTEGER DEFAULT 0,
  files_failed       INTEGER DEFAULT 0,
  measurements_done  INTEGER DEFAULT 0,
  messages           TEXT                       -- 파일별 건너뜀·오류 사유(JSON)
);
"""


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect(path):
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def upsert_equipment(conn, equipment_id, name=None, params=None):
    row = conn.execute("SELECT name, params_json FROM equipment WHERE equipment_id=?",
                       (equipment_id,)).fetchone()
    if row:
        merged = json.loads(row["params_json"])
        merged.update(params or {})
        conn.execute("UPDATE equipment SET name=?, params_json=?, updated_at=? WHERE equipment_id=?",
                     (name if name is not None else row["name"],
                      json.dumps(merged, ensure_ascii=False), now(), equipment_id))
    else:
        conn.execute("INSERT INTO equipment VALUES (?,?,?,?)",
                     (equipment_id, name, json.dumps(params or {}, ensure_ascii=False), now()))


def get_params(conn, equipment_id):
    row = conn.execute("SELECT params_json FROM equipment WHERE equipment_id=?",
                       (equipment_id,)).fetchone()
    return json.loads(row["params_json"]) if row else {}


def list_equipment(conn):
    return [dict(r, params=json.loads(r["params_json"]))
            for r in conn.execute("SELECT * FROM equipment ORDER BY equipment_id")]
