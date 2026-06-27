#!/usr/bin/env python3
"""从一个终端和一个浏览器地址启动 Slides Reader。

默认启动流程会构建 React 前端，并由 FastAPI 同时提供 API 和网页。
这样应用只占用一个端口，比同时运行 FastAPI 和 Vite 两个 localhost 地址更适合复制项目目录、
VS Code Remote 和未来轻量 exe 启动器。
"""

from __future__ import annotations

import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except AttributeError:
    pass

LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
DEFAULT_LOG_LEVEL = "INFO"
LIBREOFFICE_PORTABLE_URL = (
    "https://download.documentfoundation.org/libreoffice/portable/26.2.1/"
    "LibreOfficePortable_26.2.1_MultilingualStandard.paf.exe"
)
LIBREOFFICE_PORTABLE_INSTALLER_NAME = "LibreOfficePortable_26.2.1_MultilingualStandard.paf.exe"


def is_frozen() -> bool:
    """判断当前是否由 PyInstaller 等工具打包成可执行文件运行。"""

    return bool(getattr(sys, "frozen", False))


def resolve_root_dir() -> Path:
    """返回项目根目录。

    源码运行时，项目根目录就是 start.py 所在目录。
    打包成轻量 exe 后，项目根目录是 exe 所在目录，旁边应放置 backend、frontend 和 storage。
    """

    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT_DIR = resolve_root_dir()


@dataclass(frozen=True)
class RuntimePaths:
    """集中保存启动器需要使用的项目路径。"""

    root_dir: Path
    backend_dir: Path
    frontend_dir: Path
    frontend_dist_index: Path
    runtime_python_dir: Path
    runtime_python: Path
    storage_dir: Path
    log_dir: Path
    tmp_dir: Path
    tools_dir: Path
    download_dir: Path
    libreoffice_root: Path
    portable_soffice: Path
    launcher_log: Path
    backend_log: Path
    backend_install_log: Path
    frontend_install_log: Path
    build_log: Path
    libreoffice_install_log: Path
    diagnostics_log: Path
    pid_files: tuple[Path, ...]


@dataclass(frozen=True)
class LauncherOptions:
    """启动器最终采用的配置。

    配置来源优先级固定为：命令行参数 > 环境变量 > 默认值。
    """

    host: str
    port: int
    open_browser: bool
    skip_frontend_build: bool
    log_level: str
    diagnostics: bool
    storage_dir: Path


def parse_bool_env(value: str | None, *, default: bool = False) -> bool:
    """把环境变量中的布尔值字符串转换成 bool。"""

    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def is_release_mode(env: dict[str, str] | None = None) -> bool:
    """判断当前是否按便携式发行版规则运行。

    PyInstaller 打包后的 exe 一定属于发行版模式；测试或调试时也可以通过
    SLIDES_READER_RELEASE_MODE=1 显式启用相同路径规则。
    """

    env_value = os.environ.get("SLIDES_READER_RELEASE_MODE") if env is None else env.get(
        "SLIDES_READER_RELEASE_MODE",
        os.environ.get("SLIDES_READER_RELEASE_MODE"),
    )
    return is_frozen() or parse_bool_env(env_value)


