import re
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image as ReportLabImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


PDF_DIR = Path(__file__).resolve().parent.parent / "data" / "story_agent" / "story_pdfs"


def _safe_filename(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-")
    return clean or "story"


def create_story_pdf(
    *,
    child_name: str,
    title: str,
    theme: str,
    story_text: str,
    parent_note: Optional[str],
    story_id: str,
    illustration_path: Optional[str] = None,
) -> str:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    path = PDF_DIR / f"{_safe_filename(story_id)}.pdf"

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "StoryTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=27,
        textColor=colors.HexColor("#0e464d"),
        spaceAfter=14,
    )
    meta_style = ParagraphStyle(
        "StoryMeta",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#d86c59"),
        spaceAfter=16,
    )
    body_style = ParagraphStyle(
        "StoryBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=12,
        leading=18,
        textColor=colors.HexColor("#142126"),
        spaceAfter=10,
    )
    note_style = ParagraphStyle(
        "ParentNote",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#52616a"),
        backColor=colors.HexColor("#fff1c7"),
        borderColor=colors.HexColor("#e8aa3c"),
        borderWidth=0.7,
        borderPadding=8,
        spaceBefore=14,
    )

    doc = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title=title,
        author="Kids Daily Story Agent",
    )

    story = [
        Paragraph(title, title_style),
        Paragraph(f"Personalized story for {child_name} | Theme: {theme}", meta_style),
    ]
    image_path = Path(illustration_path) if illustration_path else None
    if image_path and image_path.exists():
        image = ReportLabImage(str(image_path))
        max_width = 2.4 * inch
        max_height = 2.4 * inch
        scale = min(max_width / image.imageWidth, max_height / image.imageHeight)
        image.drawWidth = image.imageWidth * scale
        image.drawHeight = image.imageHeight * scale
        image.hAlign = "CENTER"
        story.extend([image, Spacer(1, 0.18 * inch)])

    for paragraph in story_text.split("\n"):
        paragraph = paragraph.strip()
        if paragraph:
            story.append(Paragraph(paragraph, body_style))
            story.append(Spacer(1, 0.04 * inch))

    note = parent_note or f"Tonight's story focuses on {theme}."
    story.append(Paragraph(f"<b>Parent note:</b> {note}", note_style))

    doc.build(story)
    return str(path)
