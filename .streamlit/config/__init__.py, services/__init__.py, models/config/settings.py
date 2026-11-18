import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _get_secret(name, default=None):
    """Look in Streamlit Secrets first, then in environment variables."""
    try:
        import streamlit as st
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    groq_api_key: str | None
    groq_model: str
    database_url: str
    max_upload_mb: int
    app_name: str = "FinAudit AI"


def get_settings() -> Settings:
    default_db = f"sqlite:///{BASE_DIR / 'data' / 'finaudit.db'}"
    return Settings(
        groq_api_key=_get_secret("GROQ_API_KEY"),
        groq_model=_get_secret("GROQ_MODEL", "openai/gpt-oss-120b"),
        database_url=_get_secret("DATABASE_URL", default_db),
        max_upload_mb=int(_get_secret("MAX_UPLOAD_MB", "10")),
    )
