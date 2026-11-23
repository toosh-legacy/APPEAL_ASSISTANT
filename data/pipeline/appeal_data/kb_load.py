"""D5: load curated rights summaries into kb_chunk (source_kind=summary)."""

from __future__ import annotations

from appeal_core.kb import deadline_rules, summary_chunks
from appeal_data.common import log_blocker, sha256_text, update_manifest


def run(load_db: bool = True) -> dict:
    chunks = summary_chunks()
    rules = deadline_rules()
    disabled = [r["id"] for g in ("rules", "next_levels") for r in rules[g] if not r["enabled"]]
    if disabled:
        log_blocker(
            "Deadline rules without a resolvable citation",
            f"Rules {disabled} did not match text in the fetched regulation chunks",
            "Those rules are disabled; no deadline is shown for them (hard rule 3)",
            "Check packages/kb/deadlines.yaml must_contain phrases against the current eCFR text.",
        )
    update_manifest(
        "kb_summaries",
        rows=len(chunks),
        sha256=sha256_text("".join(c["text"] for c in chunks)),
        source="curated",
        status="needs_human_review",
        deadline_rules_disabled=disabled,
    )
    if load_db:
        from sqlalchemy import delete

        from appeal_core.db import session_scope
        from appeal_core.models import KbChunk

        with session_scope() as s:
            s.execute(delete(KbChunk).where(KbChunk.source_kind == "summary"))
            for c in chunks:
                s.add(
                    KbChunk(
                        id=c["id"],
                        source_id=c["source_id"],
                        source_kind="summary",
                        citation_path=c["citation_path"],
                        heading=c["heading"],
                        text=c["text"],
                        plan_types=c["plan_types"],
                        topics=c["topics"],
                        status=c["status"],
                        url=None,
                    )
                )
        print(f"[kb] loaded {len(chunks)} summary chunks")
    return {"rows": len(chunks), "disabled_rules": disabled}
