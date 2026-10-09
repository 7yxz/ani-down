import os
import re
import sys

from ..mirrors import find_base
from ..utils import session, unpack_packer

MIRRORS = ["https://animepahe.pw", "https://animepahe.com", "https://animepahe.org",
           "https://animepahe.si", "https://animepahe.ru"]
# DDoS-Guard accepts these empty cookies, no manual cookie needed
DDG = "__ddg1_=;__ddg2_=;__ddgid_=;"


class AnimePahe:
    name = "animepahe"
    in_all = True
    _base = None

    def _headers(self, base):
        cookie = DDG + (os.environ.get("PAHE_COOKIE") or "")
        return {"Referer": base + "/", "Cookie": cookie}

    @property
    def base(self):
        """Find a working mirror and collect DDoS-Guard cookies automatically."""
        if self._base:
            return self._base

        def probe(m):
            try:  # first hit sets the cookies in the session
                session.get(m, headers=self._headers(m), timeout=15)
            except Exception:
                pass
            r = session.get(f"{m}/api", params={"m": "search", "q": "a"},
                            headers=self._headers(m), timeout=15)
            return r.status_code == 200 and "data" in r.json()

        self._base = find_base("animepahe", MIRRORS, probe, "PAHE_URL")
        if not self._base:
            sys.exit("animepahe: no working mirror (blocked?)")
        return self._base

    def _get(self, url, **kw):
        r = session.get(url, headers=self._headers(self.base), timeout=20, **kw)
        r.raise_for_status()
        return r

    def search(self, q):
        d = self._get(f"{self.base}/api", params={"m": "search", "q": q}).json()
        return [(f"{a['title']} ({a.get('year', '?')}, {a.get('episodes', '?')} eps)", a["session"])
                for a in d.get("data", [])]

    def episodes(self, sid):
        out, page = [], 1
        while True:
            d = self._get(f"{self.base}/api", params={
                "m": "release", "id": sid, "sort": "episode_asc", "page": page}).json()
            out += [(f"Episode {e['episode']}", f"{sid}/{e['session']}") for e in d["data"]]
            if page >= d.get("last_page", 1):
                break
            page += 1
        return out

    def stream(self, _sid, epid, quality, dub=False):
        html = self._get(f"{self.base}/play/{epid}").text
        opts = re.findall(
            r'data-src="(https://kwik[^"]+)"[^>]*data-resolution="(\d+)"[^>]*data-audio="(\w+)"', html)
        if not opts:
            sys.exit("no kwik sources found (blocked or layout changed)")
        want = "eng" if dub else "jpn"
        opts.sort(key=lambda o: (o[2] != want, abs(int(o[1]) - quality)))
        page = session.get(opts[0][0], headers={"Referer": self.base + "/"}, timeout=20).text
        m = re.search(r"https?://[^'\"\s]+\.m3u8", unpack_packer(page))
        if not m:
            sys.exit("could not extract m3u8 from kwik")
        return m.group(0), {"Referer": "https://kwik.si/"}, None
