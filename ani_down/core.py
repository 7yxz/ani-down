import difflib
import re
import sys
from contextlib import nullcontext

from .providers import PROVIDERS
from .ui import console, error


def clean_title(title):
    return re.sub(r"\s*\([^)]*\)\s*$", "", title).strip()


FALLBACKS = list(PROVIDERS)


def _status(msg, quiet=False):
    return nullcontext() if quiet else console.status(msg)


def _msg(e):
    m = e.code if isinstance(e, SystemExit) else e
    return str(m or type(e).__name__)[:120]


def _sim(a, b):
    n = lambda x: re.sub(r"[^a-z0-9 ]", "", re.sub(r"\(.*?\)", "", x.lower())).strip()
    return difflib.SequenceMatcher(None, n(a), n(b)).ratio()


def search_providers(q, a):
    """Search the chosen provider; if it fails or finds nothing, quietly try the others."""
    if a.all:
        names = [n for n, c in PROVIDERS.items() if c.in_all]
    else:
        names = [a.provider] + [n for n in FALLBACKS if n != a.provider]
    results, errs = [], []
    for n in names:
        try:
            with console.status(f"Searching {n}..."):
                found = PROVIDERS[n]().search(q)
        except (Exception, SystemExit) as e:
            errs.append((n, _msg(e)))
            continue
        if not found:
            errs.append((n, "no results"))
            continue
        results += [(f"[{n}] {t}", (n, i, t)) for t, i in found]
        if not a.all:
            if errs:
                console.print(f"[dim]{errs[0][0]} failed ({errs[0][1][:60]}), using {n}[/]")
            break
    if not results:
        error("all providers failed")
        for n, m in errs:
            console.print(f"  [dim]{n}:[/] {m}")
        console.print("  [dim]try another provider with -p, or check your connection[/]")
        sys.exit(1)
    return results


def get_stream(prov, prov_name, aid, epid, label, title, a, avoid=(), quiet=False):
    """Try the chosen provider, then the same episode on the other providers."""
    errs = []
    if prov_name not in avoid:
        try:
            with _status("Fetching stream...", quiet):
                return prov.stream(aid, epid, a.quality, a.dub), prov_name, errs
        except (Exception, SystemExit) as e:
            errs.append((prov_name, _msg(e)))
    n = ep_num(label)
    for name in FALLBACKS if n else []:
        if name == prov_name or name in avoid:
            continue
        try:
            with _status(f"Trying {name}...", quiet):
                p = PROVIDERS[name]()
                res = [r for r in p.search(title) if _sim(title, r[0]) >= 0.6]
                if not res:
                    raise RuntimeError("no matching title")
                best = max(res, key=lambda r: _sim(title, r[0]))
                ep = next((e for e in p.episodes(best[1]) if ep_num(e[0]) == n), None)
                if not ep:
                    raise RuntimeError(f"episode {n} not found")
                got = p.stream(best[1], ep[1], a.quality, a.dub)
            if not quiet:
                console.print(f"[dim]{prov_name} failed, using {name}: {best[0]}[/]")
            return got, name, errs
        except (Exception, SystemExit) as e:
            errs.append((name, _msg(e)))
    if avoid:  # nothing else worked, start over with every source
        return get_stream(prov, prov_name, aid, epid, label, title, a, quiet=quiet)
    return None, prov_name, errs


def ep_num(label):
    m = re.search(r"(\d+)(?:\.\d+)?$", label)
    return int(m.group(1)) if m else None
