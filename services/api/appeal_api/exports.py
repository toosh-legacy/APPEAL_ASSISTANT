"""Server-rendered exports: PDF (WeasyPrint from HTML; reportlab where Pango is missing), DOCX
(python-docx), ICS (ics)."""

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


CSS = """
@page { size: Letter; margin: 1in 0.9in; @bottom-center { content: "Page " counter(page) " of " counter(pages); font-size: 9pt; color: #555; } }
body { font-family: "DejaVu Serif", Georgia, serif; font-size: 11.5pt; line-height: 1.45; color: #111; }
p { margin: 0 0 0.8em; }
p.block { white-space: pre-line; }
sup { font-size: 0.7em; }
h2 { font-size: 11pt; margin-top: 1.6em; border-top: 1px solid #999; padding-top: 0.6em; }
ol.sources { font-size: 9.5pt; padding-left: 1.4em; }
"""


def _html(view: dict[str, Any]) -> str:
    from html import escape

    order: dict[str, int] = {}
    body = []
    for sec in view["sections"]:
        parts = []
        for s in sec["sentences"]:
            marks = ""
            for c in s.get("citations", []):
                order.setdefault(c, len(order) + 1)
                marks += f"<sup>{order[c]}</sup>"
            parts.append(escape(s["text"]) + marks)
        block = sec["id"] in ("header", "closing")
        body.append(f'<p class="{"block" if block else ""}">' + ("\n" if block else " ").join(parts) + "</p>")
    notes = "".join(f"<li>{escape(view['sources'].get(c, {}).get('citation', c))}</li>" for c, _ in sorted(order.items(), key=lambda kv: kv[1]))
    sources = f'<h2>Sources</h2><ol class="sources">{notes}</ol>' if notes else ""
    return f"<!doctype html><html><head><meta charset='utf-8'><title>Appeal letter</title><style>{CSS}</style></head><body>{''.join(body)}{sources}</body></html>"


def render_pdf(view: dict[str, Any]) -> bytes:
    try:
        from weasyprint import HTML
    except OSError:  # Pango/GTK libraries missing (plain Windows); the Docker image and CI have them
        return _render_pdf_reportlab(view)
    return HTML(string=_html(view)).write_pdf()


def _render_pdf_reportlab(view: dict[str, Any]) -> bytes:
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
