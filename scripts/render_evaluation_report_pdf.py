from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "evaluation_handoff" / "evaluation_report.md"
OUTPUT_DIR = ROOT / "evaluation_handoff"
OUTPUT = OUTPUT_DIR / "evaluation_report.pdf"


def clean_inline(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    return text


def split_table(lines, start):
    rows = []
    idx = start
    while idx < len(lines) and lines[idx].strip().startswith("|"):
        raw = lines[idx].strip().strip("|")
        cells = [clean_inline(cell.strip()) for cell in raw.split("|")]
        if not all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
            rows.append(cells)
        idx += 1
    return rows, idx


def build_story():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#183D4A"),
            spaceAfter=14,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SectionHeading",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#1F4E5F"),
            spaceBefore=12,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Body",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Small",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=7,
            leading=9,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CodeBlock",
            parent=styles["Code"],
            fontName="Courier",
            fontSize=7,
            leading=9,
            backColor=colors.HexColor("#F3F6F8"),
            borderColor=colors.HexColor("#C9D6DD"),
            borderWidth=0.5,
            borderPadding=5,
            spaceBefore=4,
            spaceAfter=8,
        )
    )

    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    story = []
    bullets = []
    in_code = False
    code_lines = []
    i = 0

    def flush_bullets():
        nonlocal bullets
        if bullets:
            story.append(
                ListFlowable(
                    [ListItem(Paragraph(clean_inline(item), styles["Body"])) for item in bullets],
                    bulletType="bullet",
                    leftIndent=16,
                )
            )
            bullets = []

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                story.append(Paragraph("<br/>".join(clean_inline(row) for row in code_lines), styles["CodeBlock"]))
                code_lines = []
                in_code = False
            else:
                flush_bullets()
                in_code = True
            i += 1
            continue

        if in_code:
            code_lines.append(line)
            i += 1
            continue

        if not stripped:
            flush_bullets()
            story.append(Spacer(1, 0.06 * inch))
            i += 1
            continue

        if stripped.startswith("|"):
            flush_bullets()
            rows, i = split_table(lines, i)
            if rows:
                table_data = [[Paragraph(cell, styles["Small"]) for cell in row] for row in rows]
                table = Table(table_data, repeatRows=1)
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E5F")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C9D6DD")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFB")]),
                            ("LEFTPADDING", (0, 0), (-1, -1), 4),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                            ("TOPPADDING", (0, 0), (-1, -1), 3),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ]
                    )
                )
                story.append(table)
                story.append(Spacer(1, 0.08 * inch))
            continue

        if stripped.startswith("# "):
            flush_bullets()
            story.append(Paragraph(clean_inline(stripped[2:]), styles["ReportTitle"]))
        elif stripped.startswith("## "):
            flush_bullets()
            story.append(Paragraph(clean_inline(stripped[3:]), styles["SectionHeading"]))
        elif stripped.startswith("- "):
            bullets.append(stripped[2:])
        else:
            flush_bullets()
            story.append(Paragraph(clean_inline(stripped), styles["Body"]))
        i += 1

    flush_bullets()
    if code_lines:
        story.append(Paragraph("<br/>".join(clean_inline(row) for row in code_lines), styles["CodeBlock"]))

    return story


def add_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#667985"))
    canvas.drawString(0.72 * inch, 0.45 * inch, "Kids Daily Story Agent - Week 4 Evaluation Report")
    canvas.drawRightString(7.78 * inch, 0.45 * inch, f"Page {doc.page}")
    canvas.restoreState()


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=letter,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.7 * inch,
        title="Week 4 Evaluation Report",
        author="Kids Daily Story Agent",
    )
    doc.build(build_story(), onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(OUTPUT)


if __name__ == "__main__":
    main()
