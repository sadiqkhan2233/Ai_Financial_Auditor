from models.database import AuditLog, Finding, get_session, log_activity, utcnow
from services.user_service import can_finalize

STATUSES = ["Pending Review", "Under Investigation", "Confirmed Issue", "Cleared - Explained", "Dismissed"]
FINAL_STATUSES = {"Confirmed Issue", "Cleared - Explained", "Dismissed"}
AUDITOR_STATUSES = ["Pending Review", "Under Investigation"]
SEVERITIES = ["High", "Medium", "Low"]


def save_exceptions(engagement_id: int, items: list):
    """Saves transaction-test exceptions as findings. Returns (new_count, skipped_count)."""
    new, skipped = 0, 0
    with get_session() as session:
        existing = {
            (f.title, f.transaction_refs)
            for f in session.query(Finding).filter_by(engagement_id=engagement_id).all()
        }
        for item in items:
            key = (item.title[:200], item.references)
            if key in existing:
                skipped += 1
                continue
            session.add(Finding(
                engagement_id=engagement_id, title=item.title[:200], severity=item.severity,
                method=item.method[:200], explanation=item.explanation, evidence=item.evidence,
                transaction_refs=item.references, review_status=item.review_status,
            ))
            existing.add(key)
            new += 1
        session.commit()
    return new, skipped


def _to_dict(f: Finding) -> dict:
    return {
        "id": f.id, "engagement_id": f.engagement_id, "title": f.title, "severity": f.severity,
        "method": f.method or "", "explanation": f.explanation or "", "evidence": f.evidence or "",
        "transaction_refs": f.transaction_refs or "", "review_status": f.review_status,
        "reviewer": f.reviewer or "", "review_comment": f.review_comment or "",
        "reviewed_at": f.reviewed_at.strftime("%Y-%m-%d %H:%M") if f.reviewed_at else "",
        "created_at": f.created_at.strftime("%Y-%m-%d %H:%M") if f.created_at else "",
    }


def list_findings(engagement_id: int) -> list:
    with get_session() as session:
        rows = session.query(Finding).filter_by(engagement_id=engagement_id).order_by(Finding.id).all()
        return [_to_dict(f) for f in rows]


def get_finding(finding_id: int) -> dict | None:
    with get_session() as session:
        row = session.get(Finding, finding_id)
        return _to_dict(row) if row else None


def findings_summary(engagement_id: int) -> dict:
    findings = list_findings(engagement_id)
    counts = {status: 0 for status in STATUSES}
    for f in findings:
        counts[f["review_status"]] = counts.get(f["review_status"], 0) + 1
    high_open = sum(1 for f in findings
                    if f["severity"] == "High" and f["review_status"] not in FINAL_STATUSES)
    return {"total": len(findings), "counts": counts, "high_open": high_open}


def add_manual_finding(engagement_id, title, severity, explanation, evidence, references, username="Unknown") -> int:
    title = (title or "").strip()
    if not title:
        raise ValueError("Please enter a title for the finding.")
    if severity not in SEVERITIES:
        raise ValueError("Please choose a severity.")
    with get_session() as session:
        finding = Finding(
            engagement_id=engagement_id, title=title[:200], severity=severity, method="Manual entry",
            explanation=(explanation or "").strip(), evidence=(evidence or "").strip(),
            transaction_refs=(references or "").strip(), review_status="Pending Review",
        )
        session.add(finding)
        session.flush()
        finding_id = finding.id
        session.commit()
    log_activity("finding_added", f"finding {finding_id}: {title[:120]}", username=username)
    return finding_id


def update_review(finding_id: int, new_status: str, reviewer: str, role: str, comment: str) -> None:
    """Records a human review. Raises ValueError or PermissionError if the rules are broken."""
    reviewer, comment = (reviewer or "").strip(), (comment or "").strip()
    if new_status not in STATUSES:
        raise ValueError("Unknown review status.")
    if not reviewer:
        raise ValueError("Enter your name in the sidebar first, so the review can be recorded.")
    if new_status in FINAL_STATUSES:
        if not can_finalize(role):
            raise PermissionError("Only a Reviewer or Admin can set a final status.")
        if len(comment) < 5:
            raise ValueError("Please write a short reason for this decision.")

    with get_session() as session:
        finding = session.get(Finding, finding_id)
        if finding is None:
            raise ValueError("That finding no longer exists.")
        if finding.review_status in FINAL_STATUSES and not can_finalize(role):
            raise PermissionError("This finding has a final status. Only a Reviewer or Admin can change it.")
        old_status = finding.review_status
        finding.review_status, finding.reviewer = new_status, reviewer
        finding.review_comment, finding.reviewed_at = comment or None, utcnow()
        session.commit()

    log_activity(
        "finding_reviewed",
        f"finding {finding_id}: {old_status} -> {new_status}; by {reviewer} ({role}); comment: {comment[:200]}",
        username=reviewer,
    )


def finding_history(finding_id: int, limit: int = 10) -> list:
    with get_session() as session:
        rows = (
            session.query(AuditLog)
            .filter(AuditLog.action == "finding_reviewed", AuditLog.details.like(f"finding {finding_id}: %"))
            .order_by(AuditLog.id.desc()).limit(limit).all()
        )
        return [{"time": r.timestamp.strftime("%Y-%m-%d %H:%M"), "details": r.details} for r in rows]
