"""Server-rendered exports: PDF (reportlab), DOCX (python-docx), ICS."""

from __future__ import annotations

import io
from typing import Any

from appeal_core.deadlines import ics_for


def _paragraphs(view: dict[str, Any]) -> tuple[list[str], list[str]]:
    paras, notes = [], []
    order: dict[str, int] = {}
    for sec in view["sections"]:
        parts = []
        for s in sec["sentences"]:
            marks = ""
            for c in s.get("citations", []):
                if c not in order:
                    order[c] = len(order) + 1
                marks += f"[{order[c]}]"
            parts.append(s["text"] + marks)
        joiner = "\n" if sec["id"] in ("header", "closing") else " "
        paras.append(joiner.join(parts))
    for c, n in sorted(order.items(), key=lambda kv: kv[1]):
        src = view["sources"].get(c, {})
        notes.append(f"[{n}] {src.get('citation', c)}")
    return paras, notes


def render_pdf(view: dict[str, Any]) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, title="Appeal letter", leftMargin=60, rightMargin=60)
    styles = getSampleStyleSheet()
    story = []
    paras, notes = _paragraphs(view)
    for p in paras:
        story.append(Paragraph(p.replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br/>"), styles["BodyText"]))
        story.append(Spacer(1, 10))
    if notes:
        story.append(Paragraph("Sources", styles["Heading4"]))
        for n in notes:
            story.append(Paragraph(n.replace("&", "&amp;").replace("<", "&lt;"), styles["BodyText"]))
    doc.build(story)
    return buf.getvalue()


def render_docx(view: dict[str, Any]) -> bytes:
    from docx import Document

    d = Document()
    paras, notes = _paragraphs(view)
    for p in paras:
        d.add_paragraph(p)
    if notes:
        d.add_heading("Sources", level=3)
        for n in notes:
            d.add_paragraph(n)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def render_ics(deadline: dict[str, Any], case_id: str) -> str:
    return ics_for(deadline, case_id)
