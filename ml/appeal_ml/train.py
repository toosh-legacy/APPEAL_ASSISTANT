"""`python -m appeal_ml.train all|m1|m2|m3` - reproducible (fixed seeds, data hashes recorded)."""

from __future__ import annotations

import sys
import time

from appeal_ml import m1, m2, m3
from appeal_ml.common import pin
from appeal_ml.promotion_check import should_promote


def main(which: str) -> None:
    for name, mod in [("m1", m1), ("m2", m2), ("m3", m3)]:
        if which not in ("all", name):
            continue
        t0 = time.time()
        mod.train()
        ok, why = should_promote(name, mod.VERSION)
        if ok:
            pin(name, mod.VERSION)
        print(f"[{name}] trained in {time.time() - t0:.0f}s; promote={ok} ({why})", flush=True)
    from appeal_ml.report import write_report

    write_report()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
