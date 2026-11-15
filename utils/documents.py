"""Turn the simple Markdown the brief uses (#, ##, -, **bold**, *italic*) into .docx, plain text and mailto links."""
from __future__ import annotations

import re
from io import BytesIO
from urllib.parse import quote

from docx import Document
from docx.shared import Pt, RGBColor

ACCENT_RGB = RGBColor(0xC2, 0x41, 0x0C)
_INLINE = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*)")


def _add_runs(paragraph, text: str) -> None:
    for part in _INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            paragraph.add_run(part[2:-2]).bold = True
        elif part.startswith("*") and part.endswith("*"):
            paragraph.add_run(part[1:-1]).italic = True
        else:
            paragraph.add_run(part)


def markdown_to_docx(md: str) -> bytes:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    for section in doc.sections:
        section.top_margin = section.bottom_margin = Pt(54)
        section.left_margin = section.right_margin = Pt(60)

    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("# "):
            h = doc.add_heading(level=0)
            _add_runs(h, line[2:])
            for run in h.runs:
                run.font.size = Pt(20)
                run.font.color.rgb = ACCENT_RGB
        elif line.startswith("## "):
            h = doc.add_heading(level=2)
            _add_runs(h, line[3:])
            for run in h.runs:
                run.font.color.rgb = ACCENT_RGB
        elif line.lstrip().startswith(("- ", "* ")):
            p = doc.add_paragraph(style="List Bullet")
            _add_runs(p, line.lstrip()[2:])
            p.paragraph_format.space_after = Pt(2)
        else:
            _add_runs(doc.add_paragraph(), line)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def markdown_to_plain(md: str) -> str:
    out = []
    for line in md.splitlines():
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", line)
        if line.startswith("# "):
            line = line[2:]
        elif line.startswith("## "):
            line = "\n" + line[3:].upper()
        elif line.lstrip().startswith("- "):
            line = "• " + line.lstrip()[2:]
        out.append(line)
    return "\n".join(out).strip()


def mailto(subject: str, body: str, to: str = "") -> str:
    return f"mailto:{quote(to)}?subject={quote(subject)}&body={quote(body)}"
