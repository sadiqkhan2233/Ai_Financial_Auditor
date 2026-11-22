"""Builds the Excel workbook with OpenPyXL. Every number comes from the saved snapshot."""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
HEADER_FONT = Font(bold=True, color="FFFFFF")
WRAP = Alignment(wrap_text=True, vertical="top")


def _put(ws, row, col, value, bold=False, number_format=None, wrap=False):
    cell = ws.cell(row=row, column=col, value=value)
    if isinstance(value, str) and value.startswith("="):
        cell.data_type = "s"  # keep text that starts with "=" as text, never as a formula
    if bold:
        cell.font = Font(bold=True)
    if number_format:
        cell.number_format = number_format
    if wrap:
        cell.alignment = WRAP
    return cell


def _header(ws, row, headers):
    for col, text in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=col, value=text)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def _autosize(ws, cap=60):
    widths = {}
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is not None:
                longest = max(len(part) for part in str(cell.value).split("\n"))
                widths[cell.column_letter] = max(widths.get(cell.column_letter, 10), min(longest + 2, cap))
    for letter, width in widths.items():
        ws.column_dimensions[letter].width = width


def _summary(ws, snap, status):
    meta, risk, fs = snap["meta"], snap["risk"], snap["findings_summary"]
    label = status.get("status", "Draft preview")
    _put(ws, 1, 1, "Audit Support Report", bold=True).font = Font(bold=True, size=16)
    ws.cell(row=2, column=1, value="AI-assisted analysis. Not an audit opinion. Review by a qualified auditor required.")
    rows = [
        ("Company", meta["company"]), ("Engagement", meta["engagement"]),
        ("Audit period", f"{meta['period_start'] or 'n/a'} to {meta['period_end'] or 'n/a'}"),
        ("Prepared by", meta["prepared_by"] or "n/a"), ("Generated (UTC)", meta["generated_at"]),
        ("Report status", label),
    ]
    if label == "Approved":
        rows += [("Approved by", status.get("approved_by") or "n/a"), ("Approved on", status.get("decided_at") or "n/a")]
    else:
        rows.append(("Note", "NOT APPROVED. Do not release to the client."))
    rows += [
        ("Overall preliminary risk",
         f"{risk['overall_level']} ({risk['overall_score']:.0f}/100)" if risk["overall_score"] is not None
         else "Not assessed"),
        ("Findings recorded", fs["total"]),
        ("High-severity findings without a final decision", fs["high_open"]),
    ]
    for offset, (key, value) in enumerate(rows, start=4):
        _put(ws, offset, 1, key, bold=True)
        _put(ws, offset, 2, value, wrap=True)
    _autosize(ws)
    ws.column_dimensions["B"].width = 70


def _trial_balance(ws, snap):
    _header(ws, 1, ["Account code", "Account name", "Category", "Debit (PKR)", "Credit (PKR)"])
    row = 2
    for line in snap["trial_balance"]:
        _put(ws, row, 1, line["code"])
        _put(ws, row, 2, line["name"])
        _put(ws, row, 3, line["category"])
        _put(ws, row, 4, line["debit"], number_format="#,##0")
        _put(ws, row, 5, line["credit"], number_format="#,##0")
        row += 1
    if snap["trial_balance"]:
        _put(ws, row, 2, "Total", bold=True)
        _put(ws, row, 4, sum(l["debit"] for l in snap["trial_balance"]), bold=True, number_format="#,##0")
        _put(ws, row, 5, sum(l["credit"] for l in snap["trial_balance"]), bold=True, number_format="#,##0")
    _autosize(ws)


