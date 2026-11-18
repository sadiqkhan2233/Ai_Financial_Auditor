from models.database import Finding, get_session


def save_exceptions(engagement_id: int, items: list):
    """Returns (new_count, skipped_count)."""
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
                engagement_id=engagement_id,
                title=item.title[:200],
                severity=item.severity,
                method=item.method[:200],
                explanation=item.explanation,
                evidence=item.evidence,
                transaction_refs=item.references,
                review_status=item.review_status,
            ))
            existing.add(key)
            new += 1
        session.commit()
    return new, skipped
