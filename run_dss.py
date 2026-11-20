"""
Điểm vào Streamlit cho DSS (chạy từ thư mục gốc project).

    cd <thư mục repo>
    streamlit run run_dss.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dss.security.log_redaction import install_log_redaction

install_log_redaction()

# Each Streamlit script rerun represents one UI operation trace.
from dss.core.observability import new_correlation_id

new_correlation_id()

_MAIN = _ROOT / "dss" / "main.py"
_source = _MAIN.read_text(encoding="utf-8")
_code = compile(_source, str(_MAIN), "exec")
_globals = {"__name__": "__main__", "__file__": str(_MAIN)}

# Dev/test only: EDUDSS_PROFILE_DIR=<thư mục> -> mỗi lượt chạy lại ghi 1 file
# cProfile (.prof) để tìm đoạn code làm trang chậm. Không đặt biến -> không tốn gì.
_profile_dir = __import__("os").environ.get("EDUDSS_PROFILE_DIR")
if _profile_dir:
    import cProfile
    import time as _t

    _prof = cProfile.Profile()
    try:
        _prof.runctx("exec(_code, _globals)", {"_code": _code, "_globals": _globals, "exec": exec}, {})
    finally:
        Path(_profile_dir).mkdir(parents=True, exist_ok=True)
        _prof.dump_stats(str(Path(_profile_dir) / f"run_{_t.time():.3f}.prof"))
else:
    exec(_code, _globals)
