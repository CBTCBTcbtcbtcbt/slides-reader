"""后端配置、路径和默认常量。

这个模块只保存不会直接执行业务流程的配置值。把这些值集中起来后，
数据库、PDF 服务、LLM 服务和路由都可以复用同一套路径与默认参数。
"""

import threading
from os import getenv
from pathlib import Path


# BASE_DIR 表示 backend 目录的绝对路径。
# 任何从文件系统读取或写入运行数据的模块，都应该从这个路径推导项目位置。
BASE_DIR = Path(__file__).resolve().parent

# DEFAULT_STORAGE_DIR 表示默认运行数据目录。
# 当前项目是本地单用户工具，所以默认把数据库、PDF 和截图放在项目根目录的 storage。
DEFAULT_STORAGE_DIR = BASE_DIR.parent / "storage"

# STORAGE_DIR 支持通过环境变量覆盖。
# 测试会把这个环境变量指向临时目录，避免污染开发时真实使用的 storage。
STORAGE_DIR = Path(getenv("SLIDES_READER_STORAGE_DIR", str(DEFAULT_STORAGE_DIR))).resolve()

# DOCUMENT_STORAGE_DIR 是后端实际使用的 PDF 保存目录。
# PDF 上传会直接写入这里；PPT/PPTX 会先转换成 PDF 后再写入这里。
DOCUMENT_STORAGE_DIR = STORAGE_DIR / "documents"

# CONVERSION_TEMP_DIR 保存 PPT/PPTX 转 PDF 的临时源文件。
# 转换完成或失败后，路由层会尽量删除这些临时文件。
CONVERSION_TEMP_DIR = STORAGE_DIR / "conversion-tmp"

# PAGE_IMAGE_STORAGE_DIR 保存每页 PDF 渲染出的 PNG 截图。
# 这些截图既给前端展示，也给视觉模型输入使用。
PAGE_IMAGE_STORAGE_DIR = STORAGE_DIR / "pages"

# CHAT_ATTACHMENT_STORAGE_DIR 保存当前页问答里用户上传或粘贴的图片。
# 这些图片需要持久保存，刷新页面后历史会话仍然可以显示缩略图。
CHAT_ATTACHMENT_STORAGE_DIR = STORAGE_DIR / "chat-attachments"

# LIBREOFFICE_PROFILE_DIR 是 LibreOffice 命令行转换使用的独立 profile。
# 单独 profile 可以降低命令行转换和桌面 LibreOffice 实例抢配置锁的概率。
LIBREOFFICE_PROFILE_DIR = STORAGE_DIR / "libreoffice-profile"

# DATABASE_PATH 是 SQLite 数据库文件路径。
# SQLite 是本地文件数据库，适合当前第一版单用户应用。
DATABASE_PATH = STORAGE_DIR / "app.db"

# 下面三个默认 prompt 会在数据库没有保存配置时生效。
# 用户可以在 WebUI 里修改它们，修改后的值会保存到 app_settings 表。
DEFAULT_COURSE_SUMMARY_PROMPT = """你是一位经验丰富、讲解清晰的课程老师。请根据用户上传的 slides 内容，生成一份面向学生的课程导读。

请用 Markdown 输出，必须包含以下部分：

## 课程主题
用 2-4 句话说明这份 slides 主要讲什么。

## 适合的学习对象
说明适合哪些学生或学习阶段。

## 主要知识点
用项目符号列出 5-10 个重点。

## 推荐学习顺序
按学习路径说明应该如何阅读和理解这些 slides。

## 学完后应掌握的内容
列出学生学习完成后应能理解或完成的事情。

要求：
- 不要简单复制 slides 原文。
- 要像老师备课一样组织内容。
- 如果某些页面文字很少，也要根据标题、上下文和整体结构进行合理归纳。
"""

DEFAULT_LECTURE_NOTES_PROMPT = """你是一位经验丰富、讲解清晰的课程老师。请根据课程简介、当前页文字和当前页截图，为这一页 slides 生成课堂讲稿。

请用 Markdown 输出，必须包含以下部分：

## 本页核心观点
用 2-4 句话说明这一页在整堂课中的作用和重点。

## 老师讲解词
写出老师可以直接照着讲的自然口语化讲稿。

## 需要提醒学生注意的地方
列出学生容易忽略、误解或需要重点观察的内容。

## 与前后页面的衔接
说明这一页如何承接前面内容，并为后续内容做铺垫。

要求：
- 重点围绕当前页，不要写成整份文档的泛泛总结。
- 结合截图理解图表、布局、公式和视觉元素。
- 不要简单复制 slides 原文。
- 讲解要像老师上课，而不是普通摘要工具。
"""

