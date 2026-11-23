from __future__ import annotations

from .base import Model
from .baselines import BASELINES


def get_model(spec: str, effort: str | None = None, blind: bool = False) -> Model:
    """'oracle' | 'near_miss' | 'random' | 'shortcut' | 'claude:<model-id>' | 'gemini:<model-id>'"""
    if spec in BASELINES:
        return BASELINES[spec]()
    if spec.startswith("claude:"):
        from .claude import Claude
        return Claude(spec.split(":", 1)[1], effort=effort if effort is not None else "medium", blind=blind)
    if spec.startswith("gemini:"):
        from .gemini import Gemini
        return Gemini(spec.split(":", 1)[1], effort=effort, blind=blind)
    raise ValueError(f"unknown model spec {spec!r}. Add an adapter in gaugebench/models/.")
