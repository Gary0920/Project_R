from __future__ import annotations

from pathlib import Path

from app.features.documents.content_parser import DocumentBlock, InlineSpan, parse_document


def render_pdf(title: str, content: str, output_path: Path) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    parsed = parse_document(title, content)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

    styles = getSampleStyleSheet()
    normal = ParagraphStyle("PRNormal", parent=styles["Normal"], fontName="STSong-Light", fontSize=10.5, leading=15)
    heading1 = ParagraphStyle("PRHeading1", parent=styles["Heading1"], fontName="STSong-Light", fontSize=18, leading=24, spaceAfter=8)
    heading2 = ParagraphStyle("PRHeading2", parent=styles["Heading2"], fontName="STSong-Light", fontSize=14, leading=20, spaceAfter=6)
    bullet_style = ParagraphStyle("PRBullet", parent=normal, leftIndent=12, firstLineIndent=-8)

    story = []
    story.append(Paragraph(_escape(parsed.title), heading1))
    story.append(Spacer(1, 6))
    for index, block in enumerate(parsed.blocks):
        if index == 0 and block.type == "heading" and block.text.strip() == parsed.title.strip():
            continue
        if block.type == "heading":
            story.append(Paragraph(_escape(block.text), heading1 if block.level == 1 else heading2))
        elif block.type == "table":
            story.append(_pdf_table(block))
        elif block.type == "bullet":
            story.append(Paragraph(f"• {_spans_to_pdf_markup(block.spans)}", bullet_style))
        elif block.type == "numbered":
            story.append(Paragraph(_spans_to_pdf_markup(block.spans), bullet_style))
        elif block.type == "quote":
            story.append(Paragraph(f"引用：{_spans_to_pdf_markup(block.spans)}", normal))
        elif block.type == "rule":
            story.append(Spacer(1, 4))
        elif block.text:
            story.append(Paragraph(_spans_to_pdf_markup(block.spans), normal))
        story.append(Spacer(1, 4))

    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    document.build(story)
    return output_path


def _pdf_table(block: DocumentBlock):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    table = Table(block.rows, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF8")),
                ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B8C0CC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _spans_to_pdf_markup(spans: list[InlineSpan]) -> str:
    parts = []
    for span in spans:
        text = _escape(span.text)
        if span.code:
            text = f"<font name=\"Courier\">{text}</font>"
        parts.append(text)
    return "".join(parts)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
