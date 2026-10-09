import re
import shutil
import subprocess
import sys

import requests

from . import __version__
from .ui import console, error, warn

REPO = "7yxz/ani-down"
RAW = f"https://raw.githubusercontent.com/{REPO}/main/ani_down/__init__.py"
ZIP = f"https://github.com/{REPO}/archive/refs/heads/main.zip"


def _key(v):
    return tuple(int(x) for x in re.findall(r"\d+", v))


def latest(timeout=15):
    r = requests.get(RAW, timeout=timeout)
    r.raise_for_status()
    return re.search(r'__version__\s*=\s*"([^"]+)"', r.text).group(1)


def upgrade(force=False):
    try:
        new = latest()
    except Exception as e:
        error(f"could not check for updates ({e})")
        return
    if _key(new) <= _key(__version__) and not force:
        console.print(f"[green]already up to date[/] (v{__version__})")
        return
    console.print(f"updating [dim]v{__version__}[/] -> [bold]v{new}[/]")
    if "pipx" in sys.prefix and shutil.which("pipx"):
        cmd = ["pipx", "install", "--force", ZIP]
    else:
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", ZIP]
    if subprocess.run(cmd).returncode == 0:
        console.print("[green]done[/], run ani-down -v to confirm")
    else:
        warn("upgrade failed. Try manually: pipx install --force " + ZIP)