def build_arg_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器。"""

    parser = argparse.ArgumentParser(description="启动 Slides Reader。")
    parser.add_argument("--host", help="后端监听地址，默认读取 SLIDES_READER_HOST 或 0.0.0.0。")
    parser.add_argument("--port", type=int, help="优先使用的端口，默认读取环境变量或 8000。")
    parser.add_argument("--no-open", action="store_true", help="服务就绪后不自动打开浏览器。")
    parser.add_argument(
        "--skip-frontend-build",
        action="store_true",
        help="如果 frontend/dist 已存在，则跳过前端构建。",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="启动器日志等级，默认读取 SLIDES_READER_LOG_LEVEL 或 INFO。",
    )
    parser.add_argument("--diagnostics", action="store_true", help="只输出环境诊断，不启动服务。")
    return parser


def resolve_default_port(env: dict[str, str]) -> int:
    """按兼容顺序读取默认端口。"""

    return int(env.get("SLIDES_READER_PORT", env.get("SLIDES_READER_BACKEND_PORT", DEFAULT_PORT)))


def build_launcher_options(
    argv: Sequence[str] | None = None,
    env: dict[str, str] | None = None,
) -> LauncherOptions:
    """合并命令行参数、环境变量和默认值，得到最终启动配置。"""

    env = os.environ.copy() if env is None else env
    args = build_arg_parser().parse_args(argv)

    host = args.host or env.get("SLIDES_READER_HOST", DEFAULT_HOST)
    port = args.port if args.port is not None else resolve_default_port(env)
    open_browser = not args.no_open and env.get("SLIDES_READER_OPEN_BROWSER", "1") != "0"
    skip_frontend_build = args.skip_frontend_build or parse_bool_env(
        env.get("SLIDES_READER_SKIP_FRONTEND_BUILD"),
    )
    log_level = (args.log_level or env.get("SLIDES_READER_LOG_LEVEL", DEFAULT_LOG_LEVEL)).upper()
    if is_release_mode(env):
        storage_dir = (ROOT_DIR / "storage").resolve()
        skip_frontend_build = True
    else:
        storage_dir = Path(env.get("SLIDES_READER_STORAGE_DIR", str(ROOT_DIR / "storage"))).resolve()

    return LauncherOptions(
        host=host,
        port=port,
        open_browser=open_browser,
        skip_frontend_build=skip_frontend_build,
        log_level=log_level,
        diagnostics=args.diagnostics,
        storage_dir=storage_dir,
    )


def build_runtime_paths(root_dir: Path, storage_dir: Path) -> RuntimePaths:
    """根据项目根目录和运行数据目录推导所有运行路径。"""

    backend_dir = root_dir / "backend"
    frontend_dir = root_dir / "frontend"
    runtime_python_dir = root_dir / "runtime" / "python"
    runtime_python = (
        runtime_python_dir / "python.exe"
        if os.name == "nt"
        else runtime_python_dir / "bin" / "python"
    )
    log_dir = storage_dir / "logs"
    tools_dir = root_dir / "tools"
    libreoffice_root = tools_dir / "libreoffice"

    return RuntimePaths(
        root_dir=root_dir,
        backend_dir=backend_dir,
        frontend_dir=frontend_dir,
        frontend_dist_index=frontend_dir / "dist" / "index.html",
        runtime_python_dir=runtime_python_dir,
        runtime_python=runtime_python,
        storage_dir=storage_dir,
        log_dir=log_dir,
        tmp_dir=storage_dir / "tmp",
        tools_dir=tools_dir,
        download_dir=tools_dir / "downloads",
        libreoffice_root=libreoffice_root,
        portable_soffice=libreoffice_root
        / "LibreOfficePortable"
        / "App"
        / "libreoffice"
        / "program"
        / "soffice.exe",
        launcher_log=log_dir / "launcher.log",
        backend_log=log_dir / "slides-reader.log",
        backend_install_log=log_dir / "backend-install.log",
        frontend_install_log=log_dir / "frontend-install.log",
        build_log=log_dir / "frontend-build.log",
        libreoffice_install_log=log_dir / "libreoffice-install.log",
        diagnostics_log=log_dir / "diagnostics.txt",
        pid_files=(
            log_dir / "slides-reader.pid",
            log_dir / "slides-reader-backend.pid",
            log_dir / "slides-reader-frontend.pid",
        ),
    )


PATHS = build_runtime_paths(ROOT_DIR, ROOT_DIR / "storage")
logger = logging.getLogger("slides_reader.launcher")


def setup_launcher_logging(paths: RuntimePaths, log_level: str) -> None:
    """配置启动器日志，写入 launcher.log 并同步输出到终端。"""

    paths.log_dir.mkdir(parents=True, exist_ok=True)
    logger.handlers.clear()
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        paths.launcher_log,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(getattr(logging, log_level, logging.INFO))
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)


def is_windows() -> bool:
    return os.name == "nt"


def resolve_existing_file(candidate: str | Path | None) -> Path | None:
    """把候选文件路径解析成真实存在的绝对路径，不存在时返回 None。"""

    if not candidate:
        return None

    candidate_path = Path(candidate)
    if candidate_path.exists() and candidate_path.is_file():
        return candidate_path.resolve()

    return None


def libreoffice_portable_roots(paths: RuntimePaths = PATHS) -> tuple[Path, ...]:
    """返回 release 内可能保存 LibreOffice Portable 的目录。"""

    return (
        paths.libreoffice_root,
        paths.libreoffice_root / "LibreOfficePortable",
        paths.tools_dir / "libreofficeLibreOfficePortable",
    )


def libreoffice_portable_candidates(paths: RuntimePaths = PATHS) -> tuple[Path, ...]:
    """返回 release 内常见 LibreOffice Portable 的 soffice.exe 候选路径。"""

    return (
        paths.portable_soffice,
        paths.libreoffice_root / "App" / "libreoffice" / "program" / "soffice.exe",
        paths.tools_dir
        / "libreofficeLibreOfficePortable"
        / "App"
        / "libreoffice"
        / "program"
        / "soffice.exe",
    )


def resolve_local_soffice_path(paths: RuntimePaths = PATHS) -> Path | None:
    """优先从 release 文件夹内部查找 LibreOffice Portable 的 soffice.exe。"""

    # 先检查已知固定结构，避免递归扫描时被其他同名文件影响优先级。
    for candidate in libreoffice_portable_candidates(paths):
        resolved_path = resolve_existing_file(candidate)
        if resolved_path is not None:
            return resolved_path

    # PortableApps 安装器的目录结构未来可能变化，所以最后在本地工具目录内做兜底扫描。
    for portable_root in libreoffice_portable_roots(paths):
        if not portable_root.exists():
            continue

        matches = sorted(
            (path for path in portable_root.rglob("soffice.exe") if path.is_file()),
            key=lambda path: (len(path.parts), str(path).lower()),
        )
        if matches:
            return matches[0].resolve()

    return None


def format_portableapps_destination(destination: Path) -> str:
    """生成 PortableApps 安装器需要的目标目录参数。"""

    destination_text = str(destination)
    separators = [os.sep]
    if os.altsep:
        separators.append(os.altsep)

    # PortableApps 安装器会把 AppName 拼到目标目录后面；没有结尾分隔符时可能变成
    # libreofficeLibreOfficePortable，所以这里显式保留结尾目录分隔符。
    if not any(destination_text.endswith(separator) for separator in separators):
        destination_text += os.sep

    return destination_text


def backend_python(paths: RuntimePaths = PATHS) -> Path:
    """返回当前操作系统下预期的后端虚拟环境 Python 路径。"""

    if is_release_mode():
        return paths.runtime_python
    if is_windows():
        return paths.backend_dir / ".venv" / "Scripts" / "python.exe"
    return paths.backend_dir / ".venv" / "bin" / "python"


def require_path(path: Path, message: str) -> None:
    if not path.exists():
        raise SystemExit(message)


def is_port_free(port: int, host: str = "0.0.0.0") -> bool:
    """判断本地 TCP 端口是否可以绑定。"""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_free_port(start_port: int) -> int:
    for port in range(start_port, start_port + 200):
        if is_port_free(port):
            logger.debug("Selected free port: %s", port)
            return port
    raise RuntimeError(f"No free port found from {start_port} to {start_port + 199}.")


def process_exists(pid: int) -> bool:
    if pid <= 0:
        return False

    if is_windows():
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            check=False,
        )
        return str(pid) in result.stdout

    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def stop_pid(pid: int, label: str) -> None:
    if not process_exists(pid):
        return

    logger.info("Stopping previous %s process %s...", label, pid)
    if is_windows():
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return

    deadline = time.time() + 8
    while process_exists(pid) and time.time() < deadline:
        time.sleep(0.2)

    if process_exists(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def stop_previous_instances(paths: RuntimePaths = PATHS) -> None:
    """停止旧启动器留下的进程。"""

    for pid_file in paths.pid_files:
        if not pid_file.exists():
            continue
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = 0
        stop_pid(pid, pid_file.stem)
        try:
            pid_file.unlink()
        except OSError:
            logger.debug("Could not remove pid file: %s", pid_file, exc_info=True)


def print_log_tail(path: Path, lines: int = 80) -> None:
    if not path.exists():
        return
    content = path.read_text(errors="replace").splitlines()[-lines:]
    if content:
        print(f"\nLast lines from {path}:", file=sys.stderr)
        print("\n".join(content), file=sys.stderr)


def run_logged(
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
    label: str,
    *,
    required: bool = True,
) -> int:
    """运行安装或构建命令，并把完整输出写入日志。"""

    logger.info(label)
    logger.debug("Running command in %s: %s", cwd, command)
    # 日志目录可能在测试或首次启动时尚未创建，写入前先确保父目录存在。
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log_file:
        log_file.write(("\n\n$ " + " ".join(command) + "\n").encode("utf-8", errors="replace"))
        result = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            check=False,
        )
    logger.debug("Command exited with code %s: %s", result.returncode, command)
    if result.returncode != 0 and required:
        print_log_tail(log_path)
        raise RuntimeError(f"{label} failed with code {result.returncode}.")
    return result.returncode


def wait_for_http(url: str, label: str, process: subprocess.Popen[bytes]) -> None:
    last_error = ""
    for _ in range(90):
        if process.poll() is not None:
            raise RuntimeError(f"{label} exited early with code {process.returncode}.")
        try:
            with urllib.request.urlopen(url, timeout=1.5) as response:
                if response.status < 500:
                    logger.debug("%s became ready at %s with status %s", label, url, response.status)
                    return
        except Exception as error:  # noqa: BLE001 - 启动轮询需要持续重试。
            last_error = str(error)
        time.sleep(1)
    raise RuntimeError(f"{label} did not become ready at {url}. Last error: {last_error}")


def backend_import_check(py: Path, env: dict[str, str], paths: RuntimePaths = PATHS) -> bool:
    check_code = "import fastapi, fitz, uvicorn, multipart"
    result = subprocess.run(
        [str(py), "-c", check_code],
        cwd=str(paths.backend_dir),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def ensure_backend_environment(env: dict[str, str], paths: RuntimePaths = PATHS) -> Path:
    """在可能时创建并安装后端虚拟环境。"""

    py = backend_python(paths)
    requirements = paths.backend_dir / "requirements.txt"
    require_path(requirements, "backend/requirements.txt not found.")

    if is_release_mode(env):
        require_path(
            py,
            "Release runtime Python was not found. Please rebuild the release package with "
            "scripts/build-release.ps1.",
        )
    elif not py.exists():
        run_logged(
            [sys.executable, "-m", "venv", str(paths.backend_dir / ".venv")],
            paths.root_dir,
            env,
            paths.backend_install_log,
            "Creating backend virtual environment...",
        )

    require_path(
        py,
        "Backend virtual environment was not created. Please install Python 3 with venv support.",
    )

    if backend_import_check(py, env, paths):
        logger.debug("Backend dependencies are already importable.")
        return py

    run_logged(
        [str(py), "-m", "ensurepip", "--upgrade"],
        paths.backend_dir,
        env,
        paths.backend_install_log,
        "Bootstrapping backend pip...",
        required=False,
    )
    run_logged(
        [str(py), "-m", "pip", "install", "-r", str(requirements)],
        paths.backend_dir,
        env,
        paths.backend_install_log,
        "Installing backend dependencies...",
    )

    if not backend_import_check(py, env, paths):
        print_log_tail(paths.backend_install_log)
        raise RuntimeError("Backend dependencies are still unavailable after installation.")

    return py


def run_frontend_build(
    env: dict[str, str],
    paths: RuntimePaths = PATHS,
    *,
    skip_build: bool = False,
) -> None:
    """构建前端；Node.js 不可用时尽量复用已有 frontend/dist。"""

    if is_release_mode(env):
        if paths.frontend_dist_index.exists():
            logger.info("Using packaged frontend/dist build.")
            return
        raise RuntimeError(
            "frontend/dist/index.html not found at "
            f"{paths.frontend_dist_index}. Please rebuild the release package with scripts/build-release.ps1.",
        )

    if skip_build and paths.frontend_dist_index.exists():
        logger.info("Using existing frontend/dist build.")
        return

    npm_command = shutil.which("npm")
    if npm_command is None:
        if paths.frontend_dist_index.exists():
            logger.warning("npm was not found; using the existing frontend/dist build.")
            return
        raise SystemExit(
            "npm was not found and frontend/dist is missing. Install Node.js LTS first, then rerun:\n"
            "  python start.py"
        )

    if not (paths.frontend_dir / "node_modules").exists():
        install_code = run_logged(
            [npm_command, "install"],
            paths.frontend_dir,
            env,
            paths.frontend_install_log,
            "Installing frontend dependencies...",
            required=False,
        )
        if install_code != 0:
            if paths.frontend_dist_index.exists():
                logger.warning("Frontend dependency install failed; using existing frontend/dist.")
                print_log_tail(paths.frontend_install_log)
                return
            print_log_tail(paths.frontend_install_log)
            raise RuntimeError(f"Frontend dependency install failed with code {install_code}.")

    build_code = run_logged(
        [npm_command, "run", "build"],
        paths.frontend_dir,
        env,
        paths.build_log,
        "Building frontend...",
        required=False,
    )
    if build_code != 0:
        if paths.frontend_dist_index.exists():
            logger.warning("Frontend build failed; using existing frontend/dist.")
            print_log_tail(paths.build_log)
            return
        print_log_tail(paths.build_log)
        raise RuntimeError(f"Frontend build failed with code {build_code}.")

    require_path(
        paths.frontend_dist_index,
        "Frontend build finished, but frontend/dist/index.html was not created.",
    )


def build_backend_command(py: Path, host: str, port: int) -> list[str]:
    """构造 uvicorn 启动命令。

    uvicorn 的 --log-config 只支持 ini/json/yaml 文件；后端 Python 日志由 app 启动时自行配置。
    """

    return [
        str(py),
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]


def start_backend(
    py: Path,
    host: str,
    port: int,
    env: dict[str, str],
    paths: RuntimePaths = PATHS,
) -> tuple[subprocess.Popen[bytes], object]:
    log_file = paths.backend_log.open("wb")
    command = build_backend_command(py, host, port)

    kwargs: dict[str, object] = {
        "cwd": str(paths.backend_dir),
        "env": env,
        "stdout": log_file,
        "stderr": subprocess.STDOUT,
    }
    if is_windows():
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True

    try:
        logger.debug("Starting backend command: %s", command)
        process = subprocess.Popen(command, **kwargs)
        return process, log_file
    except Exception:
        log_file.close()
        raise


def maybe_open_browser(url: str, *, should_open: bool) -> bool:
    """按配置决定是否打开浏览器。"""

    if not should_open:
        logger.info("Browser auto-open is disabled.")
        return False
    try:
        opened = webbrowser.open(url)
        logger.info("Browser open requested for %s: %s", url, opened)
        return bool(opened)
    except Exception:
        logger.exception("Failed to open browser for %s", url)
        return False


def stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return

    process.terminate()
    deadline = time.time() + 8
    while process.poll() is None and time.time() < deadline:
        time.sleep(0.2)

    if process.poll() is None:
        process.kill()


def resolve_soffice_path(paths: RuntimePaths = PATHS, env: dict[str, str] | None = None) -> Path | None:
    """按固定优先级查找 LibreOffice 的 soffice 可执行文件。"""

    env = os.environ if env is None else env
    env_soffice = resolve_existing_file(env.get("SLIDES_READER_SOFFICE_PATH"))
    if env_soffice is not None:
        return env_soffice

    local_soffice = resolve_local_soffice_path(paths)
    if local_soffice is not None:
        return local_soffice

    candidates: list[str | None] = []
    if is_windows():
        candidates.extend(
            [
                r"C:\Program Files\LibreOffice\program\soffice.exe",
                r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
            ],
        )
        path_command = shutil.which("soffice.exe")
    else:
        path_command = shutil.which("soffice")

    candidates.append(path_command)
    for candidate in candidates:
        resolved_path = resolve_existing_file(candidate)
        if resolved_path is not None:
            return resolved_path
    return None


def find_soffice() -> str | None:
    """查找 LibreOffice 的 soffice 命令，用于诊断 PPT/PPTX 转换能力。"""

    soffice = resolve_soffice_path(PATHS, os.environ)
    return str(soffice) if soffice is not None else None


def download_file(url: str, output_path: Path, log_path: Path) -> None:
    """下载文件到指定路径，并把下载过程写入日志。"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        logger.info("Using cached download: %s", output_path)
        return

    logger.info("Downloading LibreOffice Portable...")
    with log_path.open("ab") as log_file:
        log_file.write((f"\n\nDownloading {url}\nTo {output_path}\n").encode("utf-8"))
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                with output_path.open("wb") as output_file:
                    shutil.copyfileobj(response, output_file)
        except Exception:
            log_file.write(b"Download failed.\n")
            raise
        log_file.write(b"Download finished.\n")


