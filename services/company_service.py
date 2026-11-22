from sqlalchemy import func

from models.database import Company, Engagement, get_session, log_activity
from services.user_service import is_admin


def _clean(value):
    return (value or "").strip() or None


def list_companies() -> list:
    with get_session() as session:
        counts = dict(
            session.query(Engagement.company_id, func.count(Engagement.id)).group_by(Engagement.company_id).all()
        )
        rows = session.query(Company).order_by(Company.name).all()
        return [
            {"id": c.id, "name": c.name, "ntn": c.ntn or "", "industry": c.industry or "",
             "city": c.city or "", "engagements": counts.get(c.id, 0)}
            for c in rows
        ]


def _name_taken(session, name, exclude_id=None) -> bool:
    query = session.query(Company).filter(func.lower(Company.name) == name.lower())
    if exclude_id:
        query = query.filter(Company.id != exclude_id)
    return query.first() is not None


def create_company(name, ntn="", industry="", city="", username="system") -> int:
    name = (name or "").strip()
    if not name:
        raise ValueError("Please enter the company name.")
    with get_session() as session:
        if _name_taken(session, name):
            raise ValueError(f"A company called '{name}' already exists.")
        company = Company(name=name, ntn=_clean(ntn), industry=_clean(industry), city=_clean(city))
        session.add(company)
        session.flush()
        company_id = company.id
        session.commit()
    log_activity("company_created", f"{name} (id {company_id})", username=username)
    return company_id


def update_company(company_id, name, ntn="", industry="", city="", username="system") -> None:
    name = (name or "").strip()
    if not name:
        raise ValueError("Please enter the company name.")
    with get_session() as session:
        company = session.get(Company, company_id)
        if company is None:
            raise ValueError("That company no longer exists.")
        if _name_taken(session, name, exclude_id=company_id):
            raise ValueError(f"A company called '{name}' already exists.")
        company.name, company.ntn = name, _clean(ntn)
        company.industry, company.city = _clean(industry), _clean(city)
        session.commit()
    log_activity("company_updated", f"{name} (id {company_id})", username=username)


def delete_company(company_id, role, username="system") -> None:
    if not is_admin(role):
        raise PermissionError("Only an Admin can delete a company.")
    with get_session() as session:
        company = session.get(Company, company_id)
        if company is None:
            raise ValueError("That company no longer exists.")
        if session.query(Engagement).filter_by(company_id=company_id).count():
            raise ValueError("This company still has engagements. Delete those first.")
        name = company.name
        session.delete(company)
        session.commit()
    log_activity("company_deleted", f"{name} (id {company_id})", username=username)
