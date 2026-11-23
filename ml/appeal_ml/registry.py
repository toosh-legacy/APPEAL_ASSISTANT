"""ModelRegistry: loads the version pinned in ml/artifacts/pinned.json (Azure ML registry in Phase C)."""

from __future__ import annotations

from functools import lru_cache

import joblib

from appeal_ml.common import ARTIFACTS, pinned


class LocalModelRegistry:
    def __init__(self) -> None:
        self._cache: dict[str, object] = {}

    def _load(self, name: str):
        if name in self._cache:
            return self._cache[name]
        v = pinned().get(name)
        obj = None
        if v:
            p = ARTIFACTS / name / v / "model.joblib"
            if p.exists():
                obj = joblib.load(p)
        self._cache[name] = obj
        return obj

    def m1(self):
        return self._load("m1")

    def m2(self):
        return self._load("m2")

    def m3(self):
        return self._load("m3")

    def versions(self) -> dict[str, str]:
        return pinned()


@lru_cache
def get_registry():
    from appeal_core.settings import get_settings

    if get_settings().model_registry == "azure":
        from appeal_core.adapters.azure import AzureMLModelRegistry

        return AzureMLModelRegistry()
    return LocalModelRegistry()
