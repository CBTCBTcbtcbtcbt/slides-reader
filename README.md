# Slides Reader

这是一个 AI slides 阅读与授课工具。第一版目标是让用户上传 PDF slides，由 LLM 扮演老师生成课程简介、逐页讲稿，并支持针对当前页提问。

当前仓库已完成任务 01 和任务 02。现在包含最小前后端通信能力，以及 PDF 上传和本地保存能力，不包含数据库、PDF 解析或 LLM 调用。

## 技术栈

- 后端：`Python + FastAPI`
  - `FastAPI` 是 Python Web 框架，用来编写 HTTP API。
- 前端：`React + TypeScript + Vite`
  - `React` 用来构建网页界面。
  - `TypeScript` 是带类型检查的 JavaScript。
  - `Vite` 是前端开发服务器和构建工具。

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

健康检查接口：

```text
http://127.0.0.1:8000/api/health
```

正常返回示例：

```json
{
  "status": "ok",
  "service": "slides-reader-api"
}
```

PDF 上传接口：

```text
POST http://127.0.0.1:8000/api/documents
```

请求格式：

- 使用 `multipart/form-data`。
- 文件字段名为 `file`。
- 只接受 `.pdf` 后缀且 `content-type` 为 `application/pdf` 的文件。

成功返回示例：

```json
{
  "document_id": "后端生成的唯一 ID",
  "filename": "用户上传的原始文件名.pdf",
  "saved_filename": "保存到本地的文件名.pdf"
}
```

上传成功后，PDF 会保存到：

```text
storage/documents/
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

如果后端已经启动，页面会显示后端连接成功。

页面中也会显示 PDF 上传区域。选择 `.pdf` 文件并点击上传后，页面会显示上传成功和后端返回的 `document_id`。

## 当前任务验收

- 后端能启动。
- 访问 `/api/health` 返回 HTTP 200。
- 前端能启动。
- 前端页面能请求后端健康检查接口。
- 页面能显示后端连接成功。
- 前端可以选择 PDF 文件并上传。
- 后端可以把 PDF 保存到 `storage/documents/`。
- 后端响应中包含 `document_id`。
- 上传非 PDF 文件时，后端会拒绝请求。
