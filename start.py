#!/usr/bin/env python3
"""Start Slides Reader from one terminal and one browser URL.

The normal startup path builds the React frontend and serves it from FastAPI.
That keeps the app on a single port, which is more reliable for VS Code Remote,
local browsers, and copied project folders than running FastAPI and Vite on two
separate localhost URLs.
"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except AttributeError:
    pass

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
FRONTEND_DIST_INDEX = FRONTEND_DIR / "dist" / "index.html"
STORAGE_DIR = ROOT_DIR / "storage"
LOG_DIR = STORAGE_DIR / "logs"
BACKEND_LOG = LOG_DIR / "slides-reader.log"
BACKEND_INSTALL_LOG = LOG_DIR / "backend-install.log"
FRONTEND_INSTALL_LOG = LOG_DIR / "frontend-install.log"
BUILD_LOG = LOG_DIR / "frontend-build.log"
PID_FILES = (
    LOG_DIR / "slides-reader.pid",
    LOG_DIR / "slides-reader-backend.pid",
    LOG_DIR / "slides-reader-frontend.pid",
)


def is_windows() -> bool:
    return os.name == "nt"


def backend_python() -> Path:
    """Return the expected backend virtualenv Python path for this OS."""

    if is_windows():
        return BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
    return BACKEND_DIR / ".venv" / "bin" / "python"


def require_path(path: Path, message: str) -> None:
    if not path.exists():
        raise SystemExit(message)


def is_port_free(port: int, host: str = "0.0.0.0") -> bool:
    """Return whether a local TCP port can be bound."""

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

    print(f"Stopping previous {label} process {pid}...")
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


def stop_previous_instances() -> None:
    """Stop processes started by older launchers for this project."""

    for pid_file in PID_FILES:
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
            pass


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
    """Run a setup/build command and store complete output in a log file."""

    print(label)
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
                    return
        except Exception as error:  # noqa: BLE001 - startup polling should keep trying.
            last_error = str(error)
        time.sleep(1)
    raise RuntimeError(f"{label} did not become ready at {url}. Last error: {last_error}")


def backend_import_check(py: Path, env: dict[str, str]) -> bool:
    check_code = "import fastapi, fitz, uvicorn, multipart"
    result = subprocess.run(
        [str(py), "-c", check_code],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def ensure_backend_environment(env: dict[str, str]) -> Path:
    """Create/install the backend environment when possible."""

    py = backend_python()
    requirements = BACKEND_DIR / "requirements.txt"
    require_path(requirements, "backend/requirements.txt not found.")

    if not py.exists():
        run_logged(
            [sys.executable, "-m", "venv", str(BACKEND_DIR / ".venv")],
            ROOT_DIR,
            env,
            BACKEND_INSTALL_LOG,
            "Creating backend virtual environment...",
        )

    require_path(
        py,
        "Backend virtual environment was not created. Please install Python 3 with venv support.",
    )

    if backend_import_check(py, env):
        return py

    run_logged(
        [str(py), "-m", "ensurepip", "--upgrade"],
        BACKEND_DIR,
        env,
        BACKEND_INSTALL_LOG,
        "Bootstrapping backend pip...",
        required=False,
    )
    run_logged(
        [str(py), "-m", "pip", "install", "-r", str(requirements)],
        BACKEND_DIR,
        env,
        BACKEND_INSTALL_LOG,
        "Installing backend dependencies...",
    )

    if not backend_import_check(py, env):
        print_log_tail(BACKEND_INSTALL_LOG)
        raise RuntimeError("Backend dependencies are still unavailable after installation.")

    return py


def run_frontend_build(env: dict[str, str]) -> None:
    """Build the frontend, or use an existing build when Node.js is unavailable."""

    skip_build = os.environ.get("SLIDES_READER_SKIP_FRONTEND_BUILD") == "1"
    if skip_build and FRONTEND_DIST_INDEX.exists():
        print("Using existing frontend/dist build.")
        return

    npm_command = shutil.which("npm")
    if npm_command is None:
        if FRONTEND_DIST_INDEX.exists():
            print("npm was not found; using the existing frontend/dist build.")
            return
        raise SystemExit(
            "npm was not found and frontend/dist is missing. Install Node.js LTS first, then rerun:\n"
            "  python start.py"
        )

    if not (FRONTEND_DIR / "node_modules").exists():
        install_code = run_logged(
            [npm_command, "install"],
            FRONTEND_DIR,
            env,
            FRONTEND_INSTALL_LOG,
            "Installing frontend dependencies...",
            required=False,
        )
        if install_code != 0:
            if FRONTEND_DIST_INDEX.exists():
                print("Frontend dependency install failed; using the existing frontend/dist build.")
                print_log_tail(FRONTEND_INSTALL_LOG)
                return
            print_log_tail(FRONTEND_INSTALL_LOG)
            raise RuntimeError(f"Frontend dependency install failed with code {install_code}.")

    build_code = run_logged(
        [npm_command, "run", "build"],
        FRONTEND_DIR,
        env,
        BUILD_LOG,
        "Building frontend...",
        required=False,
    )
    if build_code != 0:
        if FRONTEND_DIST_INDEX.exists():
            print("Frontend build failed; using the existing frontend/dist build.")
            print_log_tail(BUILD_LOG)
            return
        print_log_tail(BUILD_LOG)
        raise RuntimeError(f"Frontend build failed with code {build_code}.")

    require_path(
        FRONTEND_DIST_INDEX,
        "Frontend build finished, but frontend/dist/index.html was not created.",
    )


def start_backend(
    py: Path,
    host: str,
    port: int,
    env: dict[str, str],
) -> tuple[subprocess.Popen[bytes], object]:
    log_file = BACKEND_LOG.open("wb")
    command = [
        str(py),
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]

    kwargs: dict[str, object] = {
        "cwd": str(BACKEND_DIR),
        "env": env,
        "stdout": log_file,
        "stderr": subprocess.STDOUT,
    }
    if is_windows():
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True

    try:
        process = subprocess.Popen(command, **kwargs)
        return process, log_file
    except Exception:
        log_file.close()
        raise


def stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return

    process.terminate()
    deadline = time.time() + 8
    while process.poll() is None and time.time() < deadline:
        time.sleep(0.2)

    if process.poll() is None:
        process.kill()


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.setdefault("SLIDES_READER_STORAGE_DIR", str(STORAGE_DIR))

    backend_host = os.environ.get("SLIDES_READER_HOST", "0.0.0.0")
    preferred_port = int(
        os.environ.get(
            "SLIDES_READER_PORT",
            os.environ.get("SLIDES_READER_BACKEND_PORT", "8000"),
        )
    )

    backend: subprocess.Popen[bytes] | None = None
    backend_log_file: object | None = None

    def cleanup() -> None:
        stop_process(backend)
        if backend_log_file is not None:
            try:
                backend_log_file.close()
            except Exception:
                pass
        for pid_file in PID_FILES:
            try:
                pid_file.unlink()
            except OSError:
                pass

    def handle_signal(signum, _frame) -> None:  # type: ignore[no-untyped-def]
        print("\nStopping Slides Reader...")
        cleanup()
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_signal)

    try:
        stop_previous_instances()
        py = ensure_backend_environment(env)
        run_frontend_build(env)

        backend_port = find_free_port(preferred_port)
        local_health_url = f"http://127.0.0.1:{backend_port}/api/health"
        local_page_url = f"http://127.0.0.1:{backend_port}/"
        open_url = f"http://localhost:{backend_port}/"

        print(f"Starting Slides Reader on {open_url}")
        backend, backend_log_file = start_backend(py, backend_host, backend_port, env)
        (LOG_DIR / "slides-reader.pid").write_text(str(backend.pid), encoding="utf-8")

        wait_for_http(local_health_url, "Backend", backend)
        wait_for_http(local_page_url, "Frontend page", backend)

        print("\nSlides Reader is ready.")
        print(f"Open: {open_url}")
        print(f"Health: {local_health_url}")
        print(f"Log: {BACKEND_LOG}")
        print("Press Ctrl+C in this terminal to stop the service.")

        while True:
            if backend.poll() is not None:
                print_log_tail(BACKEND_LOG)
                raise RuntimeError(f"Slides Reader stopped with code {backend.returncode}.")
            time.sleep(1)
    except Exception as error:  # noqa: BLE001 - show friendly startup diagnostics.
        print(f"\nStartup failed: {error}", file=sys.stderr)
        print_log_tail(BACKEND_INSTALL_LOG)
        print_log_tail(FRONTEND_INSTALL_LOG)
        print_log_tail(BUILD_LOG)
        print_log_tail(BACKEND_LOG)
        cleanup()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
