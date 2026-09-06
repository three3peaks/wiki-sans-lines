"""Append-only log of WordNet connection attempts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from wiki_sans.paths import log_dir

LOG_DIR = log_dir()
LOG_FILE = LOG_DIR / "wordnet.log"


def log_path() -> Path:
    return log_dir() / "wordnet.log"


def write_session(lines: list[str]) -> Path:
    directory = log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "wordnet.log"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    block = [f"======= {stamp} =======", *lines, ""]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(block) + "\n")
    return path
