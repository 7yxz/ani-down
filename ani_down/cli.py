"""ani-down: download anime episodes from your terminal."""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from rich import box
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

from . import __version__
from .core import clean_title, ep_num, get_stream, search_providers
from .providers import PROVIDERS
from .ui import Prompt, console, error, pick
from .upgrade import upgrade
from .utils import hint_install

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
COMMON = ["-allowed_extensions", "ALL", "-protocol_whitelist", "file,http,https,tcp,tls,crypto"]
PROCS, PLOCK, SLOCK = set(), threading.Lock(), threading.Lock()


def build_parser():
    ap = argparse.ArgumentParser(
        prog="ani-down", add_help=False, description="Download anime episodes from your terminal.",
        epilog="examples:\n  ani-down naruto\n  ani-down naruto -e 1-12 -j 3\n"
               "  ani-down naruto -e latest -f mp4 -q 720 -o ~/anime\n  ani-down naruto -e all --dry-run",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="*", help="search query")
    ap.add_argument("-p", "--provider", choices=PROVIDERS, default="hianime")
    ap.add_argument("-e", "--episodes", help="all, latest, 5, 1-5, 3-, 1,4,7-9 (asks if left out)")
    ap.add_argument("-q", "--quality", type=int, default=1080, help="preferred quality")
    ap.add_argument("-d", "--dub", action="store_true", default=False, help="dubbed audio")
    ap.add_argument("--sub", dest="dub", action="store_false", help="subbed audio")
    ap.add_argument("-o", "--output", default="~/Videos/anime", help="output folder")
    ap.add_argument("-f", "--format", choices=["mkv", "mp4"], default="mkv")
    ap.add_argument("-j", "--jobs", type=int, default=2, help="parallel downloads")
    ap.add_argument("--retries", type=int, default=2, help="retries per episode")
    ap.add_argument("--overwrite", action="store_true", help="redo files that already exist")
    ap.add_argument("--no-subs", action="store_true", help="do not add subtitles")
    ap.add_argument("--dry-run", action="store_true", help="only list what would be downloaded")
    ap.add_argument("--upgrade", action="store_true", help="upgrade ani-down from GitHub")
    ap.add_argument("-v", "--version", action="version", version=f"ani-down {__version__}")
    ap.add_argument("-h", "-help", "--help", action="help", help="show this help and exit")
    return ap


def parse_spec(spec, eps):
    """Turn 'all', 'latest', '5', '1-5', '3-', '1,4,7-9' into episode indexes."""
    nums, picked = [ep_num(l) for l, _ in eps], set()
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        m = re.fullmatch(r"(\d*)-(\d*)", part)
        if part == "all":
            picked.update(range(len(eps)))
        elif part in ("latest", "last"):
            picked.add(len(eps) - 1)
        elif m:
            lo = int(m.group(1)) if m.group(1) else None
            hi = int(m.group(2)) if m.group(2) else None
            picked.update(i for i, n in enumerate(nums) if n is not None
                          and (lo is None or n >= lo) and (hi is None or n <= hi))
        elif part.isdigit():
            picked.update(i for i, n in enumerate(nums) if n == int(part))
        else:
            raise ValueError(f"bad episode spec: {part}")
    return sorted(picked)


def choose(eps):
    if shutil.which("fzf"):
        lines = [f"{i}\t{l}" for i, (l, _) in enumerate(eps)]
        p = subprocess.run(
            ["fzf", "--multi", "--with-nth=2..", "--delimiter=\t", "--layout=reverse", "--border=rounded",
             "--cycle", "--bind=ctrl-a:select-all", "--prompt=episodes > ",
             "--header=tab: mark   ctrl-a: all   enter: download   esc: cancel",
             "--color=hl:magenta,hl+:magenta,pointer:cyan,prompt:cyan,border:magenta,header:dim"],
            input="\n".join(lines), text=True, stdout=subprocess.PIPE)
        idx = [int(l.split("\t")[0]) for l in p.stdout.splitlines() if l.strip()]
        if not idx:
            sys.exit(0)
        return idx
    return parse_spec(Prompt.ask("episodes (e.g. 1-5,8 / all / latest)", default="all"), eps)


def safe(s):
    return re.sub(r'[\\/:*?"<>|]+', "", s).strip(". ") or "anime"


def ep_tag(label, i):
    m = re.search(r"(\d+)(\.\d+)?$", label)
    return (m.group(1).zfill(2) + (m.group(2) or "")) if m else f"{i + 1:02d}"


def _hdr(h):
    return "".join(f"{k}: {v}\r\n" for k, v in (h or {}).items())


def probe(url, hdrs):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                            "default=nw=1:nk=1", "-user_agent", UA, "-headers", _hdr(hdrs), *COMMON, url],
                           capture_output=True, text=True, timeout=25)
        return float(r.stdout.strip())
    except Exception:
        return None


