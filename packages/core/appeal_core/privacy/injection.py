"""Heuristic prompt-injection detector (InjectionDetector interface; Prompt Shields in Phase C).

Detection is defense in depth, not the main control: document text is always treated as untrusted data,
agents only emit structured outputs, and no agent has a tool that can send data anywhere. Even an
undetected injection can only change this user's own draft, which the user reviews.
"""

from __future__ import annotations

import base64
import re

RULES: list[tuple[str, re.Pattern[str]]] = [
    ("override_instructions", re.compile(r"\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|earlier|all|system|your)\b.{0,30}\b(instructions?|prompts?|rules?|directions?)", re.I | re.S)),
    ("fake_system_message", re.compile(r"(^|\n)\s*(system|assistant|developer)\s*(message|prompt)?\s*[:>\]]|<\s*/?\s*(system|assistant|im_start|im_end)\s*>|\[\s*(system|inst)\s*\]", re.I)),
    ("role_play", re.compile(r"\byou are (now|no longer)\b|\bact as (an?|the)\b|\bnew instructions?\b|\bjailbreak\b", re.I)),
    ("exfiltration", re.compile(r"\b(other (users?|members?|patients?|cases?)|all (users?|members?|patients?))\b.{0,40}\b(data|records?|information|names?|ids?)\b|\b(send|email|post|upload|forward)\b.{0,40}\b(to|at)\b.{0,40}(https?://|www\.|@)", re.I | re.S)),
    ("drop_appeal", re.compile(r"\b(do not|don't|never|stop)\s+(write|draft|generate|prepare|help with|helping with)\b.{0,20}\b(appeal|letter)|\b(drop|withdraw|abandon|cancel)\b.{0,20}\b(the |this |your )?(appeal|letter)\b|\bappeal is (pointless|futile|useless|not worth)\b|\b(advise|tell|recommend)\b.{0,30}\bnot to appeal\b", re.I | re.S)),
    ("add_threats_or_false_claims", re.compile(r"\b(threaten|threat|lawsuit|sue them|legal action|guarantee[ds]?)\b|\b(state|claim|write) that\b.{0,40}\b(approved|guaranteed|already paid|fraud)\b", re.I | re.S)),
    ("assistant_addressed", re.compile(r"\b(note|message|instructions?) (to|for) (the )?(ai|assistant|chatbot|model|llm|claims? processor|processor)\b|\b(ai|assistant|chatbot|model|llm)\s*[:,]\s*(please|you must|you should)", re.I)),
    ("hidden_markup", re.compile(r"<!--.*?-->|​|‌|‍|⁠", re.S)),
]

_B64 = re.compile(r"\b[A-Za-z0-9+/]{24,}={0,2}")


def _decoded_b64(text: str) -> list[str]:
    out = []
    for m in _B64.finditer(text):
        s = m.group(0)
        try:
            dec = base64.b64decode(s + "=" * (-len(s) % 4), validate=True).decode("utf-8")
        except Exception:
            continue
        if sum(c.isprintable() for c in dec) / max(1, len(dec)) > 0.9 and " " in dec:
            out.append(dec)
    return out


class HeuristicInjectionDetector:
    def detect(self, text: str) -> list[str]:
        flags = [name for name, pat in RULES if pat.search(text)]
        for dec in _decoded_b64(text):
            inner = [name for name, pat in RULES if pat.search(dec)]
            flags.append("base64_encoded_instructions")
            flags.extend(inner)
        return sorted(set(flags))


def spans_to_neutralize(text: str) -> list[tuple[int, int]]:
    """Character spans of matched injection text (so agents can exclude them from reason text)."""
    spans = []
    for _, pat in RULES:
        for m in pat.finditer(text):
            spans.append((m.start(), m.end()))
    for m in _B64.finditer(text):
        if _decoded_b64(m.group(0)):
            spans.append((m.start(), m.end()))
    return spans
