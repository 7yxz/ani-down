import json
import os
from pathlib import Path

DIR = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "ani-down"
FILE = DIR / "config.json"


def load():
    try:
        return json.loads(FILE.read_text())
    except Exception:
        return {}


def save(cfg):
    DIR.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(cfg, indent=2))
    os.chmod(FILE, 0o600)  # holds tokens