def ffmpeg_dl(url, hdrs, sub, out, fmt, progress, task):
    dur = probe(url, hdrs)
    progress.update(task, total=dur, completed=0)
    tmp = out.with_name(out.name + ".part")
    out.parent.mkdir(parents=True, exist_ok=True)
    last = "ffmpeg failed"
    for use_sub in ([True, False] if sub else [False]):
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-user_agent", UA,
               "-headers", _hdr(hdrs), *COMMON, "-i", url]
        if use_sub:
            cmd += ["-user_agent", UA, "-i", sub]
        cmd += ["-map", "0:v:0", "-map", "0:a:0?"] + (["-map", "1:0"] if use_sub else []) + ["-c", "copy"]
        if use_sub:
            cmd += ["-c:s", "mov_text" if fmt == "mp4" else "srt"]
        cmd += ["-f", "matroska" if fmt == "mkv" else "mp4", "-progress", "pipe:1", "-nostats", str(tmp)]
        err = tempfile.TemporaryFile()
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, text=True)
        with PLOCK:
            PROCS.add(p)
        for line in p.stdout:
            k, _, v = line.strip().partition("=")
            if k in ("out_time_us", "out_time_ms") and v.lstrip("-").isdigit():
                progress.update(task, completed=max(0, int(v)) / 1e6)
        rc = p.wait()
        with PLOCK:
            PROCS.discard(p)
        if rc == 0:
            tmp.replace(out)
            return
        err.seek(0)
        tail = err.read().decode(errors="replace").strip().splitlines()
        last = tail[-1] if tail else f"ffmpeg exited with {rc}"
    tmp.unlink(missing_ok=True)
    raise RuntimeError(last)


def _run():
    a = build_parser().parse_args()
    if a.upgrade:
        return upgrade()
    if not shutil.which("ffmpeg"):
        error(f"ffmpeg not found. Install it: {hint_install('ffmpeg')}")
        sys.exit(1)
    console.print(Panel.fit(f"[bold magenta]ani-down[/]  [dim]v{__version__}  |  download anime from your terminal[/]",
                            border_style="magenta", box=box.ROUNDED, padding=(0, 3)))
    q = " ".join(a.query) or Prompt.ask("[bold magenta]search anime[/]").strip()
    results = search_providers(q, SimpleNamespace(all=False, provider=a.provider))
    prov_name, aid, title = pick(results, "anime")
    prov = PROVIDERS[prov_name]()
    with console.status("Loading episodes..."):
        eps = prov.episodes(aid)
    if not eps:
        error("no episodes found")
        sys.exit(1)
    try:
        idx = parse_spec(a.episodes, eps) if a.episodes else choose(eps)
    except ValueError as e:
        error(e)
        sys.exit(1)
    if not idx:
        error("no matching episodes")
        sys.exit(1)

    name = safe(clean_title(title))
    base = Path(a.output).expanduser() / name
    plan = [(i, eps[i][0], eps[i][1], base / f"{name} - {ep_tag(eps[i][0], i)}.{a.format}") for i in idx]
    t = Table(box=box.SIMPLE_HEAD, header_style="bold cyan", title=f"{title}  ({prov_name}, {a.quality}p, "
                                                                     f"{'dub' if a.dub else 'sub'})")
    t.add_column("episode")
    t.add_column("file")
    for _, label, _, out in plan:
        t.add_row(label, f"[dim]{out}[/]" + ("  [yellow](exists)[/]" if out.exists() and not a.overwrite else ""))
    console.print(t)
    if a.dry_run:
        return

    ns = SimpleNamespace(quality=a.quality, dub=a.dub)
    results_ = []

    def job(prog, i, label, epid, out):
        tag = ep_tag(label, i)
        task = prog.add_task(f"[cyan]{tag}[/] waiting", total=None)
        if out.exists() and not a.overwrite:
            prog.update(task, description=f"[yellow]{tag} skipped (exists)[/]", total=1, completed=1)
            return ("skipped", label, "")
        last = ""
        for attempt in range(a.retries + 1):
            try:
                prog.update(task, description=f"[cyan]{tag}[/] getting stream")
                with SLOCK:  # provider sessions are shared, resolve one at a time
                    got, _, errs = get_stream(prov, prov_name, aid, epid, label, title, ns, quiet=True)
                if not got:
                    raise RuntimeError("; ".join(f"{n}: {m}" for n, m in errs)[:160])
                url, hdrs, sub = got
                prog.update(task, description=f"[cyan]{tag}[/] downloading" + (f" (try {attempt + 1})" if attempt else ""))
                ffmpeg_dl(url, hdrs, None if a.no_subs else sub, out, a.format, prog, task)
                done = prog.tasks[task].total or prog.tasks[task].completed or 1
                prog.update(task, description=f"[green]{tag} done[/]", total=done, completed=done)
                return ("done", label, "")
            except (Exception, SystemExit) as e:
                last = str(e.code if isinstance(e, SystemExit) else e)[:160]
                time.sleep(2)
        prog.update(task, description=f"[red]{tag} failed[/]")
        return ("failed", label, last)

    cols = (SpinnerColumn(), TextColumn("{task.description}", table_column=None), BarColumn(),
            TaskProgressColumn(), TimeRemainingColumn())
    ex = ThreadPoolExecutor(max_workers=max(1, a.jobs))
    try:
        with Progress(*cols, console=console) as prog:
            futs = [ex.submit(job, prog, i, l, e, o) for i, l, e, o in plan]
            results_ = [f.result() for f in futs]
    except KeyboardInterrupt:
        ex.shutdown(wait=False, cancel_futures=True)
        with PLOCK:
            for p in list(PROCS):
                p.terminate()
        console.print("\n[yellow]cancelled[/], partial files end in .part")
        sys.exit(130)
    ex.shutdown()

    s = Table(box=box.SIMPLE_HEAD, header_style="bold cyan", title="summary")
    s.add_column("episode")
    s.add_column("result")
    s.add_column("note")
    colors = {"done": "green", "skipped": "yellow", "failed": "red"}
    for st, label, note in results_:
        s.add_row(label, f"[{colors[st]}]{st}[/]", f"[dim]{note}[/]")
    console.print(s)
    console.print(f"saved in [bold]{base}[/]")
    if any(r[0] == "failed" for r in results_):
        sys.exit(1)


def main():
    try:
        _run()
    except (KeyboardInterrupt, EOFError):
        print()
