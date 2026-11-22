import json

from models.database import AgentResult, get_session, utcnow


def save_agent_result(engagement_id: int, agent_key: str, result: dict) -> None:
    payload = json.dumps(result, default=str)
    with get_session() as session:
        row = session.query(AgentResult).filter_by(engagement_id=engagement_id, agent_key=agent_key).first()
        if row is None:
            session.add(AgentResult(engagement_id=engagement_id, agent_key=agent_key, output_json=payload))
        else:
            row.output_json, row.updated_at = payload, utcnow()
        session.commit()


def load_agent_results(engagement_id: int) -> dict:
    results = {}
    with get_session() as session:
        for row in session.query(AgentResult).filter_by(engagement_id=engagement_id).all():
            try:
                data = json.loads(row.output_json)
            except ValueError:
                continue
            data["saved_at"] = row.updated_at.strftime("%Y-%m-%d %H:%M")
            results[row.agent_key] = data
    return results
