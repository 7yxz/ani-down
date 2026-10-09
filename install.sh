#!/usr/bin/env bash
# Installs deps (python, pipx, ffmpeg, fzf) and ani-down. Supports Arch, Debian/Ubuntu, macOS.
set -e
cd "$(dirname "$0")"

if [ "$(uname)" = "Darwin" ]; then
  command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
  brew install python pipx ffmpeg fzf
elif command -v pacman >/dev/null; then
  sudo pacman -S --needed --noconfirm python python-pipx ffmpeg fzf
elif command -v apt-get >/dev/null; then
  sudo apt-get update
  sudo apt-get install -y python3 python3-venv pipx ffmpeg fzf
else
  echo "Unsupported system. Install python3, pipx, ffmpeg, fzf manually, then run: pipx install ."
  exit 1
fi

pipx ensurepath
pipx install --force .
echo "Done. Restart your shell, then run: ani-down -help"
