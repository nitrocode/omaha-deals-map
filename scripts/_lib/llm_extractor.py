"""LLM fallback for end-time extraction. Cached by SHA(text)."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

MODEL = "claude-haiku-4-5-20251001"
SYSTEM_PROMPT = """You parse Omaha happy-hour deal text into structured end times.
Return ONLY a JSON object on one line with these keys:
  end_time: "HH:MM" 24h format, or null if you can't tell
  is_reverse_hh: true if the window is a reverse / late-night happy hour, else false
Do not include any other text."""


@dataclass
class LlmResult:
    end: str | None
    is_reverse: bool


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {} if path.exists() else {}


def _save(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(cache, sort_keys=True))


def extract_with_llm(text: str, *, start_hint: str | None,
                     cache_path: Path, client=None) -> LlmResult:
    key = hashlib.sha256(f"{start_hint}|{text}".encode()).hexdigest()
    cache = _load(cache_path)
    if key in cache:
        c = cache[key]
        return LlmResult(end=c.get("end"), is_reverse=c.get("is_reverse", False))

    if client is None:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    msg = client.messages.create(
        model=MODEL, max_tokens=80, system=SYSTEM_PROMPT,
        messages=[{"role": "user",
                   "content": f"Start time hint: {start_hint or 'unknown'}\n\nText:\n{text}"}],
    )
    raw = msg.content[0].text.strip()
    try:
        data = json.loads(raw)
        end = data.get("end_time")
        is_reverse = bool(data.get("is_reverse_hh", False))
    except (json.JSONDecodeError, KeyError):
        end, is_reverse = None, False

    cache[key] = {"end": end, "is_reverse": is_reverse}
    _save(cache_path, cache)
    return LlmResult(end=end, is_reverse=is_reverse)
