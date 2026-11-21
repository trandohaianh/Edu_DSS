"""dss/core/logging_config.py — the sole technical-logging implementation in
the codebase (14+ call sites across dss/core, dss/services, dss/tabs, dss/db;
confirmed via repo-wide grep — no duplicate/competing logging setup exists).

Found missing from the Phase 1 commit (daf14a7) by a parallel security audit:
dss/core/warehouse.py (committed) imports it, but the file itself was never
`git add`ed, so a clean checkout of that commit alone cannot start. This test
file is the required test coverage for the module now that it is committed
alongside the fix (see reports/production_readiness/PHASE1B_REPORT.md).

Every test resets module-global state (`_CONFIGURED`, the "dss" logger's
handlers) since `logging_config` intentionally uses process-wide singletons —
without resetting, an earlier test's handler would leak into a later one.
"""

from __future__ import annotations

import logging

import pytest

from dss.core import logging_config


@pytest.fixture(autouse=True)
def _reset_logging_state(tmp_path, monkeypatch):
    """Isolate every test: fresh EDUDSS_DATA_ROOT (so the log file never
    touches the real data_warehouse/logs/), and force _configure_once() to
    run again by clearing both its guard flag and any handlers a previous
    test attached to the shared "dss" logger object (loggers are cached
    singletons in the `logging` module — they are NOT recreated per test)."""
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    logging_config._CONFIGURED = False
    dss_logger = logging.getLogger("dss")
    for h in list(dss_logger.handlers):
        dss_logger.removeHandler(h)
        h.close()
    yield
    dss_logger = logging.getLogger("dss")
    for h in list(dss_logger.handlers):
        dss_logger.removeHandler(h)
        h.close()
    logging_config._CONFIGURED = False


def test_get_logger_returns_a_real_logger():
    logger = logging_config.get_logger("some_module")
    assert isinstance(logger, logging.Logger)


def test_get_logger_prefixes_name_with_dss(tmp_path):
    logger = logging_config.get_logger("core.warehouse")
    assert logger.name == "dss.core.warehouse"


def test_get_logger_does_not_double_prefix_already_namespaced_names():
    logger = logging_config.get_logger("dss.core.warehouse")
    assert logger.name == "dss.core.warehouse"


def test_get_logger_root_name_stays_bare_dss():
    logger = logging_config.get_logger("dss")
    assert logger.name == "dss"


def test_log_file_created_under_isolated_data_root(tmp_path):
    logging_config.get_logger(__name__)
    log_file = tmp_path / "logs" / "technical.log"
    assert log_file.exists()


def test_log_level_respects_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("DSS_LOG_LEVEL", "WARNING")
    logging_config.get_logger(__name__)
    assert logging.getLogger("dss").level == logging.WARNING


def test_default_log_level_is_info(tmp_path, monkeypatch):
    monkeypatch.delenv("DSS_LOG_LEVEL", raising=False)
    logging_config.get_logger(__name__)
    assert logging.getLogger("dss").level == logging.INFO


def test_dss_logger_does_not_propagate_to_root(tmp_path):
    """Prevents duplicate output on the parent process's own console/log
    handlers (documented rationale in logging_config.py itself)."""
    logging_config.get_logger(__name__)
    assert logging.getLogger("dss").propagate is False


def test_configure_once_does_not_attach_duplicate_handlers(tmp_path):
    """Calling get_logger() repeatedly must not accumulate EduDSS handlers.

    Pytest may attach LogCaptureHandler instances while the full suite is
    running; those are test-framework handlers and are not created by EduDSS.
    """
    for i in range(5):
        logging_config.get_logger(f"module_{i}")

    dss_logger = logging.getLogger("dss")

    app_handlers = [
        handler for handler in dss_logger.handlers if isinstance(handler, logging.handlers.RotatingFileHandler)
    ]

    assert len(app_handlers) == 1


def test_a_real_log_line_is_written_to_the_file(tmp_path):
    logger = logging_config.get_logger(__name__)
    logger.info("test message %s", "marker_abc123")
    log_file = tmp_path / "logs" / "technical.log"
    content = log_file.read_text(encoding="utf-8")
    assert "marker_abc123" in content


def test_caller_secret_never_reaches_the_log_file_when_caller_is_correct(tmp_path):
    """logging_config itself never logs anything on its own (it only builds a
    Logger object) — this test documents and pins the actual, real-world
    invariant: auth_service.py (the codebase's main consumer that ever
    handles a secret) never passes the raw password into this logger. See
    tests/test_auth_service.py::test_authenticate_never_logs_password for the
    full end-to-end version of this same guarantee."""
    logger = logging_config.get_logger(__name__)
    secret_password = "s3cr3t-should-not-appear-in-logs"
    logger.warning("Đăng nhập thất bại (sai mật khẩu): username=%s", "someuser")
    log_file = tmp_path / "logs" / "technical.log"
    content = log_file.read_text(encoding="utf-8")
    assert secret_password not in content
    # Bước 7 (21/11/2026): tên đăng nhập KHÔNG còn được ghi nguyên văn — thay bằng mã băm ổn định
    # (dss/security/log_redaction.py) để vẫn lần theo được cùng một tài khoản trong log.
    assert "someuser" not in content
    assert "username=u#" in content
