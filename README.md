# Slides Reader

这是一个 AI slides 阅读与授课工具。第一版目标是让用户上传 PDF slides，由 LLM 扮演老师生成课程简介、逐页讲稿，并支持针对当前页提问。

当前仓库已完成任务 01 到任务 11。现在包含最小前后端通信能力、PDF 上传和本地保存能力、SQLite 文档记录持久化能力、PDF 页数和每页文字解析能力、每页 PNG 截图渲染能力、可在 WebUI 修改的 LLM 配置和统一 LLM 客户端、上传后自动生成课程简介的能力、课程简介完成后逐页生成讲稿的能力、PDF 阅读界面、可拖动讲稿文字块，以及按页独立保存的当前页问答能力。

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

任务 08 起，该接口还会返回逐页讲稿字段：`lecture_notes`、`lecture_notes_status` 和 `lecture_notes_error`。`lecture_notes_status` 使用 `pending`、`processing`、`ready`、`failed` 表示等待生成、生成中、生成成功和生成失败。

任务 10 起，该接口还会返回 `note_block`，用于保存当前页可拖动讲稿文字块的位置、尺寸和内容。

任务 11 起，该接口还会返回 `chat_messages`，表示当前页独立问答历史。每条消息包含 `chat_message_id`、`page_id`、`role`、`content` 和 `created_at`。`role` 使用 `user` 表示学生问题，使用 `assistant` 表示 AI 老师回答。

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
  "timeout_seconds": 60,
  "course_summary_prompt": "生成课程简介时使用的 prompt",
  "lecture_notes_prompt": "生成逐页讲稿时使用的 prompt",
  "page_chat_prompt": "当前页问答时使用的 prompt"
}
```

如果不传 `api_key` 字段，后端会保留之前保存的 API Key。课程简介 prompt、逐页讲稿 prompt 和当前页问答 prompt 也属于配置项，可以在 WebUI 中修改。所有 LLM 相关配置都必须能通过 WebUI 修改，环境变量只作为未保存配置时的默认值。

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

课程简介重新生成接口：

```text
POST http://127.0.0.1:8000/api/documents/{document_id}/course-summary/regenerate
```

该接口会把指定文档的课程简介状态改为生成中，并在后台重新调用 LLM 生成课程简介。课程简介生成失败不会影响 PDF 页面记录和截图继续使用。

课程简介重新生成成功后，后端会自动重新生成整份逐页讲稿，保证逐页讲稿使用最新课程简介。

逐页讲稿整份重新生成接口：

```text
POST http://127.0.0.1:8000/api/documents/{document_id}/lecture-notes/regenerate
```

该接口要求课程简介已经生成成功。接口提交后，后端会在后台按页码顺序重新生成全部页面讲稿。

逐页讲稿单页重新生成接口：

```text
POST http://127.0.0.1:8000/api/documents/{document_id}/pages/{page_number}/lecture-notes/regenerate
```

该接口要求课程简介已经生成成功。接口提交后，后端只重新生成指定页的讲稿。

文档处理状态接口：

```text
GET http://127.0.0.1:8000/api/documents/{document_id}/status
```

该接口返回文档整体状态、课程简介状态、总页数、已生成讲稿页数、失败页数、等待页数、生成中页数，以及每一页的解析状态、讲稿状态和失败原因。前端会定期调用这个接口显示生成进度，并在后端返回 `should_poll` 为 `false` 后停止无意义轮询。

按页面 ID 重新生成单页讲稿接口：

```text
POST http://127.0.0.1:8000/api/pages/{page_id}/regenerate
```

该接口要求课程简介已经生成成功。接口提交后，后端只重新生成这个 `page_id` 对应页面的讲稿，不会清空其他页面已经生成成功的讲稿。

当前页问答接口：

```text
POST http://127.0.0.1:8000/api/pages/{page_id}/chat
```

请求体示例：

```json
{
  "question": "请解释当前页这个公式的含义。"
}
```

该接口会先把用户问题保存到 `chat_messages` 表，再把课程简介、当前页文字、当前页讲稿、当前页历史问答和最新问题一起发送给 LLM。LLM 成功回答后，后端会保存 `assistant` 消息，并返回当前页完整问答历史。如果 LLM 调用失败，用户问题仍然会保存在数据库中，前端会显示错误并恢复输入框。

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
- `note_blocks` 中关联的讲稿文字块记录。
- `chat_messages` 中关联的当前页问答记录。
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

页面中还会显示 LLM 配置区域，可以修改 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`、请求超时时间、课程简介 prompt、逐页讲稿 prompt 和当前页问答 prompt，并可以点击测试按钮验证当前配置是否能成功调用模型。

