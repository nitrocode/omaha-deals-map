"""Discover active source modules from sources/registry.yaml."""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import yaml

REGISTRY_PATH = Path(__file__).parent / "registry.yaml"


@dataclass
class ActiveSources:
    names: list[str]
    modules: list[ModuleType]


def load_active_sources() -> ActiveSources:
    data = yaml.safe_load(REGISTRY_PATH.read_text())
    names = list(data.get("sources", []))
    modules = []
    for name in names:
        try:
            mod = importlib.import_module(f"sources.{name}")
        except ImportError as e:
            raise ImportError(f"sources/{name}/ not found or broken: {e}") from e
        for required in ("fetch", "parse"):
            if not hasattr(mod, required):
                raise ImportError(f"sources.{name} missing required attr: {required}()")
        modules.append(mod)
    return ActiveSources(names=names, modules=modules)
