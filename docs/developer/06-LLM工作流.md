# LLM 工作流

## 基本概念

`LLM` 是 `Large Language Model` 的缩写，中文通常叫“大语言模型”。本项目通过 OpenAI-compatible API 调用 LLM。

`OpenAI-compatible API` 表示接口格式兼容 OpenAI 的 `chat completions` 请求结构。只要模型服务提供相同格式的 HTTP 接口，就可以通过配置 `base_url`、`api_key` 和 `model` 接入。

当前项目有三类 LLM 任务：

- 课程简介生成。
- 逐页讲稿生成。
- 当前页问答。

## 配置优先级

后端读取配置时，按下面顺序合并：

1. 代码中的默认 prompt 和默认值。
2. 环境变量。
3. SQLite `app_settings` 表。

最终数据库配置优先级最高。

当前配置项：

| key | 说明 |
| --- | --- |
| `base_url` | OpenAI-compatible 服务基础地址。 |
| `api_key` | 模型服务密钥。 |
| `model` | 模型名。 |
| `timeout_seconds` | HTTP 请求超时时间，范围 5 到 300 秒。 |
| `course_summary_prompt` | 课程简介 prompt。 |
| `lecture_notes_prompt` | 逐页讲稿 prompt。 |
| `page_chat_prompt` | 当前页问答 prompt。 |

所有 LLM 配置都必须能通过 WebUI 修改。未来新增温度、最大输出长度、多模型路由等配置时，也应该同步加入后端配置接口和前端设置页。

## LLMClient 请求格式

纯文本请求：

```json
{
  "model": "gpt-4.1-mini",
  "messages": [
    {
      "role": "user",
      "content": "prompt 文本"
    }
  ]
}
```

图文请求：

```json
{
  "model": "gpt-4.1-mini",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "prompt 文本"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/png;base64,..."
          }
        }
      ]
    }
  ]
}
```

图文请求可以携带多张图片。逐页讲稿目前只传当前页截图；当前页问答会在用户上传或粘贴图片、或者同一页存在最近历史图片时使用多图请求。

流式请求会在同一个 payload 中增加：

```json
{
  "stream": true
}
```

模型服务会按 `data: ...` 行返回增量内容。后端从 `choices[0].delta.content` 中读取文本片段，再转换成当前项目自己的 `NDJSON` 事件流返回给前端。

请求头：

- `Authorization: Bearer {api_key}`
- `Accept: application/json`
- `Content-Type: application/json`
- `User-Agent: SlidesReader/0.1 (+OpenAI-compatible client)`

`User-Agent` 是客户端标识。一些模型网关会拒绝 Python 默认请求头，所以这里显式设置。

## 课程简介生成

入口函数：

```python
generate_course_summary(document_id)
```

触发方式：

- PDF 上传并解析成功后自动触发。
- 用户调用 `POST /api/documents/{document_id}/course-summary/regenerate` 手动触发。

输入构造：

```python
build_course_summary_input(document_id)
build_course_summary_prompt(document, pages_text, truncated)
```

课程简介 prompt 会包含：

- 用户配置的 `course_summary_prompt`。
- 文档标题。
- 总页数。
- 每页页码和文字。
- 是否因为长度限制被截断的提示。

长度限制：

```python
COURSE_SUMMARY_INPUT_LIMIT = 12000
```

第一版用固定字符数截断，避免长 PDF 导致单次请求过大。后续如果需要更好效果，可以改为分页压缩、分段摘要或选择性页面输入。

成功后：

1. `documents.course_summary_status = ready`
2. `documents.course_summary = LLM 返回文本`
3. 清空 `course_summary_error`
4. 调用 `reset_document_lecture_notes_status(document_id)`
5. 提交 `generate_document_lecture_notes(document_id)` 后台任务

失败后：

1. `documents.course_summary_status = failed`
2. `documents.course_summary_error = 错误原因`
3. 不删除文档和页面记录
4. 不自动生成逐页讲稿

## 逐页讲稿生成

入口函数：

```python
generate_document_lecture_notes(document_id)
generate_single_page_lecture_notes(document, page)
```

触发方式：

- 课程简介生成成功后自动触发。
- 用户手动重新生成全部讲稿。
- 用户手动继续已暂停的生成任务。
- 用户手动重新生成某一页讲稿。

前置条件：

- 文档存在。
- `documents.status = ready`
- `documents.course_summary_status = ready`
- `documents.course_summary` 非空。

整份生成流程：

1. 获取文档级锁。
2. 读取课程简介和页面列表。
3. 按 `page_number ASC` 遍历。
4. 每页开始前检查 `lecture_notes_paused`。
5. 单页状态改为 `processing`。
6. 调用 LLM 生成。
7. 成功则改为 `ready` 并同步讲稿文字块。
8. 失败则改为 `failed`，记录错误，并继续下一页。

