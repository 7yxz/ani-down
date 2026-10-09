"""Direct hianime scraper, no API server needed. Logic ported from ani-cli 5.1.x."""
import base64
import html as htmllib
import json
import os
import re
import sys
from urllib.parse import urljoin, urlparse

from ..mirrors import find_base
from ..ui import warn
from ..utils import IMPERSONATE, session

KEY = b"otaku-embed-v1"
MIRRORS = ["https://hianime.at", "https://hianime.to", "https://hianime.sx", "https://hianimez.to"]


def unxor(blob):
    raw = base64.b64decode(blob + "=" * (-len(blob) % 4))
    return bytes(b ^ KEY[i % len(KEY)] for i, b in enumerate(raw)).decode("utf-8", "replace")


class HiAnime:
    name = "hianime"
    in_all = True

    _base = None

    @property
    def base(self):
        if self._base:
            return self._base

        def probe(m):
            r = session.get(f"{m}/search", params={"keyword": "a"}, timeout=15)
            return r.status_code == 200 and "Just a moment" not in r.text[:3000] and "film-name" in r.text

        self._base = find_base("hianime", MIRRORS, probe, "HIANIME_URL")
        if not self._base:
            hint = "" if IMPERSONATE else " (pip install curl_cffi to bypass cloudflare)"
            sys.exit("hianime: no working mirror" + hint)
        return self._base

    def _get(self, url, **kw):
        r = session.get(url, timeout=20, **kw)
        if "Just a moment" in r.text[:3000]:
            hint = "" if IMPERSONATE else " (pip install curl_cffi to bypass)"
            sys.exit("hianime: blocked by cloudflare" + hint)
        r.raise_for_status()
        return r.text

    def search(self, q):
        page = self._get(f"{self.base}/search", params={"keyword": q})
        page = " ".join(page.split("id=\"main-sidebar\"")[0].split())
        return [(htmllib.unescape(m.group(2)), m.group(1)) for m in re.finditer(
            r'<h3 class="film-name">\s*<a href="[^"]*/([^"/]*)"\s*title="([^"]*)"', page)]

    def episodes(self, slug):
        num = slug.rsplit("-", 1)[-1]
        text = self._get(f"{self.base}/api/theme/episode/list/{num}").replace("\\", "")
        out = []
        for chunk in text.split("ep-item")[1:]:
            m = re.search(r'data-number="([^"]*)".*?data-id="(\d+)".*?/watch/'
                          + re.escape(slug) + r"\?ep=", chunk, re.S)
            if m:
                out.append((f"Episode {m.group(1)}", m.group(2)))
        return out

    def stream(self, _slug, ep_id, quality, dub=False):
        mode = "dub" if dub else "sub"
        servers = self._get(f"{self.base}/api/theme/episode/servers",
                            params={"episodeId": ep_id}).replace('\\"', '"')
        found = {}
        for chunk in servers.split("server-item")[1:]:
            t, n, hh = (re.search(r'data-%s="([^"]*)"' % k, chunk) for k in ("type", "server-name", "hash"))
            if t and n and hh and n.group(1) == "ZokoAnime":
                found.setdefault(t.group(1), hh.group(1))
        kind = next((k for k in (mode, "raw", "dub" if mode == "sub" else "sub") if k in found), None)
        if not kind:
            sys.exit(f"hianime: no {mode} source for this episode")
        if kind != mode:
            warn(f"hianime: no {mode} for this episode, using {kind}")
        h = found[kind]
        embed = base64.b64decode(h + "=" * (-len(h) % 4)).decode()
        u = urlparse(embed)
        refr = f"{u.scheme}://{u.netloc}/"
        page = self._get(embed)
        m = re.search(r'window\.__P="([^"]*)"', page)
        if not m:
            sys.exit("hianime: embed config not found (layout changed)")
        text = unxor(m.group(1))
        m = re.search(r'"src":"([^"]*\.m3u8[^"]*)"', text)
        if not m:
            sys.exit("hianime: no m3u8 in embed config")
        master = m.group(1).replace("\\/", "/")
        sub = None
        try:
            subs = json.loads(text).get("subtitles") or []
            sub = next((s["src"] for s in subs if s.get("default")), None)
        except Exception:
            pass
        url = master
        try:  # pick closest quality from the master playlist
            lines = self._get(master, headers={"Referer": refr}).splitlines()
            variants = []
            for i, l in enumerate(lines):
                r = re.search(r"RESOLUTION=\d+x(\d+)", l)
                if l.startswith("#EXT-X-STREAM-INF") and r and i + 1 < len(lines):
                    variants.append((int(r.group(1)), urljoin(master, lines[i + 1].strip())))
            if variants:
                url = min(variants, key=lambda v: abs(v[0] - quality))[1]
        except SystemExit:
            raise
        except Exception:
            pass
        return url, {"Referer": refr}, sub
