"""Append-only session logs."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from wiki_sans.paths import log_dir

LOG_DIR = log_dir()


def write_session(filename: str, lines: list[str]) -> Path:
    directory = log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    block = [f"======= {stamp} =======", *lines, ""]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(block) + "\n")
    return path
