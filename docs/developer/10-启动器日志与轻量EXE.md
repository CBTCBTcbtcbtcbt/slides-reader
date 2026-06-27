# 启动器、日志与轻量 EXE

本文档说明当前 `start.py` 已经实现的一键启动、日志、诊断和 Windows 轻量 EXE 打包方式。

## 启动器定位

`start.py` 是项目的跨平台主入口。它把后端、前端构建和浏览器打开流程集中到一个命令中：

```powershell
python start.py
```

Linux 或 macOS 上使用：

```bash
python3 start.py
```

启动后只有一个主要访问地址：

```text
http://localhost:{port}/
```

FastAPI 同时提供 `/api/...` 接口和前端静态页面。这样普通用户不需要分别启动后端和 Vite 前端。

## 启动流程

`start.py` 会按顺序执行：

1. 解析命令行参数。
2. 合并环境变量和默认值。
3. 创建 `storage/` 和 `storage/logs/`。
4. 配置启动器日志。
5. 停止旧启动器留下的 pid 进程。
6. 检查并创建 `backend/.venv`。
7. 检查后端依赖是否可导入。
8. 缺失后端依赖时安装 `backend/requirements.txt`。
9. 检查前端 `node_modules`。
10. 缺失前端依赖时运行 `npm install`。
11. 运行 `npm run build` 生成 `frontend/dist`。
12. 从首选端口开始寻找可用端口。
13. 启动 `uvicorn main:app`。
14. 等待 `/api/health` 可访问。
15. 等待前端首页 `/` 可访问。
16. 根据配置调用 `webbrowser.open()` 打开浏览器。
17. 在终端打印 `Open`、`Health` 和日志路径。

`uvicorn` 是运行 FastAPI 的 Python Web 服务器。`webbrowser.open()` 是 Python 标准库函数，用来请求系统默认浏览器打开指定地址。

## 命令行参数

```powershell
python start.py --host 127.0.0.1 --port 8010
python start.py --no-open
python start.py --skip-frontend-build
python start.py --log-level DEBUG
python start.py --diagnostics
```

参数说明：

| 参数 | 作用 |
| --- | --- |
| `--host` | 指定后端监听地址。默认是 `0.0.0.0`。 |
| `--port` | 指定首选端口。端口被占用时会继续寻找后续空闲端口。 |
| `--no-open` | 服务就绪后不自动打开浏览器。 |
| `--skip-frontend-build` | 如果 `frontend/dist/index.html` 已存在，就跳过前端构建。 |
| `--log-level` | 设置启动器日志等级，可选 `DEBUG`、`INFO`、`WARNING`、`ERROR`。 |
| `--diagnostics` | 只输出环境诊断，不安装依赖，不启动服务。 |

配置优先级固定为：

```text
命令行参数 > 环境变量 > 默认值
```

## 环境变量

启动器读取这些环境变量：

| 环境变量 | 作用 |
| --- | --- |
| `SLIDES_READER_HOST` | 默认监听地址。 |
| `SLIDES_READER_PORT` | 默认首选端口。 |
| `SLIDES_READER_BACKEND_PORT` | 兼容旧启动方式的默认端口。 |
| `SLIDES_READER_SKIP_FRONTEND_BUILD` | 设置为 `1`、`true`、`yes` 或 `on` 时跳过已有前端构建。 |
| `SLIDES_READER_STORAGE_DIR` | 自定义运行数据目录。 |
| `SLIDES_READER_OPEN_BROWSER=0` | 禁止自动打开浏览器。 |
| `SLIDES_READER_LOG_LEVEL=DEBUG` | 设置启动器日志等级。 |

启动器启动后还会给后端进程写入：

```text
SLIDES_READER_STORAGE_DIR
SLIDES_READER_LOG_DIR
```

后端使用这两个变量决定数据库、上传文件、页面截图和日志目录。

## 日志文件

日志默认保存在：

```text
storage/logs/
```

文件含义：

| 文件 | 内容 |
| --- | --- |
| `launcher.log` | 启动器自身日志，包括参数、路径、端口选择和浏览器打开结果。 |
| `backend-install.log` | 后端虚拟环境创建、ensurepip 和 pip install 输出。 |
| `frontend-install.log` | 前端 `npm install` 输出。 |
| `frontend-build.log` | 前端 `npm run build` 输出。 |
| `slides-reader.log` | FastAPI、uvicorn 和后端业务日志。 |
| `diagnostics.txt` | `--diagnostics` 输出的环境快照。 |

日志使用 `RotatingFileHandler` 轮转。`RotatingFileHandler` 是 Python 标准库中的日志处理器。当前配置是单个日志文件最大 10MB，保留 5 份历史文件。

