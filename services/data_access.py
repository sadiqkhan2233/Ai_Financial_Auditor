import pandas as pd
from sqlalchemy import func

from models.database import Company, Engagement, Transaction, TrialBalanceLine, get_session


def list_engagements() -> list:
    with get_session() as session:
        rows = (
            session.query(Engagement, Company)
            .join(Company, Engagement.company_id == Company.id)
            .order_by(Engagement.id.desc())
            .all()
        )
        return [{"id": e.id, "label": f"{c.name} | {e.title}"} for e, c in rows]


def load_trial_balance(engagement_id: int) -> pd.DataFrame:
    """The most recently saved trial balance of the engagement."""
    with get_session() as session:
        latest = (
            session.query(func.max(TrialBalanceLine.document_id))
            .filter(TrialBalanceLine.engagement_id == engagement_id)
            .scalar()
        )
        if latest is None:
            return pd.DataFrame()
        rows = (
            session.query(TrialBalanceLine)
            .filter_by(engagement_id=engagement_id, document_id=latest)
            .order_by(TrialBalanceLine.id)
            .all()
        )
        return pd.DataFrame([
            {"account_code": r.account_code or "", "account_name": r.account_name,
             "debit": r.debit, "credit": r.credit}
            for r in rows
        ])


def load_transactions(engagement_id: int) -> pd.DataFrame:
    """The most recently saved general ledger of the engagement."""
    with get_session() as session:
        latest = (
            session.query(func.max(Transaction.document_id))
            .filter(Transaction.engagement_id == engagement_id)
            .scalar()
        )
        if latest is None:
            return pd.DataFrame()
        rows = (
            session.query(Transaction)
            .filter_by(engagement_id=engagement_id, document_id=latest)
            .order_by(Transaction.id)
            .all()
        )
        df = pd.DataFrame([
            {"date": r.txn_date, "reference": r.reference or "", "description": r.description or "",
             "account": r.account or "", "vendor": r.vendor or "", "debit": r.debit, "credit": r.credit}
            for r in rows
        ])
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df
