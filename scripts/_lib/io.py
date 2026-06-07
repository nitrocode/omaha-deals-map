"""YAML/JSON read+write with atomic semantics."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    os.rename(tmp, path)


def read_yaml(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return yaml.safe_load(path.read_text())


def write_yaml(path: Path, data: Any) -> None:
    atomic_write(path, yaml.safe_dump(data, sort_keys=False))


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text())


def write_json(path: Path, data: Any) -> None:
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
