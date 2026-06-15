# Slides Reader

Slides Reader 是一个本地单用户的 AI slides 阅读与授课工具。用户上传 PDF、PPT 或 PPTX slides 后，系统会统一转换或保存为 PDF，解析每页文字和截图，并调用 LLM 扮演老师生成课程简介、逐页讲稿，同时支持围绕当前页提问。

这里的 `LLM` 是 `Large Language Model` 的缩写，中文通常叫“大语言模型”。本项目通过 OpenAI-compatible API 调用模型服务。

## 当前能力

- PDF/PPT/PPTX 上传、本地保存、文档列表持久化；PPT/PPTX 会通过 LibreOffice 转换为 PDF。
- SQLite 数据库保存文档、页面、讲稿文字块、问答历史和 LLM 配置。
- PyMuPDF 解析 PDF 页数、每页文字和每页 PNG 截图。
- WebUI 修改 LLM 服务地址、API Key、模型名、超时时间和 prompt。
- 上传后自动生成课程简介。
- 课程简介生成成功后自动逐页生成讲稿。
- 支持暂停、继续、整份重新生成和单页重新生成讲稿。
- PDF 阅读器、缩略图导航、课程简介侧栏、当前页问答侧栏。
- 可拖动、可缩放并持久化的讲稿文字块。
- 按页隔离并持久化的当前页问答。
- 文档重命名和删除。

## 技术栈

- 后端：`Python + FastAPI`
- 数据库：`SQLite`
- PDF 处理：`PyMuPDF`
- PPT/PPTX 转 PDF：`LibreOffice`
- LLM 调用：`OpenAI-compatible chat completions API`
- 前端：`React + TypeScript + Vite`
- PDF 前端渲染：`react-pdf`

`FastAPI` 是 Python Web 框架，用来编写 HTTP API。`SQLite` 是轻量级本地数据库，适合第一版本地单用户应用。`React` 用来构建网页界面，`TypeScript` 是带类型检查的 JavaScript，`Vite` 是前端开发服务器和构建工具。

## 开发者文档

第一版任务文档已经迁移为长期开发者文档。后续开发请优先阅读：

- [开发者文档入口](./docs/developer/README.md)
- [项目总览](./docs/developer/01-项目总览.md)
- [运行与开发环境](./docs/developer/02-运行与开发环境.md)
- [后端架构](./docs/developer/03-后端架构.md)
- [数据模型与状态机](./docs/developer/04-数据模型与状态机.md)
- [API 接口契约](./docs/developer/05-API接口契约.md)
- [LLM 工作流](./docs/developer/06-LLM工作流.md)
- [前端架构](./docs/developer/07-前端架构.md)
- [测试与验收](./docs/developer/08-测试与验收.md)
- [后续开发路线](./docs/developer/09-后续开发路线.md)

`docs/tasks/` 是初版任务拆解文档。确认新文档足够后，可以删除任务文档，后续上下文以 `docs/developer/` 为准。

## 后端启动

进入后端目录：

```powershell
cd backend
```

创建 Python 虚拟环境：

```powershell
python -m venv .venv
```

激活虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

安装依赖：

```powershell
pip install -r requirements.txt
```

启动 FastAPI 后端：

```powershell
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```text
http://127.0.0.1:8000/api/health
```

## 前端启动

进入前端目录：

```powershell
cd frontend
```

安装依赖：

```powershell
npm install
```

启动 Vite 前端：

```powershell
npm run dev
```

浏览器打开：

```text
http://localhost:5173
```

## 一键启动

项目根目录提供 PowerShell 启动脚本：

```powershell
.\launch.ps1
```

该脚本会分别启动：

- 后端：`http://127.0.0.1:8000`
- 前端：`http://localhost:5173`

运行前需要先完成后端虚拟环境依赖安装和前端 `npm install`。
PPT/PPTX 上传还需要 LibreOffice；如果本机没有安装，可以先运行：

```powershell
.\setup-env.ps1
```

这个脚本会优先复用本机 LibreOffice，找不到时会把 LibreOffice Portable 下载到项目的 `tools/libreoffice/` 目录。

## 运行数据

默认运行数据保存在：

```text
storage/
```

主要内容：

```text
storage/app.db
storage/documents/
storage/pages/
```

这些是运行时数据，不应作为源码提交。测试时可以用环境变量覆盖：

```powershell
$env:SLIDES_READER_STORAGE_DIR="C:\temp\slides-reader-storage"
```

## 基础检查

后端语法检查：

```powershell
cd backend
.\.venv\Scripts\python.exe -m py_compile main.py
```

前端构建检查：

```powershell
cd frontend
npm run build
```

更完整的测试和手动验收流程见 [测试与验收](./docs/developer/08-测试与验收.md)。
