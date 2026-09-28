import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from vibtool.config import load_settings  # noqa: E402


def temp_settings(**over):
    d = tempfile.mkdtemp(prefix="vibtest_")
    s = load_settings()
    s.update(db_path=os.path.join(d, "t.db"), inbox_dir=os.path.join(d, "inbox"),
             report_dir=os.path.join(d, "reports"))
    s.update(over)
    os.makedirs(s["inbox_dir"])
    return s, d


def write_csv(folder, name, header, rows):
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(",".join(header) + "\n")
        for r in rows:
            f.write(",".join(str(c) for c in r) + "\n")
    return path


def vib_rows(xs):
    """X 값 목록으로 진동 CSV 행을 만듭니다 (Y·Z 는 0)."""
    return [(i * 0.001, x, 0, 0) for i, x in enumerate(xs)]


VIB_HEADER = ("time_s", "ax", "ay", "az")
GYRO_HEADER = ("time_s", "gx", "gy", "gz")
