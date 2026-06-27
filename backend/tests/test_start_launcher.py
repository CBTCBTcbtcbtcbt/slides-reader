"""启动器 start.py 的轻量单元测试。

这些测试只验证参数解析、路径推导和浏览器打开策略，不启动真实后端，也不安装依赖。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


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


def test_release_mode_uses_runtime_python_and_release_paths(monkeypatch, tmp_path) -> None:
    """发行版模式应使用 runtime/python，并把临时目录和工具目录限制在 release 根目录内。"""

    start = load_start_module()
    monkeypatch.setenv("SLIDES_READER_RELEASE_MODE", "1")
    paths = start.build_runtime_paths(tmp_path, tmp_path / "storage")

    assert start.is_release_mode() is True
    assert start.backend_python(paths) == tmp_path / "runtime" / "python" / "python.exe"
    assert paths.tmp_dir == tmp_path / "storage" / "tmp"
    assert paths.tools_dir == tmp_path / "tools"
    assert paths.download_dir == tmp_path / "tools" / "downloads"
    assert paths.libreoffice_root == tmp_path / "tools" / "libreoffice"
    assert (
        paths.portable_soffice
        == tmp_path
        / "tools"
        / "libreoffice"
        / "LibreOfficePortable"
        / "App"
        / "libreoffice"
        / "program"
        / "soffice.exe"
    )


def test_source_mode_keeps_backend_venv_python(monkeypatch, tmp_path) -> None:
    """源码模式应继续使用 backend/.venv，避免破坏当前开发启动方式。"""

    start = load_start_module()
    monkeypatch.delenv("SLIDES_READER_RELEASE_MODE", raising=False)
    paths = start.build_runtime_paths(tmp_path, tmp_path / "storage")

    assert start.is_release_mode() is False
    assert start.backend_python(paths) == tmp_path / "backend" / ".venv" / "Scripts" / "python.exe"


def test_release_options_force_storage_under_root(monkeypatch) -> None:
    """发行版模式应忽略自定义 storage，保证运行数据留在 release 文件夹内。"""

    start = load_start_module()
    monkeypatch.setenv("SLIDES_READER_RELEASE_MODE", "1")

    options = start.build_launcher_options(
        [],
        {
            "SLIDES_READER_RELEASE_MODE": "1",
            "SLIDES_READER_STORAGE_DIR": r"C:\outside-storage",
        },
    )

    assert options.storage_dir == start.ROOT_DIR / "storage"


def test_release_frontend_requires_existing_dist(monkeypatch, tmp_path) -> None:
    """发行版模式不应尝试构建前端，缺少 frontend/dist 时应直接失败。"""

    start = load_start_module()
    monkeypatch.setenv("SLIDES_READER_RELEASE_MODE", "1")
    paths = start.build_runtime_paths(tmp_path, tmp_path / "storage")

    with pytest.raises(RuntimeError, match="frontend/dist/index.html"):
        start.run_frontend_build({}, paths)


def test_resolve_soffice_prefers_environment_path(monkeypatch, tmp_path) -> None:
    """用户显式指定的 SLIDES_READER_SOFFICE_PATH 应具有最高优先级。"""

    start = load_start_module()
    fake_soffice = tmp_path / "custom" / "soffice.exe"
    fake_soffice.parent.mkdir(parents=True)
    fake_soffice.write_text("", encoding="utf-8")
    paths = start.build_runtime_paths(tmp_path, tmp_path / "storage")
    monkeypatch.setattr(start.shutil, "which", lambda _command: None)

    assert start.resolve_soffice_path(paths, {"SLIDES_READER_SOFFICE_PATH": str(fake_soffice)}) == fake_soffice


def test_resolve_soffice_finds_portable_apps_direct_layout(monkeypatch, tmp_path) -> None:
    """便携版安装到 tools/libreoffice/App 时，启动器应优先使用这个 release 内路径。"""

    start = load_start_module()
    paths = start.build_runtime_paths(tmp_path, tmp_path / "storage")
    fake_soffice = (
        paths.libreoffice_root
        / "App"
        / "libreoffice"
        / "program"
        / "soffice.exe"
    )
    fake_soffice.parent.mkdir(parents=True)
    fake_soffice.write_text("", encoding="utf-8")
    monkeypatch.setattr(start, "is_windows", lambda: True)
    monkeypatch.setattr(start.shutil, "which", lambda _command: None)

    assert start.resolve_soffice_path(paths, {}) == fake_soffice.resolve()


def test_resolve_soffice_finds_legacy_concatenated_portable_layout(monkeypatch, tmp_path) -> None:
    """兼容旧安装参数可能生成的 tools/libreofficeLibreOfficePortable 目录。"""

    start = load_start_module()
    paths = start.build_runtime_paths(tmp_path, tmp_path / "storage")
    fake_soffice = (
        paths.tools_dir
        / "libreofficeLibreOfficePortable"
        / "App"
        / "libreoffice"
        / "program"
        / "soffice.exe"
    )
    fake_soffice.parent.mkdir(parents=True)
    fake_soffice.write_text("", encoding="utf-8")
    monkeypatch.setattr(start, "is_windows", lambda: True)
    monkeypatch.setattr(start.shutil, "which", lambda _command: None)

    assert start.resolve_soffice_path(paths, {}) == fake_soffice.resolve()


def test_install_libreoffice_portable_passes_destination_with_separator(monkeypatch, tmp_path) -> None:
    """安装器目标路径应带结尾分隔符，避免生成 libreofficeLibreOfficePortable 这类拼接目录。"""

    start = load_start_module()
    paths = start.build_runtime_paths(tmp_path, tmp_path / "storage")
    installer_path = paths.download_dir / "LibreOfficePortable.paf.exe"
    captured: dict[str, object] = {}

    def fake_run_logged(command, cwd, env, log_path, label, *, required=True):
        captured["command"] = command
        captured["cwd"] = cwd
        captured["env"] = env
        captured["log_path"] = log_path
        captured["label"] = label
        captured["required"] = required
        return 0

    monkeypatch.setattr(start, "run_logged", fake_run_logged)

    start.install_libreoffice_portable(
        installer_path,
        paths.libreoffice_root,
        paths.libreoffice_install_log,
    )

    destination = str(paths.libreoffice_root)
    if not destination.endswith(start.os.sep):
        destination += start.os.sep

    assert captured["command"] == [
        str(installer_path),
        "/S",
        f"/DESTINATION={destination}",
    ]


def test_ensure_libreoffice_uses_existing_soffice_without_download(monkeypatch, tmp_path) -> None:
    """已经能找到 LibreOffice 时，启动器不应重复下载便携版。"""

    start = load_start_module()
    fake_soffice = tmp_path / "system" / "soffice.exe"
    fake_soffice.parent.mkdir(parents=True)
    fake_soffice.write_text("", encoding="utf-8")
    paths = start.build_runtime_paths(tmp_path, tmp_path / "storage")
    env: dict[str, str] = {}

    monkeypatch.setattr(start, "resolve_soffice_path", lambda _paths, _env: fake_soffice)

    def fail_download(*_args, **_kwargs) -> None:
        raise AssertionError("不应下载 LibreOffice")

    monkeypatch.setattr(start, "download_file", fail_download)

    assert start.ensure_libreoffice(env, paths) == fake_soffice
    assert env["SLIDES_READER_SOFFICE_PATH"] == str(fake_soffice)


def test_ensure_libreoffice_downloads_when_release_mode_cannot_find_soffice(monkeypatch, tmp_path) -> None:
    """发行版模式找不到 LibreOffice 时，应下载并安装到 release/tools 目录。"""

    start = load_start_module()
    monkeypatch.setenv("SLIDES_READER_RELEASE_MODE", "1")
    monkeypatch.setattr(start, "is_windows", lambda: True)
    paths = start.build_runtime_paths(tmp_path, tmp_path / "storage")
    env: dict[str, str] = {"SLIDES_READER_RELEASE_MODE": "1"}
    calls: list[str] = []

    def fake_resolve(_paths, _env):
        if paths.portable_soffice.exists():
            return paths.portable_soffice
        return None

    def fake_download(_url, output_path, _log_path) -> None:
        calls.append("download")
        output_path.parent.mkdir(parents=True)
        output_path.write_text("installer", encoding="utf-8")

    def fake_install(_installer_path, _destination, _log_path) -> None:
        calls.append("install")
        paths.portable_soffice.parent.mkdir(parents=True)
        paths.portable_soffice.write_text("", encoding="utf-8")

    monkeypatch.setattr(start, "resolve_soffice_path", fake_resolve)
    monkeypatch.setattr(start, "download_file", fake_download)
    monkeypatch.setattr(start, "install_libreoffice_portable", fake_install)

    assert start.ensure_libreoffice(env, paths) == paths.portable_soffice
    assert calls == ["download", "install"]
    assert env["SLIDES_READER_SOFFICE_PATH"] == str(paths.portable_soffice)


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
