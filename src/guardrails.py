"""Input guardrails for CSV files and user questions."""

from pathlib import Path

import pandas as pd

from .config import settings
from .schemas import ValidationOutcome


def validate_csv_file(path: str) -> ValidationOutcome:
    file_path = Path(path)
    if not file_path.exists():
        return ValidationOutcome(reason=f"File not found: {path}")
    if not file_path.is_file() or file_path.suffix.lower() != ".csv":
        return ValidationOutcome(reason="Please provide a .csv file.")
    if file_path.stat().st_size == 0:
        return ValidationOutcome(reason="The CSV file is empty.")

    size_mb = file_path.stat().st_size / 1_048_576
    if size_mb > settings.max_file_size_mb:
        return ValidationOutcome(
            reason=f"File is {size_mb:.1f} MB; the limit is {settings.max_file_size_mb} MB."
        )

    try:
        frame = pd.read_csv(file_path, nrows=settings.max_rows + 1)
    except (UnicodeDecodeError, pd.errors.ParserError, OSError) as error:
        return ValidationOutcome(reason=f"Could not read CSV: {error}")

    if len(frame) < settings.min_rows:
        return ValidationOutcome(reason="The CSV has no data rows.")
    if len(frame) > settings.max_rows:
        return ValidationOutcome(reason=f"CSV exceeds the {settings.max_rows:,}-row limit.")
    if not 1 <= len(frame.columns) <= settings.max_cols:
        return ValidationOutcome(reason=f"CSV must contain 1 to {settings.max_cols} columns.")
    if frame.columns.duplicated().any():
        return ValidationOutcome(reason="CSV has duplicate column names.")

    return ValidationOutcome(is_valid=True)


def validate_question(question: str) -> str | None:
    clean_question = question.strip()
    if not clean_question:
        return "Please describe the analysis you want."
    if len(clean_question) > settings.max_user_text_chars:
        return f"Question is too long (limit: {settings.max_user_text_chars} characters)."

    blocked_phrases = (
        "ignore previous instructions",
        "system prompt",
        "api key",
        "password",
    )
    if any(phrase in clean_question.lower() for phrase in blocked_phrases):
        return "Please ask a question about the CSV rather than instructions or secrets."
    return None
