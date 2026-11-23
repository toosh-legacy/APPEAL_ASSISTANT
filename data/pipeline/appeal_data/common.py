"""Shared pipeline helpers: paths, hashing, manifest, downloads with retry."""

from __future__ import annotations

import hashlib
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
REPORTS = DATA / "reports"
MANIFEST = DATA / "manifest.json"
BLOCKERS = ROOT / "docs" / "BLOCKERS.md"
USER_AGENT = "appeal-assistant-data-pipeline/0.1 (local portfolio build)"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_manifest() -> dict[str, Any]:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"datasets": {}}


def save_manifest(m: dict[str, Any]) -> None:
    MANIFEST.write_text(json.dumps(m, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def update_manifest(name: str, **fields: Any) -> None:
    m = load_manifest()
    entry = m["datasets"].get(name, {})
    entry.update(fields)
    m["datasets"][name] = entry
    save_manifest(m)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def download(url: str, dest: Path, retries: int = 3, timeout: float = 600.0, params: dict | None = None) -> Path:
    """Download with retries + exponential backoff and jitter. Writes atomically."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    last: Exception | None = None
    for attempt in range(retries):
        try:
            with httpx.Client(follow_redirects=True, timeout=timeout, headers={"User-Agent": USER_AGENT}) as c:
                with c.stream("GET", url, params=params) as r:
                    r.raise_for_status()
                    tmp = dest.with_suffix(dest.suffix + ".part")
                    with tmp.open("wb") as f:
                        for chunk in r.iter_bytes(1 << 20):
                            f.write(chunk)
                    tmp.replace(dest)
            return dest
        except Exception as e:  # network errors, HTTP errors
            last = e
            time.sleep((2**attempt) + random.random())
    raise RuntimeError(f"download failed after {retries} attempts: {url}: {last}")


def log_blocker(title: str, tried: str, fallback: str, todo: str = "") -> None:
    BLOCKERS.parent.mkdir(parents=True, exist_ok=True)
    text = BLOCKERS.read_text(encoding="utf-8") if BLOCKERS.exists() else "# Blockers\n\n"
    if f"## {title}" in text:
        return
    entry = f"## {title}\n- **Tried:** {tried}\n- **Fallback used:** {fallback}\n"
    if todo:
        entry += f"- **Developer to do:** {todo}\n"
    BLOCKERS.write_text(text.rstrip() + "\n\n" + entry, encoding="utf-8")
