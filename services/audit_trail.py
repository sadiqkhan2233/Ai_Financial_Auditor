from datetime import datetime, time, timedelta

from sqlalchemy import or_

from models.database import AuditLog, get_session

PKT = timedelta(hours=5)


def distinct_users() -> list:
    with get_session() as session:
        return sorted(r[0] for r in session.query(AuditLog.username).distinct() if r[0])


def distinct_actions() -> list:
    with get_session() as session:
        return sorted(r[0] for r in session.query(AuditLog.action).distinct() if r[0])


def query_logs(user="", action="", text="", since=None, until=None, limit=2000) -> list:
    """Dates are Pakistan dates. Returns newest first."""
    with get_session() as session:
        query = session.query(AuditLog)
        if user:
            query = query.filter(AuditLog.username == user)
        if action:
            query = query.filter(AuditLog.action == action)
        if text:
            like = f"%{text}%"
            query = query.filter(or_(AuditLog.details.ilike(like), AuditLog.action.ilike(like),
                                     AuditLog.username.ilike(like)))
        if since:
            query = query.filter(AuditLog.timestamp >= datetime.combine(since, time.min) - PKT)
        if until:
            query = query.filter(AuditLog.timestamp <= datetime.combine(until, time.max) - PKT)
        rows = query.order_by(AuditLog.id.desc()).limit(limit).all()
        return [
            {"Time (PKT)": (r.timestamp + PKT).strftime("%Y-%m-%d %H:%M:%S"), "User": r.username,
             "Action": r.action, "Details": r.details or ""}
            for r in rows
        ]
