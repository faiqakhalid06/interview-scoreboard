from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ACCENT = colors.HexColor("#2F4BFF")
SOFT = colors.HexColor("#E9ECFF")
LINE = colors.HexColor("#D5D9E2")


def _style(header_rows=1):
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, header_rows - 1), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, header_rows - 1), colors.white),
        ("FONTNAME", (0, 0), (-1, header_rows - 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, header_rows), (-1, -1), [colors.white, colors.HexColor("#F6F7F9")]),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ])


def build_pdf(ranking, criteria, judge_count):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="Interview Results",
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Interview Results", styles["Title"]),
        Paragraph(f"Generated {datetime.now():%d %b %Y, %H:%M} | {judge_count} judges on the panel",
                  styles["Normal"]),
        Spacer(1, 8 * mm),
        Paragraph("Final ranking", styles["Heading2"]),
    ]

    rows = [["Rank", "Candidate", "Position", "Judges", "Score /10"]]
    for r in ranking:
        score = "-" if r["final_score"] is None else f'{r["final_score"]:.2f}'
        rows.append([r["rank"] or "-", r["name"], r["position"], r["judges_scored"], score])
    table = Table(rows, colWidths=[16 * mm, 54 * mm, 52 * mm, 20 * mm, 28 * mm], repeatRows=1)
    st = _style()
    if len(rows) > 1 and ranking[0]["rank"] == 1:
        st.add("BACKGROUND", (0, 1), (-1, 1), SOFT)
        st.add("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold")
    table.setStyle(st)
    story += [table, Spacer(1, 10 * mm), Paragraph("Scoring criteria", styles["Heading2"])]

    crows = [["Criterion", "Weight"]] + [[c.name, f"{c.weight:g}%"] for c in criteria]
    ctable = Table(crows, colWidths=[90 * mm, 30 * mm])
    ctable.setStyle(_style())
    story += [ctable, Spacer(1, 6 * mm),
              Paragraph("Each judge's total is the weighted average of their marks. "
                        "The final score is the average across the judges who scored the candidate.",
                        styles["Italic"])]
    doc.build(story)
    return buf.getvalue()