def install_libreoffice_portable(installer_path: Path, destination: Path, log_path: Path) -> None:
    """静默安装 PortableApps 版 LibreOffice 到 release/tools 目录。"""

    destination.mkdir(parents=True, exist_ok=True)
    command = [str(installer_path), "/S", f"/DESTINATION={format_portableapps_destination(destination)}"]
    run_logged(
        command,
        destination,
        os.environ.copy(),
        log_path,
        "Installing LibreOffice Portable...",
    )


def ensure_libreoffice(env: dict[str, str], paths: RuntimePaths = PATHS) -> Path | None:
    """确保 PPT/PPTX 转换所需的 LibreOffice 可用。"""

    soffice = resolve_soffice_path(paths, env)
    if soffice is not None:
        env["SLIDES_READER_SOFFICE_PATH"] = str(soffice)
        logger.info("LibreOffice found: %s", soffice)
        return soffice

    if not is_windows():
        logger.warning("LibreOffice was not found. PPT/PPTX conversion will be unavailable.")
        return None

    installer_path = paths.download_dir / LIBREOFFICE_PORTABLE_INSTALLER_NAME
    download_file(LIBREOFFICE_PORTABLE_URL, installer_path, paths.libreoffice_install_log)
    install_libreoffice_portable(installer_path, paths.libreoffice_root, paths.libreoffice_install_log)

    soffice = resolve_soffice_path(paths, env)
    if soffice is None:
        fallback_matches = list(paths.libreoffice_root.rglob("soffice.exe"))
        if fallback_matches:
            soffice = fallback_matches[0].resolve()

    if soffice is None:
        print_log_tail(paths.libreoffice_install_log)
        raise RuntimeError(
            f"LibreOffice Portable was installed, but soffice.exe was not found under {paths.libreoffice_root}."
        )

    env["SLIDES_READER_SOFFICE_PATH"] = str(soffice)
    logger.info("LibreOffice Portable ready: %s", soffice)
    return soffice


