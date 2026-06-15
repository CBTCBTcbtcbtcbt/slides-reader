# API 接口契约

本文档记录当前后端对前端开放的 HTTP API。除文件接口外，返回值都是 JSON。

开发环境中，前端通过 Vite 代理请求 `/api/...`。后端真实地址默认是：

```text
http://127.0.0.1:8000
```

## 通用约定

- 所有页码 `page_number` 都从 1 开始。
- 所有 ID 都是字符串，当前由后端 `uuid4` 生成。
- 时间字段使用 UTC ISO 字符串。
- 失败时 FastAPI 通常返回：

```json
{
  "detail": "错误原因"
}
```

- Pydantic 参数校验失败时，FastAPI 会返回 `422`，结构为标准校验错误列表。

## 统一响应对象

### DocumentItem

文档对象在文档列表、上传成功、重命名成功等接口中复用。

```json
{
  "document_id": "string",
  "title": "课程.pdf",
  "file_path": "C:\\...\\storage\\documents\\xxx.pdf",
  "status": "ready",
  "page_count": 10,
  "error_message": null,
  "course_summary": "课程简介正文",
  "course_summary_status": "ready",
  "course_summary_error": null,
  "lecture_notes_paused": false,
  "created_at": "2026-06-15T12:00:00+00:00"
}
```

字段说明：

- `document_id`：前端后续请求文档详情、文件、页面和状态时使用。
- `title`：用户可修改的显示标题。
- `file_path`：后端本地路径，前端只展示或调试，不应直接访问。
- `status`：PDF 解析状态。
- `page_count`：该文档关联的页面数量。
- `error_message`：文档级错误。
- `course_summary`：课程简介正文。
- `course_summary_status`：课程简介状态。
- `course_summary_error`：课程简介失败原因。
- `lecture_notes_paused`：逐页讲稿是否暂停。
- `created_at`：创建时间。

### PageItem

页面对象由 `GET /api/documents/{document_id}/pages` 返回。

```json
{
  "page_id": "string",
  "document_id": "string",
  "page_number": 1,
  "text": "页面文字",
  "image_path": "C:\\...\\storage\\pages\\xxx-page-1.png",
  "image_url": "/api/documents/{document_id}/pages/1/image",
  "status": "ready",
  "error_message": null,
  "lecture_notes": "本页讲稿",
  "lecture_notes_status": "ready",
  "lecture_notes_error": null,
  "note_block": {
    "note_block_id": "string",
    "page_id": "string",
    "content": "本页讲稿",
    "x": 24,
    "y": 24,
    "width": 320,
    "height": 240,
    "created_at": "2026-06-15T12:00:00+00:00",
    "updated_at": "2026-06-15T12:00:00+00:00"
  },
  "chat_messages": [],
  "created_at": "2026-06-15T12:00:00+00:00"
}
```

`note_block` 可能是 `null`。只有当前页讲稿已经生成成功时，后端才会创建或补齐讲稿文字块。

### ChatMessageItem

```json
{
  "chat_message_id": "string",
  "page_id": "string",
  "role": "user",
  "content": "问题或回答正文",
  "created_at": "2026-06-15T12:00:00+00:00"
}
```

`role` 当前只有：

- `user`：学生问题。
- `assistant`：AI 老师回答。

## 健康检查

```text
GET /api/health
```

用途：

- 前端启动时确认后端是否可用。
- 开发者手动检查服务是否启动。

成功响应：

```json
{
  "status": "ok",
  "service": "slides-reader-api"
}
```

## 文档列表

```text
GET /api/documents
```

用途：

- 文件管理页加载已上传文档列表。
- 前端刷新后恢复历史文档。

成功响应：

```json
[
  {
    "document_id": "string",
    "title": "课程.pdf",
    "file_path": "string",
    "status": "ready",
    "page_count": 10,
    "error_message": null,
    "course_summary": null,
    "course_summary_status": "processing",
    "course_summary_error": null,
    "lecture_notes_paused": false,
    "created_at": "string"
  }
]
```

排序规则：按 `created_at DESC` 返回，最新上传在前。