单页 prompt 由 `build_lecture_notes_prompt(document, page)` 构造，包含：

- 用户配置的 `lecture_notes_prompt`。
- 文档标题。
- 课程简介。
- 当前页页码。
- 当前页文字。
- 页面截图作为图像输入。

单页生成使用：

```python
client.complete_with_image(prompt, image_path)
```

如果当前页没有截图或截图文件不存在，生成会失败并记录错误。

## 暂停和继续

暂停只设置数据库字段：

```text
documents.lecture_notes_paused = 1
```

后台任务在每一页开始前检查：

```python
if is_lecture_notes_paused(document_id):
    break
```

因此：

- 当前已经发给 LLM 的页面不会被强制中断。
- 暂停生效点是“下一页开始前”。
- 已生成成功的页面保持 `ready`。
- 未生成页面保持 `pending`，或异常残留为 `processing`。

继续时：

1. 清除暂停标记。
2. 提交新的整份生成任务。
3. 只处理 `lecture_notes_status != ready` 的页面。

## 当前页问答

入口函数：

```python
chat_with_page(page_id, request)
```

触发方式：

```text
POST /api/pages/{page_id}/chat
POST /api/pages/{page_id}/chat/stream
```

流程：

1. 去掉问题首尾空白。
2. 问题为空时返回 `400`。
3. 如果请求是 `multipart/form-data`，读取并校验图片附件。
4. 查询页面上下文。
5. 先保存用户问题到 `chat_messages`。
6. 保存本轮图片附件到 `chat_attachments` 和 `storage/chat-attachments/`。
7. 读取最近问答历史，最多 `PAGE_CHAT_HISTORY_LIMIT = 20` 条。
8. 构造问答 prompt。
9. 非流式接口：如果本轮有图片或同一页有最近历史图片，使用 `complete_with_images` 调用 LLM；否则使用 `complete_text`。
10. 流式接口：如果本轮有图片或同一页有最近历史图片，使用 `stream_with_images` 调用 LLM；否则使用 `stream_text`。
11. 非流式接口成功后保存 `assistant` 消息，并返回当前页完整问答历史。
12. 流式接口会先返回 `user_message` 事件，再持续返回 `delta` 事件；模型正常结束后保存 `assistant` 消息，并返回 `done` 事件。

问答 prompt 包含：

- 用户配置的 `page_chat_prompt`。
- 文档标题。
- 课程简介。
- 当前页页码。
- 当前页文字。
- 当前页讲稿。
- 本页最近问答历史。
- 用户最新问题。

当前页问答的图片规则：

- 用户可以通过 `+` 按钮上传 PNG、JPEG、WebP 图片，也可以直接粘贴图片。
- 单轮最多 4 张图片，单张最大 10MB。
- 本轮图片会全部加入当前 LLM 请求。
- 后续追问会自动带入同一页最近 3 张历史图片。
- 当前页截图不会自动加入问答上下文，只有用户显式上传或粘贴的图片会进入会话上下文。

当前页问答的中断规则：

- 前端中断流式请求时，用户消息和附件可能已经保存。
- 后端只在完整回答生成结束后保存 `assistant` 消息。
- 因此中断不会保存半截 assistant 回答，前端会刷新当前页历史来对齐数据库状态。

## 错误处理原则

### 课程简介

课程简介失败只更新课程简介状态，不破坏 PDF 页面数据。

### 逐页讲稿

某页失败只标记该页失败，不影响其他页继续生成。

### 当前页问答

用户问题和本轮图片附件先保存。LLM 调用失败时，问题和图片不会丢失，但不会生成 assistant 消息。

### LLM 配置错误

如果没有配置 `base_url`、`api_key` 或 `model`，后端直接返回 `400`，不会发起外部请求。

## Prompt 维护约定

`Prompt` 是发送给 LLM 的指令文本。项目中所有 prompt 都应该遵守：

- 明确要求 LLM 扮演老师。
- 明确说明输出面向学生。
- 明确禁止简单复制 slides 原文。
- 明确要求围绕当前任务，不要泛泛总结。
- 保留 Markdown 输出能力。
- 可在 WebUI 修改。

前端显示约定：

- prompt 设置默认折叠。
- 折叠时只显示设置名称和展开按钮。
- 展开后文本框直接完整显示全部内容。
- 文本框内部不应该依赖滚动查看完整 prompt。
- 再次点击同一个按钮后折叠。

## 后续优化方向

可以优先考虑：

- 课程简介输入从固定截断改为分段压缩。
- 逐页讲稿生成支持跳过低价值页面。
- 不同任务使用不同模型，例如课程简介用大模型，问答用快模型。
- 添加温度、最大 token、重试次数等 LLM 配置。
- 为当前页问答增加是否自动带入当前页截图的开关。
- 将 LLMClient 从 `urllib.request` 迁移到更易测试的 HTTP 客户端。
