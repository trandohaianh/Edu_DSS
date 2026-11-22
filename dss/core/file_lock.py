"""Khoá đọc-sửa-ghi dùng chung giữa các LUỒNG và các TIẾN TRÌNH cho các kho JSON cục bộ.

Bước 9 (22/11/2026): app chạy 3–4 tiến trình Streamlit sau Caddy (mỗi người dùng được giữ ở một tiến trình).
Các kho JSON (nhật ký token AI, lịch sử, hàng duyệt quiz, ...) trước đây chỉ khoá bằng ``threading.Lock`` — đủ
cho một tiến trình, nhưng hai tiến trình cùng đọc-sửa-ghi một tệp thì bản ghi của một bên bị mất (bên ghi sau ghi
đè danh sách cũ). ``InterProcessLock`` thay thế trực tiếp cho ``threading.Lock`` (``with _LOCK:``), cộng thêm khoá
tệp của hệ điều hành (``msvcrt`` trên Windows, ``fcntl.flock`` trên Linux — cùng cơ chế ``login_throttle`` và
``auth_service`` đang dùng). Cho phép lồng nhau trong cùng một luồng (RLock).

Đường dẫn tệp khoá được tính LÚC VÀO khoá (không phải lúc import) để tôn trọng ``EDUDSS_DATA_ROOT`` hiện tại.
Không khoá được tệp (ổ chỉ đọc, ...) thì vẫn giữ khoá luồng và ghi cảnh báo — không chặn người dùng.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable, Union

_logger = logging.getLogger(__name__)

PathSource = Union[str, Path, Callable[[], Union[str, Path]]]


class InterProcessLock:
    def __init__(self, lock_path: PathSource) -> None:
        self._source = lock_path
        self._thread = threading.RLock()
        self._depth = 0
        self._file = None

    @classmethod
    def named(cls, name: str) -> InterProcessLock:
        """Khoá theo tên, tệp khoá nằm ở ``<data_root>/locks/<name>.lock``."""

        def _path() -> Path:
            from dss.core.data_root import get_data_root

            return get_data_root() / "locks" / f"{name}.lock"

        return cls(_path)

    def _resolve(self) -> Path:
        src = self._source() if callable(self._source) else self._source
        return Path(src)

    def __enter__(self) -> InterProcessLock:
        self._thread.acquire()
        try:
            if self._depth == 0:
                from dss.security.login_throttle import _os_lock

                try:
                    path = self._resolve()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    self._file = open(path, "a+")
                except OSError as exc:
                    _logger.warning("Không mở được tệp khoá %s (%s); chỉ khoá trong tiến trình.", self._source, exc)
                    self._file = None
                if self._file is not None:
                    _os_lock(self._file)
        except BaseException:
            if self._file is not None:
                self._file.close()
                self._file = None
            self._thread.release()
            raise
        self._depth += 1
        return self

    def __exit__(self, *exc) -> bool:
        self._depth -= 1
        try:
            if self._depth == 0 and self._file is not None:
                from dss.security.login_throttle import _os_unlock

                try:
                    _os_unlock(self._file)
                finally:
                    self._file.close()
                    self._file = None
        finally:
            self._thread.release()
        return False
