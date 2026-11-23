"""Shared ML helpers: artifact layout, data hashes, git SHA, calibration metrics, plots."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "ml" / "artifacts"
REPORTS = ROOT / "ml" / "reports"
PINNED = ARTIFACTS / "pinned.json"
SEED = 20251123


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def file_hash(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_dir(model: str, version: str) -> Path:
    d = ARTIFACTS / model / version
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_json(p: Path, obj: Any) -> None:
    p.write_text(json.dumps(obj, indent=2, sort_keys=True, default=float) + "\n", encoding="utf-8")


def ece(probs: np.ndarray, correct: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (probs > lo) & (probs <= hi)
        if m.any():
            total += m.mean() * abs(correct[m].mean() - probs[m].mean())
    return float(total)


def reliability_plot(probs: np.ndarray, correct: np.ndarray, path: Path, title: str, bins: int = 10) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    edges = np.linspace(0, 1, bins + 1)
    xs, ys, ns = [], [], []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (probs > lo) & (probs <= hi)
        if m.any():
            xs.append(probs[m].mean())
            ys.append(correct[m].mean())
            ns.append(int(m.sum()))
    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    ax.plot([0, 1], [0, 1], "--", color="#999")
    ax.plot(xs, ys, "o-", color="#4C78A8")
    for x, y, n in zip(xs, ys, ns, strict=True):
        ax.annotate(str(n), (x, y), fontsize=7, xytext=(3, -8), textcoords="offset points")
    ax.set_xlabel("Predicted probability")
    ax.set_ylabel("Observed frequency")
    ax.set_title(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def pinned() -> dict[str, str]:
    return json.loads(PINNED.read_text()) if PINNED.exists() else {}


def pin(model: str, version: str) -> None:
    p = pinned()
    p[model] = version
    save_json(PINNED, p)
