"""Tokenization vault with envelope encryption.

Each case gets a random 256-bit data key. Case data (token map, letter bodies, pasted text) is encrypted
with AES-256-GCM under that data key; the data key itself is wrapped (encrypted) with the master key.
Locally the master key comes from .env (generated at setup); in Phase C it comes from Key Vault.
Deleting the case deletes the wrapped key, which makes the remaining ciphertext unreadable.
"""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass, field

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from appeal_core.privacy.pii import PIISpan, merge_spans
from appeal_core.settings import get_settings


def _master_key() -> bytes:
    raw = get_settings().master_key
    if not raw or raw == "generate-me-at-setup":
        raise RuntimeError("MASTER_KEY not configured: run `make setup`")
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise RuntimeError("MASTER_KEY must be 32 bytes, base64-encoded")
    return key


def _seal(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def _open(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    return AESGCM(key).decrypt(blob[:12], blob[12:], aad)


def new_data_key() -> tuple[bytes, bytes]:
    """Return (data_key, wrapped_data_key)."""
    dk = AESGCM.generate_key(bit_length=256)
    return dk, _seal(_master_key(), dk, b"datakey")


def unwrap(wrapped: bytes) -> bytes:
    return _open(_master_key(), wrapped, b"datakey")


def encrypt(data_key: bytes, text: str, purpose: str) -> bytes:
    return _seal(data_key, text.encode("utf-8"), purpose.encode())


def decrypt(data_key: bytes, blob: bytes, purpose: str) -> str:
    return _open(data_key, blob, purpose.encode()).decode("utf-8")


_TOKEN_RE = re.compile(r"\[([A-Z_]+)_(\d+)\]")


def _canon(value: str) -> str:
    return re.sub(r"[\s\-.]", "", value).lower()


@dataclass
class TokenMap:
    """token -> raw value. Same raw value (after canonicalization) always gets the same token."""

    tokens: dict[str, str] = field(default_factory=dict)

    def token_for(self, entity: str, raw: str) -> str:
        c = _canon(raw)
        for tok, val in self.tokens.items():
            if tok.startswith(f"[{entity}_") and _canon(val) == c:
                return tok
        n = sum(1 for t in self.tokens if t.startswith(f"[{entity}_")) + 1
        tok = f"[{entity}_{n}]"
        self.tokens[tok] = raw
        return tok

    def to_json(self) -> str:
        return json.dumps(self.tokens)

    @classmethod
    def from_json(cls, s: str) -> TokenMap:
        return cls(tokens=json.loads(s))

    def raw_values(self) -> list[str]:
        return list(self.tokens.values())


def tokenize(text: str, spans: list[PIISpan], tmap: TokenMap | None = None) -> tuple[str, TokenMap]:
    tmap = tmap or TokenMap()
    out = text
    for sp in sorted(merge_spans(spans), key=lambda s: s.start, reverse=True):
        tok = tmap.token_for(sp.entity, text[sp.start : sp.end])
        out = out[: sp.start] + tok + out[sp.end :]
    # Second pass: any other occurrence of an already-known raw value (e.g. the name repeated without a label).
    for tok, raw in sorted(tmap.tokens.items(), key=lambda kv: -len(kv[1])):
        if len(raw) >= 4:
            out = re.sub(re.escape(raw), tok, out)
        # Name variants of a known person: "J. Last", "Jordan Q. Last", "Last, Jordan"
        if tok.startswith("[PERSON_"):
            parts = raw.split()
            if len(parts) >= 2 and len(parts[0]) > 1:
                first, last = re.escape(parts[0]), re.escape(parts[-1])
                pat = rf"\b(?:{first}|{first[0]}\.)\s+(?:[A-Z]\.\s+)?{last}\b|\b{last},\s+{first}\b"
                out = re.sub(pat, tok, out)
    return out, tmap


def rehydrate(text: str, tmap: TokenMap) -> str:
    return _TOKEN_RE.sub(lambda m: tmap.tokens.get(m.group(0), m.group(0)), text)