DEFAULT_PAGE_CHAT_PROMPT = """你是一位经验丰富、讲解清晰的课程老师。学生正在阅读一页 slides，并会围绕当前页向你提问。

请根据课程简介、当前页文字、当前页讲稿和本页历史问答回答学生的问题。

回答要求：
- 重点围绕当前页，不要把回答扩展成整份文档的泛泛总结。
- 如果问题需要联系前后文，可以基于课程简介做必要补充，但要明确说明这是上下文补充。
- 用适合学生理解的中文解释概念、步骤和原因。
- 如果当前页材料不足以确定答案，要诚实说明不确定，并给出基于当前页的合理理解。
- 不要编造 slides 中没有依据的细节。
"""

DEFAULT_EXAM_GENERATION_PROMPT = """你是一位经验丰富的双语出题老师。请根据以下课件内容生成一份完整的期末测试卷。

## 语言要求

- 试卷题目（title、description、题干、选项）使用英文
- 答案解析（explanation）使用中文
- 答案（answer）保持原有形式：选择题为 A/B/C/D，填空题必须为纯数字

## 试卷结构

- 总分 100 分
- 题型只包含两种：
  - 单选题：4 个选项，答案为 A/B/C/D 之一
  - 数字填空题：答案必须是纯数字（整数或小数），expected_type 固定为 "number"
- 包含三个部分：
  - Section A：10 道单选题，每题 3 分，共 30 分
  - Section B：5 道数字填空题，每题 5 分，共 25 分
  - Section C：3 道综合应用题，每题 15 分，共 45 分（可以是单选题，也可以是数字填空题，或两者混合）
- 每道题必须紧密围绕课件中的知识点
- 每道题的答案解析用中文详细说明原因，必须包含：题目考查的核心概念、为什么正确答案是正确的、每个错误选项或常见错误思路错在哪里、与该知识点相关的延伸说明
- 每道题必须标注来源页码（source_page），即该知识点主要出现在课件第几页
- 每道题标注难度（difficulty）：easy / medium / hard
- 每道题标注知识点标签（knowledge_tag），用简短英文概括

## 输出格式

请严格按以下 JSON 格式输出，不要包含任何其他说明文字、markdown 代码块标记或注释。

{
  "title": "Final Exam Paper",
  "description": "This exam covers the key concepts from the lecture slides.",
  "total_score": 100,
  "sections": [
    {
      "name": "A",
      "title": "Multiple Choice Questions",
      "questions": [
        {
          "number": 1,
          "type": "choice",
          "score": 3,
          "content": "Question text in English",
          "options": ["Option A", "Option B", "Option C", "Option D"],
          "answer": "B",
          "explanation": "中文解析，并在末尾说明：相关知识点见课件第 X 页。",
          "source_page": 5,
          "expected_type": "text",
          "difficulty": "medium",
          "knowledge_tag": "data types"
        }
      ]
    },
    {
      "name": "B",
      "title": "Fill-in-the-Blank Questions",
      "questions": [
        {
          "number": 1,
          "type": "fill_in",
          "score": 5,
          "content": "Question text in English, use ______ for the blank.",
          "answer": "123",
          "explanation": "中文解析，并在末尾说明：相关知识点见课件第 X 页。",
          "source_page": 8,
          "expected_type": "number",
          "difficulty": "medium",
          "knowledge_tag": "array indexing"
        }
      ]
    },
    {
      "name": "C",
      "title": "Comprehensive Questions",
      "questions": [
        {
          "number": 1,
          "type": "choice",
          "score": 15,
          "content": "Question text in English",
          "options": ["Option A", "Option B", "Option C", "Option D"],
          "answer": "C",
          "explanation": "中文详细解析，并在末尾说明：相关知识点见课件第 X 页。",
          "source_page": 12,
          "expected_type": "text",
          "difficulty": "hard",
          "knowledge_tag": "pointer basics"
        }
      ]
    }
  ]
}

## 注意事项

- type 只能是 "choice" 或 "fill_in"
- 选择题 answer 必须是单个字母 A/B/C/D
- 填空题 answer 必须是纯数字字符串，不要带单位、符号、单词、变量名、函数名或解释文字
- 如果某个知识点的答案是符号、关键字、概念名或代码片段（例如 "%", "if", "for", "list"），必须改写成单选题，不允许生成 fill_in
- fill_in 题干必须询问可计算的数值结果、数量、索引、长度、分数、百分比或页内明确出现的数字
- expected_type：选择题填 "text"，填空题填 "number"
- source_page 必须是整数，表示课件页码
- 难度分布建议：easy 30%、medium 50%、hard 20%
"""

