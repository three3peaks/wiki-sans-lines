"""Optional local Ollama. Use Qwen when the server is up; otherwise stay local."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from wiki_sans.config import get_config
from wiki_sans.session_log import write_session

PROBE_TIMEOUT = 3
GENERATE_TIMEOUT = 180


def _host() -> str:
    return get_config().ollama_host.rstrip("/")


def _preferred_model() -> str:
    return get_config().ollama_model


@dataclass
class OllamaStatus:
    server: bool = False
    model: str | None = None
    models: list[str] | None = None


status = OllamaStatus()
last_log_path = None


def ollama_ready() -> bool:
    return bool(get_config().ollama and status.server and status.model)


def chosen_model() -> str | None:
    return status.model


def _request(path: str, payload: dict | None = None, timeout: float = PROBE_TIMEOUT) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(_host() + path, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _pick_model(names: list[str]) -> str | None:
    preferred = _preferred_model()
    if preferred in names:
        return preferred
    for name in names:
        if name == preferred or name.startswith(f"{preferred}-"):
            return name
    for name in names:
        if name.startswith("qwen2.5:7b"):
            return name
    return None


def ensure_ollama() -> bool:
    """Probe localhost Ollama. Failures go to the log, not the console."""
    global last_log_path
    notes: list[str] = [f"host: {_host()}", f"wanted model: {_preferred_model()}"]
    status.server = False
    status.model = None
    status.models = []

    if not get_config().ollama:
        notes.append("disabled in config.json (ollama: false)")
        notes.append("result: skipped")
        last_log_path = write_session("ollama.log", notes)
        return False

    try:
        payload = _request("/api/tags")
    except urllib.error.URLError as exc:
        reason = exc.reason
        notes.append(f"server: down ({type(reason).__name__}: {reason})")
        notes.append("result: unavailable")
        last_log_path = write_session("ollama.log", notes)
        return False
    except TimeoutError as exc:
        notes.append(f"server: timeout ({exc})")
        notes.append("result: unavailable")
        last_log_path = write_session("ollama.log", notes)
        return False
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        notes.append(f"server: error ({type(exc).__name__}: {exc})")
        notes.append("result: unavailable")
        last_log_path = write_session("ollama.log", notes)
        return False

    names = [item.get("name", "") for item in payload.get("models", []) if item.get("name")]
    status.server = True
    status.models = names
    notes.append("server: up")
    notes.append(f"installed models: {', '.join(names) if names else '(none)'}")

    model = _pick_model(names)
    if model is None:
        notes.append(f"model {_preferred_model()}: not installed")
        notes.append("result: unavailable")
        last_log_path = write_session("ollama.log", notes)
        return False

    status.model = model
    notes.append(f"using model: {model}")
    notes.append("result: connected")
    last_log_path = write_session("ollama.log", notes)
    return True


def generate(prompt: str, system: str) -> str:
    if not ollama_ready():
        raise RuntimeError("Ollama is not connected")
    payload = _request(
        "/api/chat",
        {
            "model": status.model,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_predict": 80,
            },
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=GENERATE_TIMEOUT,
    )
    message = payload.get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Ollama returned an empty reply")
    return content
