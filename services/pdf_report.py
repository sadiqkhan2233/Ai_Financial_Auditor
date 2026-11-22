"""Builds the PDF report with ReportLab. Every number comes from the saved snapshot."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

NAVY = colors.HexColor("#1f3a5f")
LIGHT = colors.HexColor("#eef2f7")
LINE = colors.HexColor("#c5ccd6")
GREY = colors.HexColor("#555555")
WIDTH_CM = 17.4
SEVERITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}
CHECK_WORDS = {"pass": "Pass", "warn": "Warning", "fail": "Fail"}


def _t(value) -> str:
    """Makes any text safe for the PDF. (The built-in font shows Latin characters only.)"""
    text = "" if value is None else str(value)
    text = text.encode("latin-1", "replace").decode("latin-1")
    return escape(text).replace("\n", "<br/>")


def _m(value) -> str:
    return "n/a" if value is None else f"{value:,.0f}"


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontSize=24, textColor=NAVY,
                                alignment=0, spaceAfter=4),
        "h1": ParagraphStyle("h1", parent=base["Heading2"], textColor=NAVY, spaceBefore=14, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=base["Heading3"], textColor=NAVY, spaceBefore=8, spaceAfter=3,
                             fontSize=10),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontSize=9.5, leading=13),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontSize=8, leading=10, textColor=GREY),
        "cell": ParagraphStyle("cell", parent=base["BodyText"], fontSize=8.5, leading=11),
        "cellh": ParagraphStyle("cellh", parent=base["BodyText"], fontSize=8.5, leading=11,
                                textColor=colors.white, fontName="Helvetica-Bold"),
    }


def _table(header, rows, widths_cm, s):
    data = [[Paragraph(_t(h), s["cellh"]) for h in header]]
    data += [[Paragraph(_t(c), s["cell"]) for c in row] for row in rows]
    table = Table(data, colWidths=[w * cm for w in widths_cm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.25, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _kv(rows, s, widths=(4.2, 13.2)):
    data = [[Paragraph(f"<b>{_t(k)}</b>", s["cell"]), Paragraph(_t(v), s["cell"])] for k, v in rows]
    table = Table(data, colWidths=[w * cm for w in widths])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), LIGHT),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _bullets(items, s):
    return [Paragraph("&bull; " + _t(item), s["body"]) for item in items]


def build_pdf(snap: dict, status: dict) -> bytes:
    s = _styles()
    meta, label = snap["meta"], status.get("status", "Draft preview")
    approved = label == "Approved"
    story = []

    story += [Paragraph("Audit Support Report", s["title"]),
              Paragraph("AI-assisted financial audit analysis", s["small"]), Spacer(1, 10)]
    version = f" (version {meta['version']})" if meta.get("version") else ""
    story.append(_kv([
        ("Company", meta["company"]), ("Engagement", meta["engagement"]),
        ("Audit period", f"{meta['period_start'] or 'n/a'} to {meta['period_end'] or 'n/a'}"),
        ("Prepared by", f"{meta['prepared_by'] or 'n/a'} on {meta['generated_at'][:10]}"),
        ("Report status", label + version),
    ], s))
    story.append(Spacer(1, 8))
    notice = Table([[Paragraph(_t(
        "Important: this report is a preliminary analysis that supports a qualified auditor. It is not an audit "
        "opinion. Exceptions are items to investigate and are not proof of fraud or error. Parts of the text "
        "were produced with AI assistance and must be checked against the figures and documents."), s["cell"])]],
        colWidths=[WIDTH_CM * cm])
    notice.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff7e0")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0b84a")),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(notice)

    # 1. Executive summary
    risk, fs = snap["risk"], snap["findings_summary"]
    counts = fs["counts"]
    story.append(Paragraph("1. Executive summary", s["h1"]))
    if risk["overall_score"] is not None:
        story.append(Paragraph(_t(f"Overall preliminary risk: {risk['overall_level']} "
                                  f"({risk['overall_score']:.0f} out of 100)."), s["body"]))
    story.append(Paragraph(_t(
        f"{fs['total']} finding(s) recorded: {counts.get('Confirmed Issue', 0)} confirmed, "
        f"{counts.get('Cleared - Explained', 0) + counts.get('Dismissed', 0)} cleared or dismissed, "
        f"{counts.get('Under Investigation', 0)} under investigation and "
        f"{counts.get('Pending Review', 0)} awaiting review."), s["body"]))
    draft = snap["ai"]["draft"]
    if draft:
        story += [Spacer(1, 4), Paragraph("<b>AI-assisted summary</b> (draft text; verify against this report):",
                                          s["small"]), Paragraph(_t(draft["executive_summary"]), s["body"])]

    # 2. Scope and data
    story.append(Paragraph("2. Scope and data", s["h1"]))
    data = snap["data"]
    story.append(Paragraph(_t(
        f"Trial balance accounts: {data['tb_accounts']}. General ledger lines: {data['ledger_lines']}"
        + (f" (dated {data['ledger_from']} to {data['ledger_to']})." if data["ledger_from"] else ".")), s["body"]))
    if snap["documents"]:
        story += [Spacer(1, 4), _table(["File", "Type", "Status", "Uploaded"],
                                       [[d["filename"], d["type"], d["status"], d["uploaded"]]
                                        for d in snap["documents"]], [7.0, 3.6, 3.6, 3.2], s)]
    if snap["checks"]:
        story += [Spacer(1, 6), Paragraph("Data checks", s["h2"]),
                  _table(["Check", "Result", "Detail"],
                         [[c["check"], CHECK_WORDS.get(c["status"], c["status"]), c["detail"]]
                          for c in snap["checks"]], [4.6, 2.0, 10.8], s)]

    # 3. Financial position and ratios
    story.append(Paragraph("3. Financial position and ratios", s["h1"]))
    st = snap["statements"]
    if st:
        items = [("Total assets", "total_assets"), ("Total liabilities", "total_liabilities"),
                 ("Total equity (including current-period profit)", "total_equity"), ("Revenue", "revenue"),
                 ("Cost of sales", "cost_of_sales"), ("Gross profit", "gross_profit"),
                 ("Operating expenses", "operating_expenses"), ("Net profit", "net_profit")]
        story.append(_table(["Item", "PKR"], [[label_, _m(st[key])] for label_, key in items], [11.4, 6.0], s))
        story += [Spacer(1, 6), _table(["Ratio", "Value", "What it shows"],
                                       [[r["name"], r["text"], r["meaning"]] for r in snap["ratios"]],
                                       [4.6, 3.0, 9.8], s),
                  Paragraph(_t("Account groups were assigned automatically and ratios use year-end balances. "
                               "Ratios should be compared with the industry before drawing conclusions."),
                            s["small"])]
        for point in snap["review_points"]:
            story.append(Paragraph("&bull; " + _t(point), s["body"]))
    else:
        story.append(Paragraph("Not available. No trial balance was saved.", s["body"]))

    # 4. Risk assessment
    story.append(Paragraph("4. Preliminary risk assessment", s["h1"]))
    story.append(_table(["Area", "Score (0-100)", "Level"],
                        [[a["area"], f"{a['score']:.0f}" if a["assessed"] else "-", a["level"]]
                         for a in risk["areas"]], [8.0, 4.7, 4.7], s))
    for area in risk["areas"]:
        story.append(Paragraph(_t(area["area"]), s["h2"]))
        story += _bullets(area["drivers"], s)
    story.append(Paragraph(_t("Scores come from simple rules and are starting points for the auditor's judgement."),
                           s["small"]))

    # 5. Internal controls
    if snap["controls"]:
        story.append(Paragraph("5. Internal controls (questionnaire)", s["h1"]))
        story.append(_table(["Area", "Yes", "Partly", "No", "Don't know", "Score %", "Control risk"],
                            [[c["area"], c["yes"], c["partly"], c["no"], c["unknown"], f"{c['score']:.1f}", c["risk"]]
                             for c in snap["controls"]], [4.6, 1.5, 1.7, 1.5, 2.2, 2.0, 3.9], s))

    # 6. Findings
    story.append(Paragraph("6. Findings and review status", s["h1"]))
    findings = sorted(snap["findings"], key=lambda f: (SEVERITY_ORDER.get(f["severity"], 3), f["id"]))
    if not findings:
        story.append(Paragraph("No findings were recorded.", s["body"]))
    else:
        story.append(_table(["ID", "Severity", "Title", "References", "Status"],
                            [[f"#{f['id']}", f["severity"], f["title"], f["transaction_refs"] or "-",
                              f["review_status"]] for f in findings], [1.2, 1.8, 5.8, 5.0, 3.6], s))
        for f in findings:
            story.append(Paragraph(_t(f"#{f['id']} {f['title']} [{f['severity']}] - {f['review_status']}"), s["h2"]))
            if f["explanation"]:
                story.append(Paragraph(_t(f["explanation"]), s["body"]))
            if f["method"]:
                story.append(Paragraph(_t(f"Method: {f['method']}"), s["small"]))
            if f["review_comment"]:
                story.append(Paragraph(_t(f"Review comment by {f['reviewer'] or 'n/a'} on {f['reviewed_at'] or 'n/a'}: "
                                          f"{f['review_comment']}"), s["body"]))
            if f["evidence"]:
                story.append(Paragraph(_t(f["evidence"][:700]), s["small"]))

    # 7. AI-assisted observations
    story.append(Paragraph("7. AI-assisted observations", s["h1"]))
    if draft:
        story.append(Paragraph(_t(f"AI draft saved {snap['ai']['draft_saved_at'] or ''}. "
                                  f"Quality review status: {snap['ai']['qa_status'] or 'not run'}."), s["small"]))
        story.append(Paragraph("Key findings (AI draft)", s["h2"]))
        story += _bullets(draft["key_findings"], s)
        story += [Paragraph("Risk assessment (AI draft)", s["h2"]), Paragraph(_t(draft["risk_assessment"]), s["body"]),
                  Paragraph("Recommendations (AI draft)", s["h2"])]
        story += _bullets(draft["recommendations"], s)
    else:
        story.append(Paragraph("No AI draft was included in this report.", s["body"]))

    # 8. Limitations
    story.append(Paragraph("8. Limitations", s["h1"]))
    limitations = [
        "This report is a preliminary analysis to support a qualified auditor. It is not an audit opinion.",
        "Account groups were assigned automatically and may need correction.",
        "Exceptions are items to investigate, not proof of fraud or error.",
        "AI-generated text can be wrong. Every statement must be checked against the figures and documents.",
        "Risk scores use simple rules and are starting points for professional judgement.",
    ]
    if draft and draft.get("limitations"):
        limitations.append("AI draft: " + draft["limitations"])
    story += _bullets(limitations, s)

    # 9. Approval
    story.append(Paragraph("9. Approval", s["h1"]))
    rows = [("Prepared by", meta["prepared_by"] or "n/a"), ("Decision", label)]
    if approved:
        rows += [("Approved by", status.get("approved_by") or "n/a"), ("Date", status.get("decided_at") or "n/a"),
                 ("Comment", status.get("comment") or "-")]
    elif label == "Rejected":
        rows += [("Rejected by", status.get("decided_by") or "n/a"), ("Date", status.get("decided_at") or "n/a"),
                 ("Reason", status.get("comment") or "-")]
    else:
        rows.append(("Note", "This report has NOT been approved and must not be released to the client."))
    story.append(_kv(rows, s))

    watermark = None if approved else label.upper()
    top_line = f"{meta['company']}  |  {meta['engagement']}"
    footer = f"Status: {label}  |  AI-assisted analysis. Review by a qualified auditor required."

    def decorate(canvas, doc):
        width, height = A4
        if watermark:
            canvas.saveState()
            canvas.setFont("Helvetica-Bold", 54)
            canvas.setFillColor(colors.Color(0.9, 0.9, 0.9))
            canvas.translate(width / 2, height / 2)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, watermark)
            canvas.restoreState()
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(GREY)
        canvas.drawString(1.8 * cm, height - 1.1 * cm, _plain(top_line))
        canvas.drawString(1.8 * cm, 1.0 * cm, footer)
        canvas.drawRightString(width - 1.8 * cm, 1.0 * cm, f"Page {doc.page}")
        canvas.restoreState()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.6 * cm,
                            title=f"Audit Support Report - {meta['company']}", author=meta["prepared_by"] or "FinAudit AI")
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buffer.getvalue()


def _plain(text: str) -> str:
    return str(text).encode("latin-1", "replace").decode("latin-1")
