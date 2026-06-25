"""启动器 start.py 的轻量单元测试。

这些测试只验证参数解析、路径推导和浏览器打开策略，不启动真实后端，也不安装依赖。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


PROJECT_DIR = Path(__file__).resolve().parents[2]
START_PATH = PROJECT_DIR / "start.py"


def load_start_module() -> ModuleType:
    """把项目根目录的 start.py 当作普通 Python 模块导入。"""

    spec = importlib.util.spec_from_file_location("slides_reader_start", START_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cli_arguments_override_environment_values(monkeypatch) -> None:
    """命令行参数优先级应高于环境变量。"""

    start = load_start_module()
    monkeypatch.setenv("SLIDES_READER_HOST", "127.0.0.1")
    monkeypatch.setenv("SLIDES_READER_PORT", "9000")
    monkeypatch.setenv("SLIDES_READER_OPEN_BROWSER", "0")
    monkeypatch.setenv("SLIDES_READER_LOG_LEVEL", "DEBUG")

    options = start.build_launcher_options(
        [
            "--host",
            "0.0.0.0",
            "--port",
            "8010",
            "--log-level",
            "WARNING",
        ],
    )

    assert options.host == "0.0.0.0"
    assert options.port == 8010
    assert options.open_browser is False
    assert options.log_level == "WARNING"


def test_environment_values_override_defaults(monkeypatch) -> None:
    """没有命令行参数时，应使用环境变量覆盖默认值。"""

    start = load_start_module()
    monkeypatch.setenv("SLIDES_READER_HOST", "127.0.0.1")
    monkeypatch.setenv("SLIDES_READER_BACKEND_PORT", "8020")
    monkeypatch.setenv("SLIDES_READER_SKIP_FRONTEND_BUILD", "1")
    monkeypatch.setenv("SLIDES_READER_LOG_LEVEL", "DEBUG")

    options = start.build_launcher_options([])

    assert options.host == "127.0.0.1"
    assert options.port == 8020
    assert options.skip_frontend_build is True
    assert options.log_level == "DEBUG"


def test_storage_paths_follow_custom_storage_dir(tmp_path) -> None:
    """自定义 storage 目录时，日志目录也应该跟随变化。"""

    start = load_start_module()
    paths = start.build_runtime_paths(PROJECT_DIR, tmp_path / "custom-storage")

    assert paths.storage_dir == tmp_path / "custom-storage"
    assert paths.log_dir == tmp_path / "custom-storage" / "logs"
    assert paths.launcher_log == tmp_path / "custom-storage" / "logs" / "launcher.log"
    assert paths.diagnostics_log == tmp_path / "custom-storage" / "logs" / "diagnostics.txt"


def test_open_browser_respects_no_open_option(monkeypatch) -> None:
    """禁用自动打开浏览器时，不应调用 webbrowser.open。"""

    start = load_start_module()
    opened_urls: list[str] = []
    monkeypatch.setattr(start.webbrowser, "open", lambda url: opened_urls.append(url))

    assert start.maybe_open_browser("http://localhost:8000/", should_open=False) is False
    assert opened_urls == []


def test_open_browser_calls_webbrowser_when_enabled(monkeypatch) -> None:
    """默认自动打开浏览器时，应调用 webbrowser.open。"""

    start = load_start_module()
    opened_urls: list[str] = []
    monkeypatch.setattr(start.webbrowser, "open", lambda url: opened_urls.append(url) or True)

    assert start.maybe_open_browser("http://localhost:8000/", should_open=True) is True
    assert opened_urls == ["http://localhost:8000/"]


def test_backend_command_avoids_unsupported_python_log_config(tmp_path) -> None:
    """uvicorn 的 --log-config 不支持 .py 文件，启动命令不能传 Python 日志配置文件。"""

    start = load_start_module()
    command = start.build_backend_command(tmp_path / "python.exe", "127.0.0.1", 8010)

    assert command == [
        str(tmp_path / "python.exe"),
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8010",
    ]
