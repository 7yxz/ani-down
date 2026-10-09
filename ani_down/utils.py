import os
import shutil
import subprocess
import sys

try:
    # impersonates a real Chrome TLS/HTTP2 fingerprint, gets past most Cloudflare checks
    from curl_cffi import requests as _cr
    session = _cr.Session(impersonate="chrome")
    IMPERSONATE = True
except Exception:
    import requests
    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0")
    IMPERSONATE = False


def hint_install(tool):
    if sys.platform == "darwin":
        return f"brew install {tool}"
    if shutil.which("pacman"):
        return f"sudo pacman -S {tool}"
    return f"sudo apt install {tool}"


def unpack_packer(src):
    """Unpack Dean Edwards p.a.c.k.e.r JS (used by kwik)."""
    m = re.search(r"}\('(.*)',(\d+),(\d+),'(.*?)'\.split\('\|'\)", src, re.S)
    if not m:
        return ""
    p, a, c, k = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4).split("|")
    digits = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

    def enc(n):
        return ("" if n < a else enc(n // a)) + digits[n % a]

    d = {enc(i): (k[i] or enc(i)) for i in range(c)}
    return re.sub(r"\b\w+\b", lambda x: d.get(x.group(0), x.group(0)), p)
