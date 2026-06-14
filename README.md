# Slides Reader

这是一个 AI slides 阅读与授课工具。第一版目标是让用户上传 PDF slides，由 LLM 扮演老师生成课程简介、逐页讲稿，并支持针对当前页提问。

当前仓库已完成任务 01 到任务 06。现在包含最小前后端通信能力、PDF 上传和本地保存能力、SQLite 文档记录持久化能力、PDF 页数和每页文字解析能力、每页 PNG 截图渲染能力，以及可在 WebUI 修改的 LLM 配置和统一 LLM 客户端。不包含课程简介或逐页讲稿生成。

## 技术栈

- 后端：`Python + FastAPI`
  - `FastAPI` 是 Python Web 框架，用来编写 HTTP API。
- PDF 处理：`PyMuPDF`
  - `PyMuPDF` 是 Python PDF 处理库，用来读取 PDF 页数和提取每页文字。
- LLM 调用：`OpenAI-compatible API`
  - `OpenAI-compatible API` 指使用类似 OpenAI 的接口格式，可以通过配置切换不同模型服务商。
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
  "title": "用户上传的原始文件名.pdf",
  "filename": "用户上传的原始文件名.pdf",
  "file_path": "PDF 在本地的保存路径",
  "saved_filename": "保存到本地的文件名.pdf",
  "status": "ready",
  "page_count": 10,
  "error_message": null,
  "created_at": "上传时间"
}
```

上传成功后，PDF 会保存到：

```text
storage/documents/
```

SQLite 数据库文件会自动创建到：

```text
storage/app.db
```

文档列表接口：

```text
GET http://127.0.0.1:8000/api/documents
```

该接口会从 SQLite 数据库读取已上传文档记录。后端重启后，之前上传过的文档记录仍然可以通过这个接口返回。

文档页面列表接口：

```text
GET http://127.0.0.1:8000/api/documents/{document_id}/pages
```

该接口返回指定文档的每一页解析记录，包括页码、页面文字、页面截图路径、页面截图访问地址、页面状态和错误信息。页码从 1 开始，符合用户阅读 PDF 时的习惯。

页面截图接口：

```text
GET http://127.0.0.1:8000/api/documents/{document_id}/pages/{page_number}/image
```

该接口会返回指定文档指定页码的 PNG 截图。截图文件会保存到：

```text
storage/pages/
```

截图文件名会包含 `document_id` 和页码，避免不同文档的页面图片互相覆盖。

LLM 配置读取接口：

```text
GET http://127.0.0.1:8000/api/llm/config
```

该接口返回当前 LLM 配置。为了避免泄露密钥，后端不会返回 `LLM_API_KEY` 明文，只会返回是否已配置和掩码。

LLM 配置保存接口：

```text
PATCH http://127.0.0.1:8000/api/llm/config
```

请求体示例：

```json
{
  "base_url": "https://api.openai.com/v1",
  "api_key": "你的 API Key",
  "model": "gpt-4.1-mini",
  "timeout_seconds": 60
}
```

如果不传 `api_key` 字段，后端会保留之前保存的 API Key。所有 LLM 相关配置都必须能通过 WebUI 修改，环境变量只作为未保存配置时的默认值。

LLM 连接测试接口：

```text
POST http://127.0.0.1:8000/api/llm/test
```

请求体示例：

```json
{
  "prompt": "请用一句中文回复：LLM 配置测试成功。"
}
```

该接口会使用当前配置向 OpenAI-compatible 服务发起一次文本请求，用来验证 `base_url`、`api_key` 和 `model` 是否可用。

文档重命名接口：

```text
PATCH http://127.0.0.1:8000/api/documents/{document_id}
```

请求体示例：

```json
{
  "title": "新的文档标题"
}
```

该接口只修改数据库中的文档显示标题，不修改本地 PDF 文件名，也不修改 `file_path`。

文档删除接口：

```text
DELETE http://127.0.0.1:8000/api/documents/{document_id}
```

该接口会删除：

- `documents` 中的文档记录。
- `pages` 中关联的页面记录。
- `storage/documents/` 中对应的本地 PDF 文件。

如果本地 PDF 文件已经不存在，接口仍然会完成数据库删除。

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

页面中还会显示 LLM 配置区域，可以修改 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 和请求超时时间，并可以点击测试按钮验证当前配置是否能成功调用模型。

页面中还会显示已上传文档列表。这个列表来自 SQLite 数据库，所以刷新网页后仍然会显示历史上传记录。列表中会显示文档解析状态和总页数，并提供重命名和删除按钮。

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
- 后端启动后能自动创建 `storage/app.db`。
- 上传 PDF 后，SQLite 的 `documents` 表中会新增一条记录。
- 调用 `GET /api/documents` 能返回已上传文档列表。
- 后端重启后，`GET /api/documents` 仍然能返回之前的文档记录。
- 前端刷新后仍然能显示已上传文档列表。
- 上传多页 PDF 后，数据库会为每一页创建一条 `pages` 记录。
- `GET /api/documents` 会返回每个文档的 `page_count`。
- `GET /api/documents/{document_id}/pages` 会返回页面文字和页面状态。
- 上传 PDF 后，后端会为每一页生成 PNG 截图。
- `GET /api/documents/{document_id}/pages` 会返回每页的 `image_path` 和 `image_url`。
- 浏览器可以通过 `GET /api/documents/{document_id}/pages/{page_number}/image` 打开指定页面截图。
- 可以在 WebUI 中修改 LLM 配置。
- 后端通过 `LLMClient` 封装统一的 OpenAI-compatible 文本和图文调用入口。
- LLM 配置测试接口可以在配置正确时返回模型回答，在配置错误时返回明确错误。
- 空白页也会创建页面记录，不会被跳过。
- PDF 损坏或无法打开时，文档状态会变为 `failed`，后端服务不会崩溃。
- 可以通过 `PATCH /api/documents/{document_id}` 重命名文档显示标题。
- 空标题重命名会返回错误。
- 可以通过 `DELETE /api/documents/{document_id}` 删除文档。
- 删除文档会同时删除文档记录、页面记录和本地 PDF 文件。
- 前端文档列表提供重命名和删除按钮。
