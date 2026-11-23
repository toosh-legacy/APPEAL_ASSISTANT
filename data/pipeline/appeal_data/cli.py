"""Data pipeline CLI: `python -m appeal_data.cli all [--force] [--no-db]`.

Idempotent: unchanged raw files are not re-processed and already-loaded tables are not reloaded.
"""

from __future__ import annotations

import argparse
import time

from appeal_data import ecfr, imr, kb_load


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["all", "imr", "ecfr", "kb", "synth", "insurers", "embed"])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-db", action="store_true")
    ap.add_argument("--ci", action="store_true", help="CI mode: synthetic IMR sample (no 85 MB download) + LSA embeddings")
    a = ap.parse_args()
    if a.ci:
        import os

        os.environ["IMR_CI_SYNTHETIC"] = "1"
        os.environ["EMBEDDER"] = "lsa"
    load_db = not a.no_db
    t0 = time.time()
    results = {}
    if a.step in ("all", "imr"):
        results["imr"] = imr.run(load_db=load_db, force=a.force)
    if a.step in ("all", "ecfr"):
        results["ecfr"] = ecfr.run(load_db=load_db, force=a.force)
    if a.step in ("all", "kb"):
        results["kb"] = kb_load.run(load_db=load_db)
    if a.step in ("all", "synth"):
        from appeal_synth.generate import generate

        results["synth"] = generate()
    if a.step in ("all", "insurers"):
        try:
            from appeal_data import insurers

            results["insurers"] = insurers.run(load_db=load_db, force=a.force)
        except ImportError:
            results["insurers"] = "skipped (P1 not built)"
    if a.step in ("all", "embed") and load_db:
        try:
            from appeal_data import embed

            results["embed"] = embed.run(force=a.force)
        except ImportError:
            results["embed"] = "skipped (Phase 3)"
    for k, v in results.items():
        print(f"{k}: {v}")
    print(f"data pipeline finished in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
