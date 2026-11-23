"""Runtime leak gate: runs before every model-provider call and FAILS CLOSED.

Blocks the call if the payload contains (a) any raw identifier known for this case (exact or
canonicalized, so 'ZZTEST 123-456' still matches 'ZZTEST123456'), or (b) any high-precision identifier
shape (email, SSN, phone, ZZTEST member ID) that is not inside a vault token.
"""

from __future__ import annotations

import json
import re
from typing import Any

from appeal_core.privacy.pii import regex_detect

HIGH_PRECISION = {"EMAIL", "US_SSN", "PHONE"}
_ZZ = re.compile(r"ZZTEST[\s-]?\d", re.I)


class LeakBlocked(Exception):
    def __init__(self, reason: str):
        super().__init__(f"leak gate blocked provider call: {reason}")
        self.reason = reason


_blocks = {"count": 0}


def blocks_count() -> int:
    return _blocks["count"]


def _canon(s: str) -> str:
    return re.sub(r"[\s\-.()]", "", s).lower()


def check_payload(payload: Any, raw_values: list[str]) -> None:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, default=str)
    lowered = text.lower()
    canon = _canon(text)
    for raw in raw_values:
        if not raw or len(raw.strip()) < 3:
            continue
        if raw.lower() in lowered or (len(_canon(raw)) >= 6 and _canon(raw) in canon):
            _blocks["count"] += 1
            raise LeakBlocked("known raw identifier present")
    for sp in regex_detect(text):
        if sp.entity in HIGH_PRECISION:
            _blocks["count"] += 1
            raise LeakBlocked(f"untokenized {sp.entity} present")
    if _ZZ.search(text):
        _blocks["count"] += 1
        raise LeakBlocked("untokenized member ID present")
