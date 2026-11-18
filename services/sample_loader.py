from config.settings import BASE_DIR
from models.database import log_activity
from services.document_processor import process_table, read_table
from services.document_service import save_ledger, save_trial_balance
from services.engagement_service import get_or_create_engagement

SAMPLE_DIR = BASE_DIR / "data" / "sample_data"


def load_sample_data(company: str = "Demo Traders (Pvt) Ltd", title: str = "Audit FY 2025-26") -> int:
    tb_path = SAMPLE_DIR / "sample_trial_balance.csv"
    gl_path = SAMPLE_DIR / "sample_general_ledger.csv"
    if not tb_path.exists() or not gl_path.exists():
        raise FileNotFoundError("Sample files are missing in data/sample_data on GitHub.")

    tb, tb_report = process_table(read_table(tb_path.name, tb_path.read_bytes()), "Trial Balance")
    gl, gl_report = process_table(read_table(gl_path.name, gl_path.read_bytes()), "General Ledger")
    if not (tb_report.passed and gl_report.passed):
        raise ValueError("The sample data did not pass validation.")

    engagement_id = get_or_create_engagement(company, title)
    save_trial_balance(tb, engagement_id, tb_path.name)
    save_ledger(gl, engagement_id, gl_path.name)
    log_activity("sample_data_loaded", f"engagement {engagement_id}")
    return engagement_id
