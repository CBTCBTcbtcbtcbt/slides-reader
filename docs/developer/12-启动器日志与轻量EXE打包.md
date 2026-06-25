# 启动器日志与轻量 EXE 打包

本文档说明 `start.py` 的一键启动、日志、诊断和未来 Windows 轻量 exe 打包路线。

## 启动方式

推荐在项目根目录运行：

```powershell
python start.py
```

Linux 或 macOS 上运行：

```bash
python3 start.py
```

`start.py` 会自动完成以下流程：

1. 检查并创建 `backend/.venv`。
2. 检查后端依赖，缺失时自动安装 `backend/requirements.txt`。
3. 检查前端依赖，缺失时自动运行 `npm install`。
4. 运行 `npm run build`，生成 `frontend/dist`。
5. 启动 `uvicorn main:app`。
6. 等待 `/api/health` 和前端首页都可访问。
7. 默认自动打开浏览器。

`uvicorn` 是运行 FastAPI 的 Python Web 服务器。当前启动方式仍然只占用一个端口：FastAPI 同时提供 API 和前端静态页面。

## 命令行参数

```powershell
python start.py --host 127.0.0.1 --port 8010
python start.py --no-open
python start.py --skip-frontend-build
python start.py --log-level DEBUG
python start.py --diagnostics
```

参数含义：

- `--host`：后端监听地址。
- `--port`：优先使用的端口。如果端口被占用，启动器会继续寻找后续可用端口。
- `--no-open`：服务就绪后不自动打开浏览器。
- `--skip-frontend-build`：已有 `frontend/dist/index.html` 时跳过前端构建。
- `--log-level`：启动器日志等级，可选 `DEBUG`、`INFO`、`WARNING`、`ERROR`。
- `--diagnostics`：只检查环境并输出诊断，不启动服务。

配置优先级固定为：命令行参数 > 环境变量 > 默认值。

## 环境变量

- `SLIDES_READER_HOST`
- `SLIDES_READER_PORT`
- `SLIDES_READER_BACKEND_PORT`
- `SLIDES_READER_SKIP_FRONTEND_BUILD`
- `SLIDES_READER_STORAGE_DIR`
- `SLIDES_READER_OPEN_BROWSER=0`
- `SLIDES_READER_LOG_LEVEL=DEBUG`

`SLIDES_READER_STORAGE_DIR` 会同时影响数据库、上传文件、页面截图和日志目录。

## 日志文件

日志默认保存在：

```text
storage/logs/
```

主要文件：

- `launcher.log`：启动器自身日志，包括参数、路径、端口、浏览器打开结果。
- `backend-install.log`：后端虚拟环境和 pip 安装日志。
- `frontend-install.log`：前端 `npm install` 日志。
- `frontend-build.log`：前端 `npm run build` 日志。
- `slides-reader.log`：FastAPI、uvicorn 和后端业务日志。
- `diagnostics.txt`：`--diagnostics` 输出的环境快照。

日志使用 `RotatingFileHandler` 轮转。`RotatingFileHandler` 是 Python 标准库提供的日志处理器，文件超过 10MB 后会切分，默认保留 5 份历史文件。

## 诊断命令

运行：

```powershell
python start.py --diagnostics
```

它会检查：

- 项目根目录和 storage 目录。
- 当前 Python 和后端虚拟环境 Python。
- 后端 pip 是否可用。
- 后端核心依赖是否可 import。
- Node.js 和 npm 是否存在。
- `frontend/dist/index.html` 是否存在。
- 首选端口是否可用。
- LibreOffice `soffice` 是否可用。

这个命令不会安装依赖，也不会启动服务，适合排查启动失败原因。

## Windows 轻量 EXE 路线

第一阶段建议只打包启动器本身，不把整个项目塞进单文件 exe。分发结构：

```text
SlidesReader/
  SlidesReader.exe
  backend/
  frontend/
  storage/
  README.md
```

打包命令：

```powershell
pyinstaller --onefile --console --name SlidesReader start.py
```

`--console` 表示保留终端窗口。用户可以看到启动进度、日志路径，也可以按 `Ctrl+C` 停止服务。

打包后的 exe 会以 exe 所在目录作为项目根目录，因此 `backend/` 和 `frontend/` 必须放在 exe 旁边。

## 不建议第一阶段做全内置 EXE

当前项目包含：

- Python 后端和虚拟环境依赖。
- `PyMuPDF` 这类带原生二进制的库。
- React 构建产物。
- SQLite 数据库和上传文件等运行数据。
- 可选 LibreOffice 依赖。

把这些全部打进单文件 exe 会明显增加调试和升级成本。轻量启动器更适合当前阶段。

