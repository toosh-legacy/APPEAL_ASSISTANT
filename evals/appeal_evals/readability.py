"""Reading-level check for user-facing copy (SPEC 21.6: grades 6-8).

Scores (Flesch-Kincaid grade) the visible text of each web page and, for information only, the rights
summaries and playbooks in packages/kb (legal content: rewrite only during the human KB review).

    uv run python -m appeal_evals.readability          # writes evals/reports/readability.md
"""

from __future__ import annotations

import re
import statistics
from pathlib import Path

import textstat
import yaml

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps" / "web" / "src" / "app"
KB = ROOT / "packages" / "kb"
REPORT = ROOT / "evals" / "reports" / "readability.md"
TARGET = 8.0
# Words a user must learn here anyway; they inflate FK grade without making the copy harder.
DOMAIN = ["Medicare Advantage", "Medicaid", "Marketplace", "insurance", "insurer", "appeal", "appealing", "denial", "California"]

USER_FACING_PLAYBOOK_FIELDS = ("why", "usually_means", "evidence")
_JSX_TEXT = re.compile(r">\s*([^<>{}]*[A-Za-z][^<>{}]*?)\s*<")
_STRING = re.compile(r'"([A-Z][^"\n]{20,})"')


def page_copy(path: Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    src = re.sub(r"className=\"[^\"]*\"", "", src)
    out = [m.group(1) for m in _JSX_TEXT.finditer(src)]
    out += [m.group(1) for m in _STRING.finditer(src) if " " in m.group(1) and not m.group(1).startswith(("/", "http"))]
    return [re.sub(r"\s+", " ", t).strip() for t in out if len(t.split()) >= 4]


def grade(text: str) -> float:
    for w in DOMAIN:
        text = re.sub(rf"\b{re.escape(w)}\b", "plan", text, flags=re.I)
    return float(textstat.flesch_kincaid_grade(text))


def score_pages() -> list[dict]:
    rows = []
    for p in sorted(WEB.rglob("page.tsx")):
        copy = page_copy(p)
        if not copy:
            continue
        text = " ".join(c if c.endswith((".", "?", "!")) else c + "." for c in copy)
        worst = sorted(((grade(c), c) for c in copy if len(c.split()) >= 8), reverse=True)[:3]
        rows.append({"page": str(p.relative_to(ROOT)).replace("\\", "/"), "grade": round(grade(text), 1), "n": len(copy), "worst": worst})
    return rows


def score_kb() -> list[dict]:
    rows = []
    for p in sorted((KB / "summaries").glob("*.md")):
        body = re.sub(r"^---.*?---", "", p.read_text(encoding="utf-8"), flags=re.S)
        body = re.sub(r"[#*`>\[\]()]", " ", body)
        rows.append({"file": f"packages/kb/summaries/{p.name}", "grade": round(grade(body), 1)})
    for p in sorted((KB / "playbooks").glob("*.yaml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        texts: list[str] = []

        def walk(x):
            if isinstance(x, str) and len(x.split()) >= 6:
                texts.append(x)
            elif isinstance(x, dict):
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)

        # only what the user reads on the explanation card; `legal`/`facts` are formal letter wording for the insurer
        walk({k: data.get(k) for k in USER_FACING_PLAYBOOK_FIELDS})
        if texts:
            rows.append({"file": f"packages/kb/playbooks/{p.name}", "grade": round(grade(" ".join(texts)), 1)})
    return rows


def main() -> dict:
    pages, kb = score_pages(), score_kb()
    lines = [
        "# Reading level (Flesch-Kincaid grade)",
        "",
        f"Target: grade 6-8 (SPEC 21.6). Domain words users must learn anyway ({', '.join(DOMAIN)}) are scored as 'plan'.",
        "",
        "## Web pages",
        "",
        "| Page | Grade | Strings |",
        "|---|---:|---:|",
    ]
    lines += [f"| `{r['page']}` | {r['grade']} | {r['n']} |" for r in pages]
    lines += ["", "Hardest strings per page (grade > 8):", ""]
    for r in pages:
        for g, c in r["worst"]:
            if g > TARGET:
                lines.append(f"- `{r['page'].split('/app/')[-1]}` ({g:.1f}): {c[:160]}")
    lines += [
        "",
        "## Knowledge base (information only: legal content, rewrite during the human KB review)",
        "",
        "| File | Grade |",
        "|---|---:|",
    ]
    lines += [f"| `{r['file']}` | {r['grade']} |" for r in kb]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"pages": {r["page"]: r["grade"] for r in pages}, "pages_mean": round(statistics.mean(r["grade"] for r in pages), 1), "kb": {r["file"]: r["grade"] for r in kb}}


if __name__ == "__main__":
    import json

    print(json.dumps(main(), indent=1))
