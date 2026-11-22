from models.database import User, get_session

ROLES = ["Auditor", "Reviewer", "Admin"]


def register_user(username: str, role: str) -> None:
    username = (username or "").strip()
    if not username or role not in ROLES:
        return
    with get_session() as session:
        user = session.query(User).filter_by(username=username).first()
        if user is None:
            session.add(User(username=username, role=role))
        else:
            user.role = role
        session.commit()


def can_finalize(role: str) -> bool:
    """Only a Reviewer or Admin may set a final decision on a finding."""
    return role in ("Reviewer", "Admin")


def is_admin(role: str) -> bool:
    return role == "Admin"