## 上传 PDF

```text
POST /api/documents
```

请求格式：

- `multipart/form-data`
- 文件字段名：`file`
- 只接受文件名后缀 `.pdf` 且 `content-type = application/pdf`

成功状态码：`201`

成功响应：

```json
{
  "document_id": "string",
  "title": "原始文件名.pdf",
  "filename": "原始文件名.pdf",
  "file_path": "C:\\...\\storage\\documents\\xxx.pdf",
  "saved_filename": "document_id.pdf",
  "status": "ready",
  "page_count": 10,
  "error_message": null,
  "course_summary": null,
  "course_summary_status": "processing",
  "course_summary_error": null,
  "lecture_notes_paused": false,
  "created_at": "string"
}
```

后端行为：

1. 保存 PDF。
2. 创建 `documents` 记录。
3. 同步解析 PDF 页面和截图。
4. 如果解析成功，后台生成课程简介。
5. 如果解析失败，文档状态为 `failed`。

常见错误：

- `400`：不是合法 PDF。
- `500`：PDF 已保存但无法读取文档记录等内部错误。

## 读取原始 PDF 文件

```text
GET /api/documents/{document_id}/file
```

用途：

- 阅读器通过 `react-pdf` 加载原始 PDF。

成功响应：

- 文件响应。
- `media_type = application/pdf`

常见错误：

- `404`：文档不存在。
- `404`：PDF 文件不存在，可能被手动删除。
- `500`：数据库中的文件路径越过允许目录。

## 文档处理状态

```text
GET /api/documents/{document_id}/status
```

用途：

- 文件管理页和阅读器轮询生成进度。
- 判断是否还需要继续轮询。

成功响应：

```json
{
  "document_id": "string",
  "title": "课程.pdf",
  "status": "ready",
  "error_message": null,
  "course_summary_status": "ready",
  "course_summary_error": null,
  "course_summary_ready": true,
  "total_pages": 10,
  "lecture_notes_ready_count": 8,
  "lecture_notes_failed_count": 1,
  "lecture_notes_processing_count": 1,
  "lecture_notes_pending_count": 0,
  "lecture_notes_paused": false,
  "should_poll": true,
  "pages": [
    {
      "page_id": "string",
      "page_number": 1,
      "status": "ready",
      "error_message": null,
      "lecture_notes_status": "ready",
      "lecture_notes_error": null
    }
  ]
}
```

`should_poll` 是前端是否继续轮询的主要依据。

常见错误：

- `404`：文档不存在。

## 页面列表

```text
GET /api/documents/{document_id}/pages
```

用途：

- 查看文档所有页面文字、截图地址、讲稿状态和讲稿内容。
- 阅读器加载当前页对应的讲稿文字块和问答历史。
- 文件页展开“逐页讲稿”时展示每页讲稿。

成功响应：

```json
[
  {
    "page_id": "string",
    "document_id": "string",
    "page_number": 1,
    "text": "页面文字",
    "image_path": "string",
    "image_url": "/api/documents/{document_id}/pages/1/image",
    "status": "ready",
    "error_message": null,
    "lecture_notes": "本页讲稿",
    "lecture_notes_status": "ready",
    "lecture_notes_error": null,
    "note_block": null,
    "chat_messages": [],
    "created_at": "string"
  }
]
```

后端兼容行为：

- 如果历史数据中某页讲稿已经 `ready` 但没有 `note_blocks`，该接口会自动补齐默认文字块。

常见错误：

- `404`：文档不存在。

## 页面截图

```text
GET /api/documents/{document_id}/pages/{page_number}/image
```

用途：

- 浏览器显示后端渲染的页面 PNG。
- LLM 生成逐页讲稿时读取本地图片路径，不通过这个 HTTP 接口。

成功响应：

- 文件响应。
- `media_type = image/png`

常见错误：

- `404`：页码小于 1。
- `404`：文档不存在。
- `404`：页面不存在。
- `404`：当前页面没有截图。
- `404`：截图文件被手动删除。
- `500`：截图路径越过允许目录。

## LLM 配置读取

```text
GET /api/llm/config
```

成功响应：

