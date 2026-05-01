"""Generate the demo Q3 financial report fixture.

This produces a one-page native-text PDF with no concealment mechanisms.
It is the file served behind Exhibit A on bayyinah.dev/demo. The content
is plain Q3 narrative + a small numeric table so that Anthropic's Sonnet
4.6 returns a genuine Q3 summary when the firewall verdict is sahih.

Output: docs/demo/fixtures/clean_q3_report.pdf
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib import colors


def build() -> Path:
    out = Path(__file__).resolve().parents[1] / "docs" / "demo" / "fixtures" / "clean_q3_report.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "body",
        parent=styles["BodyText"],
        fontName="Times-Roman",
        fontSize=10.5,
        leading=14,
        spaceAfter=8,
    )
    h1 = ParagraphStyle(
        "h1",
        parent=styles["Heading1"],
        fontName="Times-Bold",
        fontSize=15,
        leading=18,
        spaceAfter=10,
    )
    h2 = ParagraphStyle(
        "h2",
        parent=styles["Heading2"],
        fontName="Times-Bold",
        fontSize=11.5,
        leading=14,
        spaceBefore=10,
        spaceAfter=6,
    )
    meta = ParagraphStyle(
        "meta",
        parent=styles["BodyText"],
        fontName="Times-Italic",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#555555"),
        spaceAfter=14,
    )

    doc = SimpleDocTemplate(
        str(out),
        pagesize=LETTER,
        leftMargin=0.95 * inch,
        rightMargin=0.95 * inch,
        topMargin=0.85 * inch,
        bottomMargin=0.85 * inch,
        title="Q3 Financial Summary",
        author="Northbrook Analytics, Inc.",
        subject="Quarterly financial summary",
    )

    story = []

    story.append(Paragraph("Q3 Financial Summary", h1))
    story.append(
        Paragraph(
            "Northbrook Analytics, Inc. &nbsp;&middot;&nbsp; Folio 01 &nbsp;&middot;&nbsp; "
            "Quarter ending September 30, 2025",
            meta,
        )
    )

    story.append(Paragraph("Quarterly update", h2))
    story.append(
        Paragraph(
            "Revenue grew 8% year over year to $1,000 thousand for the third quarter, "
            "compared with $926 thousand in the same period last year. Margins held "
            "steady at 41.2%. Cash position remains strong at $4.2 million, with "
            "operating cash flow of $312 thousand for the quarter.",
            body,
        )
    )
    story.append(
        Paragraph(
            "New annual recurring revenue from enterprise customers contributed "
            "$184 thousand, bringing total ARR to $3.6 million. Net revenue retention "
            "stood at 112%, reflecting expansion within existing accounts. Sales "
            "headcount remained flat quarter over quarter; engineering grew by two "
            "full-time positions.",
            body,
        )
    )

    story.append(Paragraph("Key figures", h2))

    figures = [
        ["Metric", "Q3 2025", "Q3 2024", "YoY"],
        ["Revenue", "$1,000K", "$926K", "+8.0%"],
        ["Gross margin", "41.2%", "40.6%", "+60 bps"],
        ["Operating cash flow", "$312K", "$245K", "+27.3%"],
        ["Cash and equivalents", "$4.2M", "$3.6M", "+16.7%"],
        ["ARR (period end)", "$3.6M", "$2.9M", "+24.1%"],
        ["Net revenue retention", "112%", "108%", "+4 pp"],
    ]
    table = Table(figures, colWidths=[2.3 * inch, 1.1 * inch, 1.1 * inch, 1.1 * inch])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
                ("TOPPADDING", (0, 0), (-1, 0), 4),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
                ("TOPPADDING", (0, 1), (-1, -1), 5),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#333333")),
                ("LINEABOVE", (0, -1), (-1, -1), 0.4, colors.HexColor("#888888")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAFA")]),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1a1a1a")),
                ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#1a1a1a")),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 14))

    story.append(Paragraph("Outlook", h2))
    story.append(
        Paragraph(
            "Management reiterates the prior full-year revenue range of $3.85M to "
            "$3.95M and expects gross margin in the 40% to 42% band. Q4 typically "
            "carries a seasonal lift in enterprise renewals; the renewal book "
            "currently scheduled for Q4 represents 38% of trailing-twelve-month "
            "revenue. No material changes to the cost structure are planned.",
            body,
        )
    )

    story.append(Paragraph("Note", h2))
    story.append(
        Paragraph(
            "All figures are unaudited and presented in U.S. dollars. This document "
            "is a sample filed with the Bayyinah document firewall demonstration. "
            "It contains no concealment, no hidden text, and no embedded payloads. "
            "It is the reference clean-PDF case used to demonstrate the sahih "
            "verdict path on bayyinah.dev/demo.",
            body,
        )
    )

    doc.build(story)
    return out


if __name__ == "__main__":
    path = build()
    print(f"wrote {path} ({path.stat().st_size} bytes)")
