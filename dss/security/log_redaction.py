"""Best-effort redaction for application logs; do not log raw prompts or files."""

from __future__ import annotations

import logging
import re

_PATTERNS = (
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+"), "Bearer [REDACTED]"),
    (
        re.compile(
            r"(?i)\b(db[_-]?password|database[_-]?password|password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token|session[_-]?token|authorization|secret|prompt)\b[\"']?\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
        ),
        r"\1=[REDACTED]",
    ),
    (re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|gsk_[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{20,})\b"), "[REDACTED]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL REDACTED]"),
    (re.compile(r"(?i)\bSV\d{3,}\b"), "SV[REDACTED]"),
)

# Bước 7 (21/11/2026): tên đăng nhập (có thể là mã SV không theo mẫu "SV...", hoặc tên thật) không
# được ghi nguyên văn. Thay bằng mã băm ngắn: vẫn lần theo được cùng một tài khoản trong log
# (ví dụ nhiều lần đăng nhập sai) mà không lộ tên.
_USERNAME_RE = re.compile(r"(?i)\b(username|user_id|user)=([^\s,;]+)")


def _hash_username(match: re.Match) -> str:
    import hashlib

    digest = hashlib.sha256(match.group(2).strip("'\"").lower().encode("utf-8")).hexdigest()[:10]
    return f"{match.group(1)}=u#{digest}"


def redact_text(value: object) -> str:
    text = str(value)
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return _USERNAME_RE.sub(_hash_username, text)


class RedactingFormatter(logging.Formatter):
    def __init__(self, original: logging.Formatter | None = None):
        super().__init__()
        self.original = original or logging.Formatter("%(levelname)s:%(name)s:%(message)s")

    def format(self, record: logging.LogRecord) -> str:
        return redact_text(self.original.format(record))


def install_log_redaction() -> None:
    """Redact existing handlers and future records before any handler sees them."""
    old_factory = logging.getLogRecordFactory()
    if getattr(old_factory, "_edudss_redacting", False):
        return

    def factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - lỗi định dạng (%s thiếu/thừa đối số) không được làm hỏng code đang log
            # logging thường chỉ báo lỗi này qua Handler.handleError; trong record factory nó ném thẳng vào nơi gọi.
            message = (
                f"{record.msg} [log format error; args={len(record.args) if isinstance(record.args, tuple) else 1}]"
            )
        record.msg = redact_text(message)
        record.args = ()
        if record.exc_info and record.exc_info[1] is not None:
            message = str(record.exc_info[1])
            if redact_text(message) != message:
                record.exc_info = None
                record.msg += " [exception details redacted]"
        return record

    factory._edudss_redacting = True
    logging.setLogRecordFactory(factory)
    loggers = [logging.getLogger()]
    loggers.extend(logger for logger in logging.root.manager.loggerDict.values() if isinstance(logger, logging.Logger))
    for logger in loggers:
        for handler in logger.handlers:
            if not isinstance(handler.formatter, RedactingFormatter):
                handler.setFormatter(RedactingFormatter(handler.formatter))