```json
{
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4.1-mini",
  "timeout_seconds": 60,
  "course_summary_prompt": "string",
  "lecture_notes_prompt": "string",
  "page_chat_prompt": "string",
  "api_key_configured": true,
  "api_key_preview": "sk-p********abcd"
}
```

注意：

- 永远不返回 API Key 明文。
- `api_key_preview` 是掩码。

## LLM 配置保存

```text
PATCH /api/llm/config
```

请求体：

```json
{
  "base_url": "https://api.openai.com/v1",
  "api_key": "新的 API Key",
  "model": "gpt-4.1-mini",
  "timeout_seconds": 60,
  "course_summary_prompt": "课程简介 prompt",
  "lecture_notes_prompt": "逐页讲稿 prompt",
  "page_chat_prompt": "当前页问答 prompt"
}
```

字段规则：

- `base_url` 必填，保存前会去掉首尾空白和末尾 `/`。
- `model` 必填，不能为空。
- `timeout_seconds` 必填，必须在 `5` 到 `300` 秒之间。
- `api_key` 不传或为 `null` 时保留旧密钥。
- `api_key` 传空字符串时清空密钥。
- 三个 prompt 如果传入，必须不是空字符串。

成功响应与读取配置接口相同。

常见错误：

- `400`：地址为空。
- `400`：模型名为空。
- `400`：超时时间非法。
- `400`：prompt 为空。

## LLM 连接测试

```text
POST /api/llm/test
```

请求体：

```json
{
  "prompt": "请用一句中文回复：LLM 配置测试成功。"
}
```

成功响应：

```json
{
  "status": "ok",
  "answer": "模型返回内容"
}
```

常见错误：

- `400`：测试 prompt 为空。
- `400`：LLM 配置缺失。
- `502`：LLM 服务返回错误、连接失败或返回格式不符合预期。
- `504`：LLM 请求超时。

## 重新生成课程简介

```text
POST /api/documents/{document_id}/course-summary/regenerate
```

用途：

- 用户手动重新生成课程简介。
- 课程简介失败后重试。

成功响应：

```json
{
  "status": "processing",
  "document_id": "string"
}
```

后端行为：

1. 要求文档存在。
2. 要求文档至少有一页。
3. 设置 `course_summary_status = processing`。
4. 清空旧简介和旧错误。
5. 提交后台任务。
6. 后台生成成功后，会自动重置并重新生成全部逐页讲稿。

常见错误：

- `404`：文档不存在。
- `400`：文档没有页面，无法生成简介。

## 重新生成整份逐页讲稿

```text
POST /api/documents/{document_id}/lecture-notes/regenerate
```

用途：

- 用户手动重新生成全部页面讲稿。
- prompt 更新后重新跑整份讲稿。

成功响应：

```json
{
  "status": "processing",
  "document_id": "string"
}
```

前置条件：

- 文档存在。
- 文档解析状态是 `ready`。
- 课程简介状态是 `ready`。
- 课程简介正文非空。

后端行为：

- 清除暂停标记。
- 把所有页面讲稿重置为 `pending`。
- 清空旧讲稿和旧错误。
- 后台按页码顺序生成。

常见错误：

- `404`：文档不存在。
- `400`：文档还没有解析完成。
- `400`：课程简介未生成成功。

## 暂停逐页讲稿生成

```text
POST /api/documents/{document_id}/lecture-notes/pause
```

成功响应：

```json
{
  "status": "paused",
  "document_id": "string",
  "lecture_notes_paused": true
}
```

行为：

- 设置 `documents.lecture_notes_paused = 1`。
- 不强制中断当前正在请求 LLM 的页面。
- 后台生成任务会在开始下一页前检查暂停状态。

常见错误：

- `404`：文档不存在。

## 继续逐页讲稿生成

```text
POST /api/documents/{document_id}/lecture-notes/resume
```

成功响应：

```json
{
  "status": "processing",
  "document_id": "string",
  "lecture_notes_paused": false
}
```

行为：

- 要求课程简介已生成成功。
- 设置 `documents.lecture_notes_paused = 0`。
- 提交后台任务继续生成未完成页面。
- 已经 `ready` 的页面不会被覆盖。