所有 prompt 类设置在前端 WebUI 中都必须默认折叠显示，只露出设置名称和展开按钮。用户点击展开按钮后，前端才完整显示可编辑文本框；展开后的文本框必须直接显示全部 prompt 内容，不允许在文本框内部用滑轨滚动查看。再次点击同一个按钮后，文本框应重新折叠。后续新增逐页讲稿 prompt、问答 prompt 或其他 prompt setting 时，都需要遵守这个显示规则。

页面中还会显示已上传文档列表。这个列表来自 SQLite 数据库，所以刷新网页后仍然会显示历史上传记录。列表中会显示文档解析状态、总页数、课程简介状态和 AI 生成进度，并提供重命名、删除、重新生成简介、查看页面讲稿、重新生成全部讲稿和重新生成单页讲稿按钮。点击“阅读 PDF”后，阅读页会显示原始 PDF、缩略图、可拖动讲稿文字块、当前文档生成进度，以及当前页底部的问答区域。

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
- 上传并解析 PDF 成功后，后端会在后台调用 LLM 生成课程简介。
- `GET /api/documents` 会返回 `course_summary`、`course_summary_status` 和 `course_summary_error`。
- 前端文档列表可以展示课程简介内容、生成中状态和失败原因。
- 可以通过 WebUI 修改课程简介 prompt。
- prompt 类设置在 WebUI 中默认折叠，点击展开后才能完整编辑，再次点击后折叠。
- 可以通过重新生成接口重新生成某个文档的课程简介。
- 课程简介生成成功后，后端会按页码顺序调用 LLM 为每一页生成讲稿。
- `GET /api/documents/{document_id}/pages` 会返回 `lecture_notes`、`lecture_notes_status` 和 `lecture_notes_error`。
- 前端文档列表可以展开查看每页讲稿状态、讲稿正文和失败原因。
- 可以通过 WebUI 修改逐页讲稿 prompt。
- 可以通过 WebUI 修改当前页问答 prompt。
- 可以重新生成整份文档的逐页讲稿，也可以重新生成指定页讲稿。
- 单页讲稿生成失败时，不影响其他页面讲稿继续生成或显示已有结果。
- `GET /api/documents/{document_id}/status` 会返回文档、课程简介和每一页讲稿的生成进度。
- 前端会自动刷新仍在生成中的文档进度，并在生成结束后停止轮询。
- 页面讲稿失败时，前端会显示失败原因，并提供单页重试按钮。
- 阅读页底部可以针对当前页向 AI 老师提问。
- 当前页问答会保存到 `chat_messages` 表，刷新页面后仍然存在。
- 切换页面后，只显示新页面自己的问答历史。
- 当前页问答调用 LLM 失败时，用户问题不会丢失，前端会显示错误并恢复可输入状态。
- 空白页也会创建页面记录，不会被跳过。
- PDF 损坏或无法打开时，文档状态会变为 `failed`，后端服务不会崩溃。
- 可以通过 `PATCH /api/documents/{document_id}` 重命名文档显示标题。
- 空标题重命名会返回错误。
- 可以通过 `DELETE /api/documents/{document_id}` 删除文档。
- 删除文档会同时删除文档记录、页面记录和本地 PDF 文件。
- 前端文档列表提供重命名和删除按钮。
