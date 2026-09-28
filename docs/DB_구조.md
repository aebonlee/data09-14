# DB 구조 설명서 (1단계)

로컬 파일형 DB(SQLite) 파일 하나에 모두 담습니다. 기본 위치는 `data/vibration.db` 이고 `config/settings.json` 의 `db_path` 로 바꿉니다. 파일을 복사하면 그대로 백업·이동됩니다. 표 정의의 원본은 `vibtool/db.py` 의 `SCHEMA` 입니다.

표 이름은 기획서 8장의 한글 이름에 대응하는 영문 이름을 씁니다(SQL 도구에서 다루기 쉽게 하기 위함).

| 표 | 기획서 이름 | 한 행의 뜻 |
|---|---|---|
| `equipment` | 장비 | 장비 한 대 |
| `measurement` | 측정 | 한 장비의 한 측정 일시 (진동·각속도 파일 한 쌍) |
| `source_file` | (측정의 원본 파일 경로) | 등록한 CSV 파일 하나 |
| `result` | 결과 | 한 측정 건의 결과 항목 하나 |
| `judgement` | 판정 | 한 측정 건의 판정 |
| `run_log` | 실행 이력 | `run`·`rejudge` 실행 한 번 |

## equipment — 장비

| 열 | 형식 | 설명 |
|---|---|---|
| equipment_id | TEXT, 기본키 | 장비 ID. 파일 이름의 장비 부분과 같아야 연결됩니다 |
| name | TEXT | 장비명 |
| params_json | TEXT | 파라미터(항목: 값)를 JSON 으로. 항목은 정해 두지 않았습니다(기획서 10장 3번 확인 후 정리) |
| updated_at | TEXT | 마지막 수정 시각 |

## measurement — 측정

| 열 | 형식 | 설명 |
|---|---|---|
| measurement_id | INTEGER, 기본키 | 일련번호 |
| equipment_id | TEXT | 장비 |
| measured_at | TEXT | 측정 일시 `YYYY-MM-DD HH:MM:SS` (파일 이름에서 읽음) |
| status | TEXT | `대기`(짝 파일 기다림) / `완료` / `오류`(계산 실패 — 다음 실행 때 다시 시도) |
| status_note | TEXT | 대기·오류 사유 |
| is_sample | INTEGER | 예시 데이터 파일이면 1 |
| created_at | TEXT | 등록 시각 |

같은 장비·같은 측정 일시는 한 건만 있습니다(UNIQUE).

## source_file — 원본 파일

| 열 | 형식 | 설명 |
|---|---|---|
| file_id | INTEGER, 기본키 | 일련번호 |
| measurement_id | INTEGER | 측정 건 |
| sensor | TEXT | `vib`(진동) / `gyro`(각속도) |
| path | TEXT | 원본 파일 경로. 짝 파일이 늦게 오면 이 경로에서 다시 읽으므로 계산이 끝날 때까지 옮기지 않습니다 |
| sha256 | TEXT | 파일 내용 지문. 같은 파일을 다시 넣으면 건너뜁니다 |
| row_count | INTEGER | 계산에 쓴 데이터 행 수 |
| registered_at | TEXT | 등록 시각 |

측정 건·센서마다 파일은 하나입니다(UNIQUE). 내용이 다른 파일이 같은 자리에 오면 덮어쓰지 않고 오류로 남깁니다.

## result — 결과

| 열 | 형식 | 설명 |
|---|---|---|
| measurement_id | INTEGER | 측정 건 |
| item | TEXT | 결과 항목 이름 (임시 알고리즘: `vib_X_rms`, `gyro_Z_peak` 처럼 센서_축_통계) |
| value | REAL | 값 |
| unit | TEXT | 단위 |
| algorithm_version | TEXT | 계산한 알고리즘 `모듈@버전` |

기본키는 (measurement_id, item) 입니다.

## judgement — 판정

| 열 | 형식 | 설명 |
|---|---|---|
| measurement_id | INTEGER, 기본키 | 측정 건 |
| grade | TEXT | `정상` / `주의` / `고장` / `판정 불가`(기준이 설정된 항목이 없음) |
| basis | TEXT | 근거 항목 — 등급을 정한 항목과 값, 적용 기준 |
| thresholds_version | TEXT | 적용한 판정 기준 버전 (`settings.json` 의 `thresholds.version`) |
| algorithm_version | TEXT | 결과를 계산한 알고리즘 버전 |
| judged_at | TEXT | 판정 시각 |

## run_log — 실행 이력

| 열 | 형식 | 설명 |
|---|---|---|
| run_id | INTEGER, 기본키 | 일련번호 |
| started_at / finished_at | TEXT | 시작·종료 시각 |
| trigger | TEXT | `수동(start)` / `재판정` |
| inbox | TEXT | 처리한 입력 폴더 |
| algorithm_version / thresholds_version | TEXT | 이 실행에 쓴 알고리즘·판정 기준 버전 |
| files_seen / files_registered / files_skipped / files_failed | INTEGER | 파일 수: 확인 / 등록 / 건너뜀(이미 처리) / 실패 |
| measurements_done | INTEGER | 계산·판정을 마친 측정 건 수 |
| messages | TEXT | 파일별 건너뜀·경고·오류·대기 사유(JSON 목록) |