def tail_log_file(path: Path, stop_event: threading.Event) -> None:
    """持续把日志文件新增内容打印到终端。"""

    while not path.exists() and not stop_event.is_set():
        time.sleep(0.2)
    if stop_event.is_set():
        return

    with path.open("r", encoding="utf-8", errors="replace") as log_file:
        log_file.seek(0, os.SEEK_END)
        while not stop_event.is_set():
            line = log_file.readline()
            if line:
                print(line, end="")
                continue
            time.sleep(0.2)


def start_backend_log_tail(path: Path) -> tuple[threading.Event, threading.Thread]:
    """启动后端日志实时输出线程，并返回停止信号和线程对象。"""

    stop_event = threading.Event()
    thread = threading.Thread(
        target=tail_log_file,
        args=(path, stop_event),
        daemon=True,
        name="slides-reader-backend-log-tail",
    )
    thread.start()
    return stop_event, thread


def collect_diagnostics(
    options: LauncherOptions,
    paths: RuntimePaths,
    env: dict[str, str],
) -> str:
    """收集运行环境快照，供 --diagnostics 输出和写入 diagnostics.txt。"""

    py = backend_python(paths)
    npm_command = shutil.which("npm")
    node_command = shutil.which("node")
    pip_available = False

    if py.exists():
        pip_result = subprocess.run(
            [str(py), "-m", "pip", "--version"],
            cwd=str(paths.backend_dir),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        pip_available = pip_result.returncode == 0

    lines = [
        "Slides Reader diagnostics",
        f"Root dir: {paths.root_dir}",
        f"Storage dir: {paths.storage_dir}",
        f"Log dir: {paths.log_dir}",
        f"Temp dir: {paths.tmp_dir}",
        f"Python executable: {sys.executable}",
        f"Backend venv Python: {py} ({'exists' if py.exists() else 'missing'})",
        f"Release mode: {is_release_mode(env)}",
        f"Runtime Python dir: {paths.runtime_python_dir}",
        f"Backend pip available: {pip_available}",
        f"Backend imports available: {backend_import_check(py, env, paths) if py.exists() else False}",
        f"Node.js command: {node_command or 'missing'}",
        f"npm command: {npm_command or 'missing'}",
        f"frontend/dist index: {paths.frontend_dist_index} ({'exists' if paths.frontend_dist_index.exists() else 'missing'})",
        f"Preferred host: {options.host}",
        f"Preferred port: {options.port}",
        f"Preferred port free: {is_port_free(options.port)}",
        f"Auto open browser: {options.open_browser}",
        f"Skip frontend build: {options.skip_frontend_build}",
        f"Log level: {options.log_level}",
        f"LibreOffice soffice: {resolve_soffice_path(paths, env) or 'missing'}",
    ]
    return "\n".join(lines) + "\n"


def write_diagnostics(
    options: LauncherOptions,
    paths: RuntimePaths,
    env: dict[str, str],
) -> str:
    """把诊断信息写入文件并返回内容。"""

    paths.log_dir.mkdir(parents=True, exist_ok=True)
    diagnostics = collect_diagnostics(options, paths, env)
    paths.diagnostics_log.write_text(diagnostics, encoding="utf-8")
    return diagnostics


def main(argv: Sequence[str] | None = None) -> int:
    options = build_launcher_options(argv)
    paths = build_runtime_paths(ROOT_DIR, options.storage_dir)
    paths.log_dir.mkdir(parents=True, exist_ok=True)
    paths.storage_dir.mkdir(parents=True, exist_ok=True)
    paths.tmp_dir.mkdir(parents=True, exist_ok=True)
    paths.download_dir.mkdir(parents=True, exist_ok=True)
    paths.libreoffice_root.mkdir(parents=True, exist_ok=True)
    setup_launcher_logging(paths, options.log_level)

    env = os.environ.copy()
    env["SLIDES_READER_STORAGE_DIR"] = str(paths.storage_dir)
    env["SLIDES_READER_LOG_DIR"] = str(paths.log_dir)
    env["TEMP"] = str(paths.tmp_dir)
    env["TMP"] = str(paths.tmp_dir)

    logger.info("Slides Reader launcher starting.")
    logger.debug("Options: %s", options)
    logger.debug("Runtime paths: %s", paths)

    if options.diagnostics:
        diagnostics = write_diagnostics(options, paths, env)
        print(diagnostics, end="")
        print(f"Diagnostics written to: {paths.diagnostics_log}")
        return 0

    backend: subprocess.Popen[bytes] | None = None
    backend_log_file: object | None = None
    log_tail_stop: threading.Event | None = None
    log_tail_thread: threading.Thread | None = None

    def cleanup() -> None:
        if log_tail_stop is not None:
            log_tail_stop.set()
        stop_process(backend)
        if backend_log_file is not None:
            try:
                backend_log_file.close()
            except Exception:
                logger.debug("Could not close backend log file.", exc_info=True)
        if log_tail_thread is not None:
            log_tail_thread.join(timeout=2)
        for pid_file in paths.pid_files:
            try:
                pid_file.unlink()
            except OSError:
                pass

    def handle_signal(signum, _frame) -> None:  # type: ignore[no-untyped-def]
        print("\nStopping Slides Reader...")
        logger.info("Received signal %s, stopping service.", signum)
        cleanup()
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_signal)

    try:
        stop_previous_instances(paths)
        py = ensure_backend_environment(env, paths)
        run_frontend_build(env, paths, skip_build=options.skip_frontend_build)
        ensure_libreoffice(env, paths)

        backend_port = find_free_port(options.port)
        local_health_url = f"http://127.0.0.1:{backend_port}/api/health"
        local_page_url = f"http://127.0.0.1:{backend_port}/"
        open_url = f"http://localhost:{backend_port}/"

        logger.info("Starting Slides Reader on %s", open_url)
        backend, backend_log_file = start_backend(py, options.host, backend_port, env, paths)
        log_tail_stop, log_tail_thread = start_backend_log_tail(paths.backend_log)
        (paths.log_dir / "slides-reader.pid").write_text(str(backend.pid), encoding="utf-8")

        wait_for_http(local_health_url, "Backend", backend)
        wait_for_http(local_page_url, "Frontend page", backend)
        maybe_open_browser(open_url, should_open=options.open_browser)

        print("\nSlides Reader is ready.")
        print(f"Open: {open_url}")
        print(f"Health: {local_health_url}")
        print(f"Launcher log: {paths.launcher_log}")
        print(f"Backend log: {paths.backend_log}")
        print("Press Ctrl+C in this terminal to stop the service.")

        while True:
            if backend.poll() is not None:
                print_log_tail(paths.backend_log)
                raise RuntimeError(f"Slides Reader stopped with code {backend.returncode}.")
            time.sleep(1)
    except Exception as error:  # noqa: BLE001 - 启动器应提供友好的失败诊断。
        logger.exception("Startup failed.")
        print(f"\nStartup failed: {error}", file=sys.stderr)
        print_log_tail(paths.launcher_log)
        print_log_tail(paths.backend_install_log)
        print_log_tail(paths.frontend_install_log)
        print_log_tail(paths.build_log)
        print_log_tail(paths.libreoffice_install_log)
        print_log_tail(paths.backend_log)
        cleanup()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