启动失败时，终端会打印简短错误，并自动输出相关日志最后 80 行。

## 后端日志配置

后端集中日志入口是：

```text
backend/logging_config.py
```

`backend/app.py` 创建 FastAPI 应用时会调用：

```python
configure_backend_logging()
```

这个函数会：

- 创建日志目录。
- 创建 `storage/logs/slides-reader.log`。
- 给 Python root logger 挂载轮转文件 handler。
- 让 `uvicorn`、`uvicorn.error` 和 `uvicorn.access` 日志传播到同一个日志文件。

如果用户直接运行：

```powershell
cd backend
uvicorn main:app
```

后端会把日志目录默认放到 `storage/logs/`。如果通过 `start.py` 启动，则使用启动器注入的 `SLIDES_READER_LOG_DIR`。

## 诊断命令

运行：

```powershell
python start.py --diagnostics
```

诊断内容包括：

- 项目根目录。
- `storage/` 和 `logs/` 路径。
- 当前 Python 路径。
- 后端虚拟环境 Python 是否存在。
- 后端 pip 是否可用。
- 后端核心依赖是否可导入。
- Node.js 是否存在。
- npm 是否存在。
- `frontend/dist/index.html` 是否存在。
- 首选端口是否可用。
- 是否自动打开浏览器。
- 是否跳过前端构建。
- LibreOffice `soffice` 是否可用。

诊断结果会同时打印到终端，并写入：

```text
storage/logs/diagnostics.txt
```

## Windows 便携式 Release EXE

当前采用便携式 release 文件夹方式打包。`SlidesReader.exe` 仍然只负责启动和检查环境，但它旁边会放好后端代码、前端构建结果和 Python runtime。

打包命令：

```powershell
.\scripts\build-release.ps1
```

脚本内部会调用 PyInstaller：

```powershell
pyinstaller --onefile --console --name SlidesReader start.py
```

`--onefile` 表示启动器本身输出为单个 exe。`--console` 表示保留终端窗口，用户能看到启动进度、后端实时日志和错误信息，也可以按 `Ctrl+C` 停止服务。

打包完成后，通常会生成：

```text
build/                # PyInstaller 中间文件
dist/SlidesReader.exe # 最终 exe
SlidesReader.spec     # PyInstaller 配置文件
release/SlidesReader/ # 给用户使用的便携式发行目录
```

这些内容可以重新生成，已经被 `.gitignore` 忽略。

## EXE 分发结构

启动器运行时会把 exe 所在目录当成项目根目录。因此分发时需要保持：

```text
SlidesReader/
  SlidesReader.exe
  backend/
  frontend/
    dist/
  runtime/
    python/
  tools/
    downloads/
    libreoffice/
  storage/
  README.md
```

不要只复制单独的 `SlidesReader.exe`。它需要在旁边找到 `backend/`、`frontend/dist/` 和 `runtime/python/`。

## Release 模式运行规则

当启动器由 PyInstaller 打包后的 `SlidesReader.exe` 运行，或设置了 `SLIDES_READER_RELEASE_MODE=1` 时，会进入 release 模式。

release 模式会使用这些路径：

```text
runtime/python/python.exe
storage/
storage/logs/
storage/tmp/
tools/downloads/
tools/libreoffice/
```

release 模式不会运行 `npm install` 或 `npm run build`。它只检查 `frontend/dist/index.html` 是否存在。缺失时说明发行包没有正确构建，需要重新运行：

```powershell
.\scripts\build-release.ps1
```

release 模式下，后端依赖安装到 `runtime/python/`，不会创建 `backend/.venv`。首次启动如果缺少依赖，会执行：

```powershell
runtime/python/python.exe -m pip install -r backend/requirements.txt
```

## LibreOffice 自动准备

启动器查找 LibreOffice 的顺序是：

1. `SLIDES_READER_SOFFICE_PATH`
2. `tools/libreoffice/LibreOfficePortable/App/libreoffice/program/soffice.exe`
3. `C:\Program Files\LibreOffice\program\soffice.exe`
4. `C:\Program Files (x86)\LibreOffice\program\soffice.exe`
5. PATH 中的 `soffice.exe`

如果都找不到，启动器会下载 LibreOffice Portable 到：

```text
tools/downloads/
```

然后静默安装到：

```text
tools/libreoffice/
```

安装日志写入：

```text
storage/logs/libreoffice-install.log
```

## Linux 源码运行

Linux 不需要 exe。保持源码运行：

```bash
python3 start.py
```

启动器里的路径、虚拟环境路径、日志路径和信号处理已经按 Windows 与非 Windows 系统分支处理。
