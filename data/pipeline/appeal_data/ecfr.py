"""D2: federal regulations from the eCFR versioner API.

fetch (skip unchanged) -> parse into a paragraph hierarchy with citation paths -> chunk (150-600 tokens,
parent headings kept) -> tag plan types / topics -> load into kb_chunk (source_kind=regulation).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from appeal_data.common import RAW, download, log_blocker, now_iso, sha256_file, update_manifest

TITLES_URL = "https://www.ecfr.gov/api/versioner/v1/titles.json"
FULL_URL = "https://www.ecfr.gov/api/versioner/v1/full/{date}/title-{title}.xml"
ECFR_DIR = RAW / "ecfr"
PROCESSED_JSON = Path(__file__).resolve().parents[2] / "processed" / "regulation_chunks.json"

EMPLOYER = ["employer_self_funded", "employer_fully_insured"]
COMMERCIAL = EMPLOYER + ["individual_marketplace"]

# (source_id, title, params, plan_types, label)
SOURCES: list[tuple[str, int, dict[str, str], list[str], str]] = [
    ("29cfr2560.503-1", 29, {"part": "2560", "section": "2560.503-1"}, EMPLOYER, "ERISA claims procedure"),
    ("45cfr147.136", 45, {"part": "147", "section": "147.136"}, COMMERCIAL, "Internal claims, appeals and external review"),
    ("42cfr422.M", 42, {"part": "422", "subpart": "M"}, ["medicare_advantage"], "Medicare Advantage appeals (Subpart M)"),
    ("42cfr438.F", 42, {"part": "438", "subpart": "F"}, ["medicaid_managed_care"], "Medicaid managed care appeals (Subpart F)"),
    ("45cfr149.110", 45, {"part": "149", "section": "149.110"}, COMMERCIAL, "No Surprises Act: emergency services"),
    ("45cfr149.120", 45, {"part": "149", "section": "149.120"}, COMMERCIAL, "No Surprises Act: nonparticipating providers at participating facilities"),
    ("45cfr149.130", 45, {"part": "149", "section": "149.130"}, COMMERCIAL, "No Surprises Act: air ambulance"),
    ("45cfr149.410", 45, {"part": "149", "section": "149.410"}, COMMERCIAL, "No Surprises Act: balance billing for emergency services"),
    ("45cfr149.420", 45, {"part": "149", "section": "149.420"}, COMMERCIAL, "No Surprises Act: notice and consent"),
]

TOPIC_RULES = {
    "deadlines": re.compile(r"\b(\d+|sixty|thirty|forty-five|seventy-two)[- ](calendar |business )?(days?|hours)\b|\bwithin a reasonable period\b|\bno later than\b", re.I),
    "external_review": re.compile(r"external review|independent review|independent review organization|IRE\b|\bIRO\b|State hearing|fair hearing", re.I),
    "urgent_care": re.compile(r"urgent care|expedited|concurrent care|72 hours", re.I),
    "notice_requirements": re.compile(r"\bnotice\b|notification|notify|culturally and linguistically", re.I),
    "continued_coverage": re.compile(r"continued coverage|continuation of benefits|pending the outcome|continue to provide coverage", re.I),
    "full_and_fair_review": re.compile(r"full and fair review|review that takes into account|de novo|without deference", re.I),
    "emergency_services": re.compile(r"emergency services|emergency medical condition|prudent layperson", re.I),
    "medical_necessity": re.compile(r"medical necessity|medically necessary|medical judgment|experimental|investigational", re.I),
}


# ---------------------------------------------------------------- hierarchy parsing
ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii", "xviii", "xix", "xx", "xxi", "xxii", "xxiii", "xxiv", "xxv"]
LOWER = [chr(c) for c in range(ord("a"), ord("z") + 1)] + [a + a for a in "abcdefghijklmnopqrstuvwxyz"]
UPPER = [chr(c) for c in range(ord("A"), ord("Z") + 1)]


def _seq(kind: str) -> list[str]:
    return {"lower": LOWER, "digit": [str(i) for i in range(1, 100)], "roman": ROMAN, "upper": UPPER, "idigit": [str(i) for i in range(1, 100)], "iroman": ROMAN}[kind]


def _kinds(marker: str, italic: bool) -> list[str]:
    kinds = []
    if marker.isdigit():
        kinds.append("idigit" if italic else "digit")
    if marker in ROMAN:
        kinds.append("iroman" if italic else "roman")
    if marker in LOWER and marker.islower():
        kinds.append("lower")
    if marker in UPPER:
        kinds.append("upper")
    return kinds


class Hierarchy:
    def __init__(self) -> None:
        self.stack: list[tuple[str, str]] = []  # (kind, marker)

    def feed(self, marker: str, italic: bool = False) -> None:
        kinds = _kinds(marker, italic)
        # 1) continuation of an existing level (deepest first)
        for depth in range(len(self.stack) - 1, -1, -1):
            kind, prev = self.stack[depth]
            if kind in kinds:
                seq = _seq(kind)
                if prev in seq and seq.index(prev) + 1 < len(seq) and seq[seq.index(prev) + 1] == marker:
                    self.stack = self.stack[:depth] + [(kind, marker)]
                    return
        # 2) first item of a new deeper level
        used = {k for k, _ in self.stack}
        for kind in kinds:
            if kind not in used and _seq(kind)[0] == marker:
                self.stack.append((kind, marker))
                return
        # 3) fallback: treat as sibling at deepest level
        if self.stack:
            self.stack[-1] = (self.stack[-1][0], marker)
        else:
            self.stack.append((kinds[0] if kinds else "lower", marker))

    def feed_kind(self, marker: str, kind: str) -> None:
        for depth in range(len(self.stack) - 1, -1, -1):
            if self.stack[depth][0] == kind:
                self.stack = self.stack[:depth] + [(kind, marker)]
                return
        self.stack.append((kind, marker))

    def has_lower_prev(self, marker: str) -> bool:
        for kind, prev in self.stack:
            if kind == "lower" and prev in LOWER and LOWER.index(prev) + 1 == LOWER.index(marker):
                return True
        return False

    def path(self) -> str:
        return "".join(f"({m})" for _, m in self.stack)


_MARK = re.compile(r"^\s*\((\w{1,5})\)\s*")
_EMBED = re.compile(r"(?:—|\.)\s*\((\w{1,5})\)\s+(?=[A-Z<])")


@dataclass
class Para:
    section: str  # e.g. "45 CFR 147.136"
    section_head: str
    path: str  # (b)(2)(ii)
    text: str
    title: str | None = None
    parents: list[str] = field(default_factory=list)

    @property
    def citation(self) -> str:
        return f"{self.section}{self.path}"


def _text(el) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def leading_markers(raw: str) -> list[str]:
    """Markers that open a paragraph: '(c)(1)(i) ...' or '(a) Scope—(1) Scope—(i) In general.'"""
    marks: list[str] = []
    rest = raw
    while True:
        m = _MARK.match(rest)
        if not m:
            break
        marks.append(m.group(1))
        rest = rest[m.end():]
    if marks:
        while True:
            em = _EMBED.search(rest[:250])
            if not em:
                break
            marks.append(em.group(1))
            rest = rest[em.end():]
            while True:
                m = _MARK.match(rest)
                if not m:
                    break
                marks.append(m.group(1))
                rest = rest[m.end():]
    return marks


def _is_next_roman(a: str, b: str) -> bool:
    return a in ROMAN and b in ROMAN and ROMAN.index(b) == ROMAN.index(a) + 1


def parse_sections(xml_bytes: bytes) -> list[Para]:
    root = etree.fromstring(xml_bytes)
    paras: list[Para] = []
    sections = [root] if root.tag == "DIV8" else list(root.iter("DIV8"))
    for sec in sections:
        n = sec.get("N")
        head_el = sec.find("HEAD")
        head = _text(head_el) if head_el is not None else f"§ {n}"
        meta = sec.get("hierarchy_metadata") or ""
        tnum = re.search(r"title-(\d+)", meta)
        section_cite = f"{tnum.group(1) if tnum else ''} CFR {n}".strip()
        items = []
        for p in sec.iter("P", "FP"):
            raw = _text(p)
            if raw:
                items.append((p, raw, leading_markers(raw)))
        h = Hierarchy()
        titles: dict[str, str] = {}
        for idx, (p, raw, marks) in enumerate(items):
            for k, mk in enumerate(marks):
                # look-ahead for ambiguous roman/letter markers like (i), (v), (x)
                if mk in ROMAN and mk in LOWER:
                    nxt = marks[k + 1] if k + 1 < len(marks) else None
                    if nxt is None:
                        j = idx + 1
                        while j < len(items) and not items[j][2]:
                            j += 1
                        nxt = items[j][2][0] if j < len(items) else None
                    if nxt is not None and _is_next_roman(mk, nxt):
                        h.feed_kind(mk, "roman")
                        continue
                    if nxt is not None and nxt in LOWER and LOWER.index(nxt) == LOWER.index(mk) + 1 and h.has_lower_prev(mk):
                        h.feed_kind(mk, "lower")
                        continue
                h.feed(mk)
            path = h.path()
            first_i = p.find("I")
            ptitle = None
            if first_i is not None and first_i.text:
                cand = first_i.text.strip().rstrip(".")
                if 2 < len(cand) < 120 and not cand.startswith("("):
                    ptitle = cand
            if ptitle and path:
                titles[path] = ptitle
            parents = []
            acc = ""
            for _, mk in h.stack[:-1]:
                acc += f"({mk})"
                if acc in titles:
                    parents.append(f"{acc} {titles[acc]}")
            paras.append(Para(section_cite, head, path, raw, ptitle, parents))
    return paras


def _tokens(text: str) -> int:
    return int(len(text.split()) * 1.3)


def chunk_paragraphs(paras: list[Para], min_tokens: int = 150, max_tokens: int = 600) -> list[dict]:
    """Merge consecutive paragraphs that share a parent (top two levels) until >= min_tokens; split > max."""
    chunks: list[dict] = []
    buf: list[Para] = []

    def group_key(p: Para) -> tuple[str, str]:
        parts = re.findall(r"\([^)]+\)", p.path)
        return (p.section, "".join(parts[:2]))

    def flush() -> None:
        if not buf:
            return
        first = buf[0]
        body = "\n".join(p.text for p in buf)
        context = " > ".join([first.section_head] + first.parents)
        # split overly long bodies by words
        words = body.split()
        max_words = int(max_tokens / 1.3)
        pieces = [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)] or [body]
        for j, piece in enumerate(pieces):
            cid = first.citation + (f"~{j}" if j else "")
            chunks.append(
                {
                    "citation_path": first.citation,
                    "chunk_key": cid,
                    "heading": context,
                    "text": piece,
                    "end_citation": buf[-1].citation,
                }
            )
        buf.clear()

    def top(p: Para) -> tuple[str, str]:
        parts = re.findall(r"\([^)]+\)", p.path)
        return (p.section, parts[0] if parts else "")

    for p in paras:
        if buf:
            cur = _tokens(" ".join(b.text for b in buf))
            nxt = cur + _tokens(p.text)
            if top(p) != top(buf[0]):
                flush()
            elif group_key(p) != group_key(buf[0]) and cur >= min_tokens:
                flush()
            elif nxt > max_tokens and cur >= min_tokens:
                flush()
        buf.append(p)
        if _tokens(" ".join(b.text for b in buf)) >= max_tokens:
            flush()
    flush()
    return chunks


def tag_topics(text: str) -> list[str]:
    return [t for t, pat in TOPIC_RULES.items() if pat.search(text)]


# ---------------------------------------------------------------- fetch
def fetch_all(force: bool = False) -> list[dict]:
    ECFR_DIR.mkdir(parents=True, exist_ok=True)
    titles_path = ECFR_DIR / "titles.json"
    download(TITLES_URL, titles_path, retries=3, timeout=60)
    titles = {t["number"]: t for t in json.loads(titles_path.read_text(encoding="utf-8"))["titles"]}
    all_chunks: list[dict] = []
    fetched = []
    for source_id, title, params, plan_types, label in SOURCES:
        date = titles[title]["up_to_date_as_of"]
        dest = ECFR_DIR / f"{source_id}_{date}.xml"
        if not dest.exists() or force:
            download(FULL_URL.format(date=date, title=title), dest, retries=3, timeout=120, params=params)
        sha = sha256_file(dest)
        paras = parse_sections(dest.read_bytes())
        chunks = chunk_paragraphs(paras)
        url = f"https://www.ecfr.gov/current/title-{title}/" + (
            f"section-{params['section']}" if "section" in params else f"part-{params['part']}/subpart-{params['subpart']}"
        )
        for c in chunks:
            c.update(
                {
                    "id": "reg:" + c["chunk_key"].replace(" ", ""),
                    "source_id": source_id,
                    "source_kind": "regulation",
                    "plan_types": plan_types,
                    "topics": tag_topics(c["text"]),
                    "effective_date": date,
                    "url": url,
                    "label": label,
                    "sha256": sha,
                }
            )
        all_chunks.extend(chunks)
        fetched.append({"source_id": source_id, "date": date, "sha256": sha, "paragraphs": len(paras), "chunks": len(chunks), "url": url})
    # de-duplicate ids
    seen: dict[str, int] = {}
    for c in all_chunks:
        if c["id"] in seen:
            seen[c["id"]] += 1
            c["id"] = f"{c['id']}~{seen[c['id']]}"
        else:
            seen[c["id"]] = 0
    update_manifest(
        "ecfr",
        url=TITLES_URL,
        sources=fetched,
        rows=len(all_chunks),
        downloaded_at=now_iso(),
        schema_ok=True,
        source="real",
        sha256=sha256_file(titles_path),
    )
    return all_chunks


def run(load_db: bool = True, force: bool = False) -> dict:
    try:
        chunks = fetch_all(force=force)
    except Exception as e:
        log_blocker(
            "D2 eCFR fetch failed",
            f"eCFR versioner API with 3 retries: {e}. GovInfo bulk XML fallback not attempted automatically (different volume structure).",
            "Continuing with D5 curated summaries only",
            "Re-run `make data` when ecfr.gov is reachable.",
        )
        return {"rows": 0, "source": "missing"}
    PROCESSED_JSON.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_JSON.write_text(json.dumps(chunks, indent=1), encoding="utf-8")
    if load_db:
        load(chunks)
    return {"rows": len(chunks), "source": "real"}


def load(chunks: list[dict]) -> None:
    from appeal_core.db import session_scope
    from appeal_core.models import DatasetManifest, KbChunk, KbSource
    from sqlalchemy import delete

    with session_scope() as s:
        s.execute(delete(KbChunk).where(KbChunk.source_kind == "regulation"))
        s.execute(delete(KbSource).where(KbSource.kind == "regulation"))
        sources = {}
        for c in chunks:
            sources[c["source_id"]] = c
            s.add(
                KbChunk(
                    id=c["id"],
                    source_id=c["source_id"],
                    source_kind="regulation",
                    citation_path=c["citation_path"],
                    heading=c["heading"],
                    text=c["text"],
                    plan_types=c["plan_types"],
                    topics=c["topics"],
                    effective_date=c["effective_date"],
                    url=c["url"],
                    status="official",
                )
            )
        for sid, c in sources.items():
            s.add(
                KbSource(
                    id=sid,
                    url=c["url"],
                    citation_path=c["citation_path"].split("(")[0],
                    sha256=c["sha256"],
                    effective_date=c["effective_date"],
                    version=c["effective_date"],
                    kind="regulation",
                )
            )
        s.merge(
            DatasetManifest(
                name="ecfr", url=TITLES_URL, sha256=chunks[0]["sha256"] if chunks else "", rows=len(chunks),
                downloaded_at=now_iso(), schema_ok=True, source="real",
            )
        )
    print(f"[ecfr] loaded {len(chunks)} regulation chunks")
