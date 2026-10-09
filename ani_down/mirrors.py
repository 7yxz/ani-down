import os

from . import config


def find_base(name, candidates, probe, env=None):
    """Return the first working mirror. Order: env override, last working one, candidates.
    The working mirror is remembered in the config so next runs skip probing."""
    if env and os.environ.get(env):
        order = [os.environ[env].rstrip("/")]
    else:
        cached = config.load().get("mirrors", {}).get(name)
        order = ([cached] if cached else []) + [c for c in candidates if c != cached]
    for m in order:
        try:
            if probe(m):
                cfg = config.load()
                if not (env and os.environ.get(env)) and cfg.get("mirrors", {}).get(name) != m:
                    cfg.setdefault("mirrors", {})[name] = m
                    config.save(cfg)
                return m
        except Exception:
            continue
    return None
