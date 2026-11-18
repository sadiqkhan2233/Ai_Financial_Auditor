import pandas as pd

from models.database import Document, Transaction, TrialBalanceLine, get_session


def save_trial_balance(df: pd.DataFrame, engagement_id: int, filename: str) -> int:
    with get_session() as session:
        doc = Document(
            engagement_id=engagement_id, filename=filename,
            file_type="Trial Balance", status="Validated",
        )
        session.add(doc)
        session.flush()
        doc_id = doc.id
        session.add_all([
            TrialBalanceLine(
                engagement_id=engagement_id, document_id=doc_id,
                account_code=row.account_code or None, account_name=row.account_name,
                debit=float(row.debit), credit=float(row.credit),
            )
            for row in df.itertuples(index=False)
        ])
        session.commit()
    return doc_id


def save_ledger(df: pd.DataFrame, engagement_id: int, filename: str) -> int:
    with get_session() as session:
        doc = Document(
            engagement_id=engagement_id, filename=filename,
            file_type="General Ledger", status="Validated",
        )
        session.add(doc)
        session.flush()
        doc_id = doc.id
        session.add_all([
            Transaction(
                engagement_id=engagement_id, document_id=doc_id,
                txn_date=row.date.date() if pd.notna(row.date) else None,
                reference=row.reference or None, description=row.description or None,
                account=row.account or None, vendor=row.vendor or None,
                debit=float(row.debit), credit=float(row.credit),
            )
            for row in df.itertuples(index=False)
        ])
        session.commit()
    return doc_id


def save_pdf_document(engagement_id: int, filename: str) -> int:
    with get_session() as session:
        doc = Document(
            engagement_id=engagement_id, filename=filename,
            file_type="PDF", status="Text extracted",
        )
        session.add(doc)
        session.flush()
        doc_id = doc.id
        session.commit()
    return doc_id


def list_documents(limit: int = 20) -> list:
    with get_session() as session:
        docs = session.query(Document).order_by(Document.id.desc()).limit(limit).all()
        return [
            {
                "ID": d.id, "File": d.filename, "Type": d.file_type,
                "Status": d.status, "Uploaded": d.uploaded_at.strftime("%Y-%m-%d %H:%M"),
            }
            for d in docs
        ]
