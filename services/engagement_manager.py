from datetime import date

from models.database import (
    AgentResult, Company, Document, Engagement, Finding, Report, Transaction,
    TrialBalanceLine, get_session, log_activity,
)
from services.user_service import is_admin

STATUSES = ["Planning", "Fieldwork", "Review", "Completed"]


def list_engagements_detailed() -> list:
    with get_session() as session:
        rows = (
            session.query(Engagement, Company)
            .join(Company, Engagement.company_id == Company.id)
            .order_by(Engagement.id.desc())
            .all()
        )
        result = []
        for engagement, company in rows:
            findings = session.query(Finding).filter_by(engagement_id=engagement.id)
            result.append({
                "id": engagement.id, "company_id": company.id, "company": company.name,
                "title": engagement.title, "status": engagement.status,
                "period_start": engagement.period_start, "period_end": engagement.period_end,
                "documents": session.query(Document).filter_by(engagement_id=engagement.id).count(),
                "findings": findings.count(),
                "pending": findings.filter(Finding.review_status == "Pending Review").count(),
            })
        return result


def _check(title, status, period_start, period_end):
    if not (title or "").strip():
        raise ValueError("Please enter an engagement title.")
    if status not in STATUSES:
        raise ValueError("Unknown status.")
    if period_start and period_end and period_end < period_start:
        raise ValueError("The period end date is before the start date.")


def create_engagement(company_id, title, period_start: date | None, period_end: date | None,
                      status="Planning", username="system") -> int:
    title = (title or "").strip()
    _check(title, status, period_start, period_end)
    with get_session() as session:
        if session.get(Company, company_id) is None:
            raise ValueError("Please choose a company.")
        if session.query(Engagement).filter_by(company_id=company_id, title=title).first():
            raise ValueError("This company already has an engagement with that title.")
        engagement = Engagement(company_id=company_id, title=title, status=status,
                                period_start=period_start, period_end=period_end)
        session.add(engagement)
        session.flush()
        engagement_id = engagement.id
        session.commit()
    log_activity("engagement_created", f"{title} (id {engagement_id})", username=username)
    return engagement_id


def update_engagement(engagement_id, title, status, period_start, period_end, username="system") -> None:
    title = (title or "").strip()
    _check(title, status, period_start, period_end)
    with get_session() as session:
        engagement = session.get(Engagement, engagement_id)
        if engagement is None:
            raise ValueError("That engagement no longer exists.")
        engagement.title, engagement.status = title, status
        engagement.period_start, engagement.period_end = period_start, period_end
        session.commit()
    log_activity("engagement_updated", f"{title} (id {engagement_id}), status {status}", username=username)


def delete_engagement(engagement_id, role, username="system") -> dict:
    """Deletes an engagement and everything saved under it. The activity log is kept."""
    if not is_admin(role):
        raise PermissionError("Only an Admin can delete an engagement.")
    removed = {}
    with get_session() as session:
        engagement = session.get(Engagement, engagement_id)
        if engagement is None:
            raise ValueError("That engagement no longer exists.")
        title = engagement.title
        for label, model in [("findings", Finding), ("reports", Report), ("transactions", Transaction),
                             ("trial balance lines", TrialBalanceLine), ("AI results", AgentResult),
                             ("documents", Document)]:
            removed[label] = session.query(model).filter_by(engagement_id=engagement_id).delete()
        session.delete(engagement)
        session.commit()
    log_activity("engagement_deleted", f"{title} (id {engagement_id}); removed {removed}", username=username)
    return removed
