from pathlib import Path

from config.settings import get_settings

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".pdf"}


def validate_upload(filename: str, data: bytes):
    """Returns (True, 'OK') or (False, 'reason')."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, "Only CSV, Excel (.xlsx) and PDF files are allowed."
    if len(data) == 0:
        return False, "The file is empty."

    limit_mb = get_settings().max_upload_mb
    size_mb = len(data) / (1024 * 1024)
    if size_mb > limit_mb:
        return False, f"The file is {size_mb:.1f} MB. The limit is {limit_mb} MB."

    if ext == ".pdf" and not data.startswith(b"%PDF"):
        return False, "This file is named .pdf but is not a real PDF."
    if ext == ".xlsx" and not data.startswith(b"PK"):
        return False, "This file is named .xlsx but is not a real Excel file."
    return True, "OK"
