from models.database import Company, Engagement, get_session


def get_or_create_engagement(company_name: str, engagement_title: str) -> int:
    with get_session() as session:
        company = session.query(Company).filter_by(name=company_name).first()
        if company is None:
            company = Company(name=company_name)
            session.add(company)
            session.flush()

        engagement = (
            session.query(Engagement)
            .filter_by(company_id=company.id, title=engagement_title)
            .first()
        )
        if engagement is None:
            engagement = Engagement(company_id=company.id, title=engagement_title)
            session.add(engagement)
            session.flush()

        engagement_id = engagement.id
        session.commit()
        return engagement_id