def _statements(ws, snap):
    _header(ws, 1, ["Item", "PKR"])
    st = snap["statements"]
    if not st:
        _put(ws, 2, 1, "No trial balance was saved.")
        return
    items = [("Total assets", "total_assets"), ("Current assets", "current_assets"),
             ("Total liabilities", "total_liabilities"), ("Current liabilities", "current_liabilities"),
             ("Total equity (including current-period profit)", "total_equity"), ("Revenue", "revenue"),
             ("Cost of sales", "cost_of_sales"), ("Gross profit", "gross_profit"),
             ("Operating expenses", "operating_expenses"), ("Finance cost", "finance_cost"),
             ("Net profit", "net_profit")]
    for row, (label, key) in enumerate(items, start=2):
        _put(ws, row, 1, label)
        _put(ws, row, 2, st[key], number_format="#,##0")
    _autosize(ws)


def _ratios(ws, snap):
    _header(ws, 1, ["Group", "Ratio", "Value", "Formula", "What it shows"])
    formats = {"percent": "0.0%", "x": "0.00", "amount": "#,##0"}
    for row, r in enumerate(snap["ratios"], start=2):
        _put(ws, row, 1, r["group"])
        _put(ws, row, 2, r["name"])
        if r["value"] is None:
            _put(ws, row, 3, "n/a")
        else:
            _put(ws, row, 3, r["value"], number_format=formats.get(r["kind"], "0.00"))
        _put(ws, row, 4, r["formula"], wrap=True)
        _put(ws, row, 5, r["meaning"], wrap=True)
    _autosize(ws)


def _risk(ws, snap):
    _header(ws, 1, ["Area", "Score (0-100)", "Level", "What drives the score"])
    for row, area in enumerate(snap["risk"]["areas"], start=2):
        _put(ws, row, 1, area["area"])
        _put(ws, row, 2, area["score"] if area["assessed"] else "Not assessed", number_format="0.0")
        _put(ws, row, 3, area["level"])
        _put(ws, row, 4, "\n".join(area["drivers"]), wrap=True)
    _autosize(ws)


def _controls(ws, snap):
    _header(ws, 1, ["Area", "Yes", "Partly", "No", "Don't know", "Not answered", "Score %", "Control risk"])
    if not snap["controls"]:
        _put(ws, 2, 1, "The questionnaire was not answered.")
    for row, c in enumerate(snap["controls"], start=2):
        for col, key in enumerate(["area", "yes", "partly", "no", "unknown", "unanswered", "score", "risk"], start=1):
            _put(ws, row, col, c[key])
    _autosize(ws)


def _findings(ws, snap):
    _header(ws, 1, ["ID", "Severity", "Title", "References", "Method", "Explanation", "Evidence",
                    "Status", "Reviewer", "Reviewed at", "Reviewer comment"])
    for row, f in enumerate(snap["findings"], start=2):
        values = [f["id"], f["severity"], f["title"], f["transaction_refs"], f["method"], f["explanation"],
                  f["evidence"], f["review_status"], f["reviewer"], f["reviewed_at"], f["review_comment"]]
        for col, value in enumerate(values, start=1):
            _put(ws, row, col, value, wrap=col in (3, 4, 6, 7, 11))
    _autosize(ws, cap=50)


def _checks(ws, snap):
    _header(ws, 1, ["Check", "Result", "Detail"])
    for row, c in enumerate(snap["checks"], start=2):
        _put(ws, row, 1, c["check"])
        _put(ws, row, 2, {"pass": "Pass", "warn": "Warning", "fail": "Fail"}.get(c["status"], c["status"]))
        _put(ws, row, 3, c["detail"], wrap=True)
    _autosize(ws)


def build_excel(snap: dict, status: dict) -> bytes:
    wb = Workbook()
    _summary(wb.active, snap, status)
    wb.active.title = "Summary"
    _trial_balance(wb.create_sheet("Trial Balance"), snap)
    _statements(wb.create_sheet("Financial Statements"), snap)
    _ratios(wb.create_sheet("Ratios"), snap)
    _risk(wb.create_sheet("Risk"), snap)
    _controls(wb.create_sheet("Controls"), snap)
    _findings(wb.create_sheet("Findings"), snap)
    _checks(wb.create_sheet("Data Checks"), snap)
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
