"""Prints the metric and data tables for docs/MORNING_REPORT.md from the committed reports."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def eval_table() -> str:
    p = ROOT / "evals" / "reports" / "latest.json"
    if not p.exists():
        return "_evals not run_"
    d = json.loads(p.read_text())
    lines = ["| Suite | Gate | Result | Key numbers |", "|---|---|---|---|"]
    for name, s in d.items():
        m = s["metrics"]
        key = {
            "extraction": lambda m: f"mean {m['mean']:.3f}; min field {min(m['per_field'].values()):.3f}",
            "classification": lambda m: f"macro-F1 {m['macro_f1']:.3f}; ask-user rate {m['ask_user_rate']:.1%}",
            "deadlines": lambda m: f"exact {m['exact']:.1%}",
            "retrieval": lambda m: f"recall@5 {m['production']['recall@5']:.3f}, MRR {m['production']['mrr']:.3f}, nDCG@10 {m['production']['ndcg@10']:.3f}",
            "citation_validity": lambda m: f"{m['citations']} citations, {m['invalid']} invalid",
            "support": lambda m: f"{m['supported']}/{m['cited_sentences']} supported ({m['rate']:.1%})",
            "precedent_wording": lambda m: f"{m['non_binding']}/{m['precedent_sentences']} non-binding; {m['letters_citing_precedents']} letters cite precedents",
            "red_team": lambda m: f"{m['failures']} failures / {m['cases']} cases; {m['detected_by_heuristics']} flagged by detector",
            "privacy": lambda m: f"{m['raw_identifier_hits']} raw identifiers in {m['payloads_checked']} payloads; {m['leak_gate_blocks']} leak-gate blocks",
            "budget": lambda m: f"p50 {m['p50_s']:.2f}s, p95 {m['p95_s']:.2f}s; statuses {m['statuses']}",
        }.get(name, lambda m: json.dumps(m)[:120])
        try:
            k = key(m)
        except Exception:
            k = json.dumps(m)[:120]
        lines.append(f"| {name} | {s['gate']} | {'PASS' if s['passed'] else 'FAIL'} | {k} |")
    return "\n".join(lines)


def data_table() -> str:
    m = json.loads((ROOT / "data" / "manifest.json").read_text())["datasets"]
    lines = ["| Dataset | Real or synthetic | Rows | SHA-256 |", "|---|---|---:|---|"]
    names = {"imr": "D1 DMHC IMR determinations", "ecfr": "D2 eCFR regulations (chunks)", "kb_summaries": "D5 rights summaries (chunks)", "embeddings": "Embeddings", "insurers": "D3 CMS Transparency in Coverage"}
    for k, v in m.items():
        lines.append(f"| {names.get(k, k)} | {v.get('source', '?')} | {v.get('rows', '?')} | `{str(v.get('sha256', '-'))[:16]}…` |")
    lines.append("| D4 synthetic letters | synthetic (by design) | 3,000 / 500 / 120 | generator seed 20251123 |")
    return "\n".join(lines)


if __name__ == "__main__":
    print(eval_table())
    print()
    print(data_table())
