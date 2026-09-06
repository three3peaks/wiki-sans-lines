"""User settings from config.json next to the program (or the exe)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from wiki_sans.paths import config_path

MODES = ("word", "sentence", "letter")


@dataclass
class AppConfig:
    wordnet: bool = True
    ollama: bool = True
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    default_mode: str = "word"

    def to_dict(self) -> dict:
        return asdict(self)


_config: AppConfig | None = None
last_error: str | None = None


def get_config() -> AppConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> AppConfig:
    global _config
    _config = load_config()
    return _config


def load_config() -> AppConfig:
    global last_error
    last_error = None
    path = config_path()
    raw: dict = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            return AppConfig()
        if isinstance(loaded, dict):
            raw = loaded
        else:
            last_error = "config.json must be a JSON object"
            return AppConfig()
        cfg = _from_dict(raw)
        official = cfg.to_dict()
        extras = {key: raw[key] for key in raw if key not in official}
        if any(key not in raw for key in official):
            _write(path, {**official, **extras})
        return cfg

    cfg = AppConfig()
    _write(path, cfg.to_dict())
    return cfg


def _from_dict(raw: dict) -> AppConfig:
    defaults = AppConfig()
    mode = str(raw.get("default_mode", defaults.default_mode)).strip().casefold()
    if mode not in MODES:
        mode = defaults.default_mode
    host = str(raw.get("ollama_host", defaults.ollama_host)).strip() or defaults.ollama_host
    model = str(raw.get("ollama_model", defaults.ollama_model)).strip() or defaults.ollama_model
    return AppConfig(
        wordnet=_as_bool(raw.get("wordnet"), defaults.wordnet),
        ollama=_as_bool(raw.get("ollama"), defaults.ollama),
        ollama_host=host.rstrip("/"),
        ollama_model=model,
        default_mode=mode,
    )


def _as_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        folded = value.strip().casefold()
        if folded in {"true", "1", "yes", "on"}:
            return True
        if folded in {"false", "0", "no", "off"}:
            return False
    return default


def _write(path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
