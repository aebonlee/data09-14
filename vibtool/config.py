"""설정 파일(config/settings.json) 읽기."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SETTINGS = os.path.join(ROOT, "config", "settings.json")

PATH_KEYS = ("inbox_dir", "db_path", "report_dir")


def load_settings(path=None, overrides=None):
    """설정을 읽고, 상대 경로를 저장소 폴더 기준 절대 경로로 바꿉니다."""
    path = path or DEFAULT_SETTINGS
    with open(path, encoding="utf-8") as f:
        s = json.load(f)
    if overrides:
        s.update({k: v for k, v in overrides.items() if v is not None})
    for key in PATH_KEYS:
        if key in s and not os.path.isabs(s[key]):
            s[key] = os.path.join(ROOT, s[key])
    s.setdefault("required_sensors", sorted(s.get("sensors", {}).keys()))
    s.setdefault("missing_policy", "reject")
    s.setdefault("csv_encodings", ["utf-8-sig", "cp949"])
    return s