# LLM_DEFAULT_CONFIG 保存 LLM 配置默认值。
# 环境变量提供部署时默认值，数据库中的 WebUI 配置会覆盖这些值。
LLM_DEFAULT_CONFIG = {
    "base_url": getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
    "api_key": getenv("LLM_API_KEY", ""),
    "model": getenv("LLM_MODEL", "gpt-4.1-mini"),
    "timeout_seconds": getenv("LLM_TIMEOUT_SECONDS", "60"),
    "course_summary_prompt": getenv("COURSE_SUMMARY_PROMPT", DEFAULT_COURSE_SUMMARY_PROMPT),
    "lecture_notes_prompt": getenv("LECTURE_NOTES_PROMPT", DEFAULT_LECTURE_NOTES_PROMPT),
    "page_chat_prompt": getenv("PAGE_CHAT_PROMPT", DEFAULT_PAGE_CHAT_PROMPT),
    "exam_generation_prompt": getenv("EXAM_GENERATION_PROMPT", DEFAULT_EXAM_GENERATION_PROMPT),
}

# LLM_CONFIG_KEYS 限定可以保存到 app_settings 的配置项。
# 任何新增 LLM 配置都应该先加入这里，再开放给前端保存。
LLM_CONFIG_KEYS = {
    "base_url",
    "api_key",
    "model",
    "timeout_seconds",
    "course_summary_prompt",
    "lecture_notes_prompt",
    "page_chat_prompt",
    "exam_generation_prompt",
}

# COURSE_SUMMARY_INPUT_LIMIT 限制课程简介阶段发送给 LLM 的页面文字长度。
# 这是第一版的固定保护，避免长 PDF 把单次请求撑得过大。
COURSE_SUMMARY_INPUT_LIMIT = 12000

# PAGE_CHAT_HISTORY_LIMIT 限制当前页问答带入 prompt 的历史消息数量。
# 只带最近 20 条，可以避免长时间追问导致 prompt 过长。
PAGE_CHAT_HISTORY_LIMIT = 20

# PAGE_CHAT_RECENT_IMAGE_LIMIT 限制后续追问自动带入的历史图片数量。
# 新一轮用户刚上传的图片不受这个历史数量限制。
PAGE_CHAT_RECENT_IMAGE_LIMIT = 3

# PAGE_CHAT_MAX_ATTACHMENTS_PER_MESSAGE 限制单轮会话可上传的图片数量。
# 这个限制同时用于后端校验和前端交互提示。
PAGE_CHAT_MAX_ATTACHMENTS_PER_MESSAGE = 4

# PAGE_CHAT_MAX_ATTACHMENT_BYTES 限制单张会话图片大小。
# 10MB 对本地工具足够宽松，也能避免一次请求占用过多内存。
PAGE_CHAT_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

# 默认讲稿文字块坐标和尺寸。
# 当前版本使用阅读区像素坐标，与前端拖拽逻辑保持一致。
DEFAULT_NOTE_BLOCK_X = 24.0
DEFAULT_NOTE_BLOCK_Y = 24.0
DEFAULT_NOTE_BLOCK_WIDTH = 320.0
DEFAULT_NOTE_BLOCK_HEIGHT = 240.0

# 讲稿文字块服务端保存前的最小尺寸。
# 后端重复校验可以防止异常请求把文字块保存成不可见状态。
MIN_NOTE_BLOCK_WIDTH = 120.0
MIN_NOTE_BLOCK_HEIGHT = 80.0

# LECTURE_NOTES_GENERATION_LOCKS 保存每个文档的整份讲稿生成锁。
# 这个锁只在单进程内有效，后续生产化时应替换为任务队列或数据库锁。
LECTURE_NOTES_GENERATION_LOCKS: dict[str, threading.Lock] = {}

# LECTURE_NOTES_GENERATION_LOCKS_GUARD 保护上面的锁字典本身。
# 多个请求同时恢复同一文档时，需要避免创建出多把不同的锁。
LECTURE_NOTES_GENERATION_LOCKS_GUARD = threading.Lock()
