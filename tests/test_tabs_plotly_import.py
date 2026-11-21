"""Hồi quy: các tab vẽ biểu đồ bằng `go.*` phải tự import plotly.graph_objects.

Trước đây `go` chỉ có nhờ `from dss.config import *`. Khi dss/config.py bỏ dòng
`import plotly.graph_objects as go` (đồng bộ 20/11/2026, commit 093ce58), Trang chủ
sinh viên, Dashboard giảng viên và Phân cụm bị NameError ngay khi đã có mô hình
Production. Test này bắt lỗi đó mà không cần chạy trình duyệt.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_TABS = Path(__file__).resolve().parent.parent / "dss" / "tabs"


def _uses_go(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "go"
        for node in ast.walk(tree)
    )


def _imports_go(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            a.name == "plotly.graph_objects" and a.asname == "go" for a in node.names
        ):
            return True
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "plotly"
            and any(a.name == "graph_objects" and a.asname == "go" for a in node.names)
        ):
            return True
    return False


_FILES = sorted(_TABS.glob("*.py"))


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.name)
def test_tab_that_uses_go_imports_it_explicitly(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    if _uses_go(tree):
        assert _imports_go(tree), f"{path.name} dùng go.* nhưng không import plotly.graph_objects as go"