常见错误：

- `404`：文档不存在。
- `400`：课程简介未生成成功。

## 重新生成指定页讲稿

按文档 ID 和页码：

```text
POST /api/documents/{document_id}/pages/{page_number}/lecture-notes/regenerate
```

按页面 ID：

```text
POST /api/pages/{page_id}/regenerate
```

前端当前主要使用按页面 ID 的接口。

成功响应示例：

```json
{
  "status": "processing",
  "document_id": "string",
  "page_id": "string",
  "page_number": 3
}
```

行为：

- 要求课程简介已生成成功。
- 将该页讲稿状态改为 `processing`。
- 清空该页旧讲稿和旧错误。
- 后台只生成这一页。

常见错误：

- `404`：页面或文档不存在。
- `400`：课程简介未生成成功。

## 保存讲稿文字块位置

```text
PATCH /api/note-blocks/{note_block_id}
```

请求体：

```json
{
  "x": 24,
  "y": 24,
  "width": 320,
  "height": 240
}
```

成功响应：

```json
{
  "note_block_id": "string",
  "page_id": "string",
  "content": "讲稿正文",
  "x": 24,
  "y": 24,
  "width": 320,
  "height": 240,
  "created_at": "string",
  "updated_at": "string"
}
```

规则：

- 只允许更新位置和尺寸。
- 不允许通过该接口修改 `content`。
- 坐标和尺寸必须是有限数字。
- `width >= 120`
- `height >= 80`

常见错误：

- `400`：坐标或尺寸非法。
- `400`：文字块太小。
- `404`：文字块不存在。

## 当前页问答

```text
POST /api/pages/{page_id}/chat
```

请求体：

```json
{
  "question": "请解释当前页这个公式的含义。"
}
```

成功响应：

```json
{
  "status": "ok",
  "page_id": "string",
  "user_message": {
    "chat_message_id": "string",
    "page_id": "string",
    "role": "user",
    "content": "请解释当前页这个公式的含义。",
    "created_at": "string"
  },
  "assistant_message": {
    "chat_message_id": "string",
    "page_id": "string",
    "role": "assistant",
    "content": "AI 老师回答",
    "created_at": "string"
  },
  "messages": []
}
```

重要行为：

- 后端会先保存用户问题。
- 如果后续 LLM 调用失败，用户问题仍然保留在 `chat_messages` 表。
- 构造 prompt 时会带上课程简介、当前页文字、当前页讲稿、最近问答历史和最新问题。
- 最近问答历史最多取 `PAGE_CHAT_HISTORY_LIMIT = 20` 条。

常见错误：

- `400`：问题为空。
- `404`：页面不存在。
- `502`：LLM 调用失败。
- `504`：LLM 请求超时。

## 重命名文档

```text
PATCH /api/documents/{document_id}
```

请求体：

```json
{
  "title": "新的文档标题"
}
```

成功响应：

- 返回更新后的 `DocumentItem`。

规则：

- 标题会去掉首尾空白。
- 空标题返回错误。
- 只修改数据库中的显示标题，不修改本地 PDF 文件名和 `file_path`。

常见错误：

- `400`：标题为空。
- `404`：文档不存在。

## 删除文档

```text
DELETE /api/documents/{document_id}
```

成功状态码：

```text
204 No Content
```

删除内容：

- `chat_messages` 中该文档所有页面的问答。
- `note_blocks` 中该文档所有页面的文字块。
- `pages` 中该文档所有页面。
- `documents` 中该文档。
- `storage/documents/` 中对应 PDF。
- `storage/pages/` 中对应页面截图。

删除顺序：

1. 检查文档存在。
2. 检查 PDF 文件路径安全。
3. 查询并检查所有截图路径安全。
4. 删除数据库记录。
5. 删除原始 PDF 文件。
6. 删除页面截图文件。

如果本地文件已经不存在，数据库删除仍然算成功。

常见错误：

- `404`：文档不存在。
- `500`：路径越界。
- `500`：数据库已删除但本地文件删除失败。

