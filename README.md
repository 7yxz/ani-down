# ani-down

Download anime episodes from your terminal. Pick an anime, mark the episodes, and ani-down saves them with ffmpeg. If a provider fails it quietly tries the others.

Works on Arch Linux, Debian, Ubuntu and macOS.

## Install

```
git clone https://github.com/7yxz/ani-down
cd ani-down
bash install.sh
```

The script installs python, pipx, ffmpeg and fzf with pacman, apt or brew, then installs ani-down with pipx. Check it with `ani-down -v`.

## Usage

```
ani-down naruto                       # pick the anime, then mark episodes (tab to mark, ctrl-a for all)
ani-down naruto -e 1-12 -j 3          # episodes 1 to 12, three at a time
ani-down naruto -e 1,5,9- -f mp4 -q 720 -o ~/anime
ani-down naruto -e all --dry-run      # show what would be saved
```

| Flag | Meaning |
|------|---------|
| `-p, --provider` | animepahe or hianime (default hianime), falls back to the other |
| `-e, --episodes` | `all`, `latest`, `5`, `1-5`, `3-`, `1,4,7-9` (asks if left out) |
| `-q, --quality` | preferred quality, default 1080 |
| `-d, --dub` / `--sub` | audio language |
| `-o, --output` | output folder, default `~/Videos/anime` |
| `-f, --format` | `mkv` (default) or `mp4` |
| `-j, --jobs` | parallel downloads, default 2 |
| `--retries` | retries per episode, default 2 |
| `--overwrite` | redo files that already exist (otherwise they are skipped) |
| `--no-subs` | do not add subtitles |
| `--dry-run` | list what would be downloaded |
| `--upgrade` | update to the latest version from GitHub |

Files go to `FOLDER/Title/Title - 01.mkv`. A half-finished download ends in `.part`.

## Troubleshooting

- **animepahe says no working mirror**: it is behind a Cloudflare browser check. Copy the `cf_clearance` cookie from your browser and run `export PAHE_COOKIE="cf_clearance=VALUE"`. hianime is usually easier.
- **Cloudflare blocks hianime**: make sure `curl_cffi` is installed (`pipx inject ani-down curl_cffi`).
- **`./install.sh` not executable**: run it with `bash install.sh`.

Environment variables (optional): `PAHE_URL`, `PAHE_COOKIE`, `HIANIME_URL`.

## Credits and license

The hianime logic is ported from [ani-cli](https://github.com/pystardust/ani-cli) (GPL-3.0), so ani-down is GPL-3.0 too (see `LICENSE`).

## Disclaimer

ani-down does not host any video. It fetches links from third-party sites and saves what they serve. You are responsible for how you use it and for following the laws where you live. Please support the official releases.
