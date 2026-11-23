"""Deadline calculator. Only rules with a resolved citation are used (hard rule 3)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from appeal_core.kb import deadline_rules


def compute_deadlines(plan_type: str | None, notice_date: date | None, today: date | None = None) -> list[dict[str, Any]]:
    if not plan_type or not notice_date:
        return []
    out = []
    for r in deadline_rules()["rules"]:
        if not r["enabled"] or plan_type not in r["plan_types"]:
            continue
        if r["trigger"] != "notice_date":
            continue
        due = notice_date + timedelta(days=int(r["days"]))
        item = {
            "kind": r["kind"],
            "label": r["label"],
            "rule_id": r["id"],
            "days": int(r["days"]),
            "trigger_date": notice_date.isoformat(),
            "due_date": due.isoformat(),
            "basis_chunk_id": r["basis_chunk_id"],
            "basis_citation": r["basis_citation"],
            "also_chunk_id": r.get("also_chunk_id"),
            "letter_text": r.get("letter_text"),
        }
        if today is not None:
            item["days_remaining"] = (due - today).days
        out.append(item)
    return out


def next_level_options(plan_type: str | None) -> list[dict[str, Any]]:
    if not plan_type:
        return []
    return [
        {
            "kind": r["kind"],
            "label": r["label"],
            "window_text": r["window_text"],
            "rule_id": r["id"],
            "basis_chunk_id": r["basis_chunk_id"],
            "basis_citation": r["basis_citation"],
        }
        for r in deadline_rules()["next_levels"]
        if r["enabled"] and plan_type in r["plan_types"]
    ]


def ics_for(deadline: dict[str, Any], uid: str) -> str:
    """Minimal RFC 5545 all-day event for the due date."""
    d = deadline["due_date"].replace("-", "")
    return "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Appeal Assistant//local//EN",
            "BEGIN:VEVENT",
            f"UID:{uid}@appeal-assistant.local",
            f"DTSTAMP:{date.today().strftime('%Y%m%d')}T000000Z",
            f"DTSTART;VALUE=DATE:{d}",
            f"SUMMARY:Appeal deadline: {deadline['label']}",
            f"DESCRIPTION:Based on {deadline.get('basis_citation') or 'cited rule'}. Check your notice for the exact date.",
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
    )
