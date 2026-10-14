import io
import logging

from dss.security.log_redaction import RedactingFormatter, install_log_redaction, redact_text


def test_redact_secret_labels_tokens_and_student_identifiers():
    message = 'password="very secret" api_key=abc123 Authorization: Bearer token123 SV001 learner@example.org'
    safe = redact_text(message)
    for sensitive in ("very secret", "abc123", "token123", "SV001", "learner@example.org"):
        assert sensitive not in safe
    assert "[REDACTED]" in safe


def test_database_password_labels_are_redacted():
    message = "db_password=SYNTHETIC_DB_MARKER database_password=SYNTHETIC_OTHER_MARKER"
    safe = redact_text(message)
    assert "SYNTHETIC_DB_MARKER" not in safe
    assert "SYNTHETIC_OTHER_MARKER" not in safe


def test_log_factory_and_formatter_hide_exception_details():
    old_factory = logging.getLogRecordFactory()
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(RedactingFormatter())
    logger = logging.getLogger("edudss.security.test")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        install_log_redaction()
        try:
            raise RuntimeError("access_token=private-token-123")
        except RuntimeError:
            logger.exception("request failed for SV123")
        logger.info("Authorization: Bearer secret-token-456")
        text = output.getvalue()
        assert "private-token-123" not in text
        assert "secret-token-456" not in text
        assert "SV123" not in text
        assert "exception details redacted" in text
    finally:
        logging.setLogRecordFactory(old_factory)
        logger.removeHandler(handler)
