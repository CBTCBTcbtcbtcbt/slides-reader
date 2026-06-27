"""PDF 服务里 LibreOffice 路径解析的单元测试。"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest


PROJECT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_DIR / "backend"


@pytest.fixture()
def pdf_service_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """重新导入 pdf_service，让每个测试都能独立修改模块级路径。"""

    # 后端源码使用 config、repositories 这类直接导入名，所以测试前把 backend 加入导入路径。
    monkeypatch.syspath_prepend(str(BACKEND_DIR))

    # 清理相关模块缓存，避免其他测试留下的环境变量或模块属性影响本测试。
    for module_name in list(sys.modules):
        if module_name in {"config", "pdf_service"} or module_name.startswith("repositories"):
            sys.modules.pop(module_name, None)

    return importlib.import_module("pdf_service")


def test_pdf_service_finds_release_direct_libreoffice_layout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    pdf_service_module: ModuleType,
) -> None:
    """后端应能找到 tools/libreoffice/App 下的 soffice.exe。"""

    fake_backend_dir = tmp_path / "backend"
    fake_soffice = (
        tmp_path
        / "tools"
        / "libreoffice"
        / "App"
        / "libreoffice"
        / "program"
        / "soffice.exe"
    )
    fake_soffice.parent.mkdir(parents=True)
    fake_soffice.write_text("", encoding="utf-8")

    # BASE_DIR 是 pdf_service 从 config 导入的模块级变量，改它就能模拟 release 根目录。
    monkeypatch.setattr(pdf_service_module, "BASE_DIR", fake_backend_dir)
    monkeypatch.delenv("SLIDES_READER_SOFFICE_PATH", raising=False)

    assert pdf_service_module.resolve_soffice_path() == fake_soffice.resolve()

