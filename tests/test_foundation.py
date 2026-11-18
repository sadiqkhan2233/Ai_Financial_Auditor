import pytest

from config.settings import get_settings
from models.database import AuditLog, get_session, init_db, log_activity
from services.llm_service import LLMError, LLMService


def test_default_model_is_configurable(monkeypatch):
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    assert get_settings().groq_model == "openai/gpt-oss-120b"
    monkeypatch.setenv("GROQ_MODEL", "some/other-model")
    assert get_settings().groq_model == "some/other-model"


def test_database_logging(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    init_db(url)
    log_activity("hello", "test", url=url)
    with get_session(url) as session:
        assert session.query(AuditLog).count() == 1


def test_missing_api_key_gives_clear_error(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(LLMError):
        LLMService()
