"""AI slides reader 后端入口文件。

这个文件实现当前阶段需要的最小后端能力：
1. 创建一个 FastAPI 应用。
2. 开放开发环境前端可以访问的 CORS 配置。
3. 提供 `/api/health` 健康检查接口。
4. 提供 PDF/PPT/PPTX 文件上传接口，并把内容统一保存为系统使用的 PDF。
5. 使用 SQLite 持久保存上传文档记录。
6. 使用 PyMuPDF 解析 PDF 页数、每页文字和每页截图。
7. 提供可在 WebUI 修改的 LLM 配置，并封装统一 LLMClient。
"""

import base64
import json
import math
import sqlite3
import subprocess
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from os import getenv
from pathlib import Path
from typing import Any
from uuid import uuid4

import pymupdf
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel


# BASE_DIR 表示 backend 目录的绝对路径。
# 使用绝对路径可以避免从不同工作目录启动后端时保存位置发生变化。
BASE_DIR = Path(__file__).resolve().parent

# DEFAULT_STORAGE_DIR 表示默认运行数据目录。
# 如果没有额外配置，上传文件和 SQLite 数据库都会保存到项目根目录下的 storage。
DEFAULT_STORAGE_DIR = BASE_DIR.parent / "storage"

# STORAGE_DIR 支持通过环境变量覆盖。
# 这能让测试使用临时目录，不影响开发时正在使用的 storage 数据。
STORAGE_DIR = Path(getenv("SLIDES_READER_STORAGE_DIR", str(DEFAULT_STORAGE_DIR))).resolve()

# DOCUMENT_STORAGE_DIR 是系统实际使用的 PDF 保存目录。
# 对 PDF 上传会直接保存到这里；对 PPT/PPTX 上传会先转换成 PDF 再保存到这里。
DOCUMENT_STORAGE_DIR = STORAGE_DIR / "documents"

# CONVERSION_TEMP_DIR 是 PPT/PPTX 上传后的临时转换目录。
# 原始 PPT/PPTX 只会短暂保存在这里，转换成 PDF 成功后会被删除。
CONVERSION_TEMP_DIR = STORAGE_DIR / "conversion-tmp"

# PAGE_IMAGE_STORAGE_DIR 是页面截图的本地保存目录。
# 每个 PDF 页面会渲染成一张 PNG 图片，供前端和后续 LLM 视觉输入使用。
PAGE_IMAGE_STORAGE_DIR = STORAGE_DIR / "pages"

# LIBREOFFICE_PROFILE_DIR 是后端调用 LibreOffice 转换文件时使用的独立用户配置目录。
# 这样可以降低命令行转换和用户桌面 LibreOffice 实例互相抢配置锁的概率。
LIBREOFFICE_PROFILE_DIR = STORAGE_DIR / "libreoffice-profile"

# DATABASE_PATH 是 SQLite 数据库文件路径。
# SQLite 是本地文件数据库，适合当前阶段的单用户本地应用。
DATABASE_PATH = STORAGE_DIR / "app.db"

# LECTURE_NOTES_GENERATION_LOCKS 保存每个文档的整份讲稿生成锁。
# 后台任务在同一进程内运行时，这个锁可以避免暂停后立刻继续造成两条整份生成任务并发写同一批页面。
LECTURE_NOTES_GENERATION_LOCKS: dict[str, threading.Lock] = {}

# LECTURE_NOTES_GENERATION_LOCKS_GUARD 保护上面的锁字典本身，避免多个请求同时为同一个文档创建不同锁。
LECTURE_NOTES_GENERATION_LOCKS_GUARD = threading.Lock()


# 创建 FastAPI 应用对象。
# FastAPI 应用对象可以理解为整个后端服务的核心入口，所有 API 都挂载在它上面。
app = FastAPI(
    title="Slides Reader API",
    description="AI slides 阅读与授课工具的后端 API。",
    version="0.1.0",
)


class RenameDocumentRequest(BaseModel):
    """重命名文档的请求体。

    属性：
        title：用户希望显示在文档列表里的新标题。
    """

    title: str


class LLMConfigUpdateRequest(BaseModel):
    """更新 LLM 配置的请求体。

    属性：
        base_url：OpenAI-compatible API 的服务地址。
        api_key：模型服务密钥；为 None 时表示不修改旧密钥。
        model：用于生成文本或图文回答的模型名称。
        timeout_seconds：请求模型服务时最多等待的秒数。
        course_summary_prompt：生成课程简介时使用的可编辑 prompt；为 None 时表示不修改旧 prompt。
        lecture_notes_prompt：生成逐页讲稿时使用的可编辑 prompt；为 None 时表示不修改旧 prompt。
        page_chat_prompt：当前页问答时使用的可编辑 prompt；为 None 时表示不修改旧 prompt。
    """

    base_url: str
    api_key: str | None = None
    model: str
    timeout_seconds: int
    course_summary_prompt: str | None = None
    lecture_notes_prompt: str | None = None
    page_chat_prompt: str | None = None


class LLMTestRequest(BaseModel):
    """测试 LLM 文本调用的请求体。

    属性：
        prompt：用于测试模型连接的一小段提示词。
    """

    prompt: str = "请用一句中文回复：LLM 配置测试成功。"


class PageChatRequest(BaseModel):
    """当前页问答接口的请求体。

    属性：
        question：用户围绕当前页 slides 输入的问题。
    """

    question: str


class NoteBlockPositionUpdateRequest(BaseModel):
    """更新讲稿文字块位置和尺寸的请求体。

    属性：
        x：文字块左上角距离阅读区左侧的像素距离。
        y：文字块左上角距离阅读区顶部的像素距离。
        width：文字块宽度，单位是像素。
        height：文字块高度，单位是像素。
    """

    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class LLMConfig:
    """后端内部使用的 LLM 配置对象。

    属性：
        base_url：OpenAI-compatible API 的服务地址。
        api_key：模型服务密钥。
        model：使用的模型名称。
        timeout_seconds：HTTP 请求超时时间，单位是秒。
        course_summary_prompt：生成课程简介时使用的 prompt。
        lecture_notes_prompt：生成逐页讲稿时使用的 prompt。
        page_chat_prompt：当前页问答时使用的 prompt。
    """

    base_url: str
    api_key: str
    model: str
    timeout_seconds: int
    course_summary_prompt: str
    lecture_notes_prompt: str
    page_chat_prompt: str


# LLM_DEFAULT_CONFIG 保存 LLM 配置的默认值。
# 这些值会优先从环境变量读取，随后可以被 WebUI 写入的 SQLite 配置覆盖。
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

LLM_DEFAULT_CONFIG = {
    "base_url": getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
    "api_key": getenv("LLM_API_KEY", ""),
    "model": getenv("LLM_MODEL", "gpt-4.1-mini"),
    "timeout_seconds": getenv("LLM_TIMEOUT_SECONDS", "60"),
    "course_summary_prompt": getenv(
        "COURSE_SUMMARY_PROMPT",
        DEFAULT_COURSE_SUMMARY_PROMPT,
    ),
    "lecture_notes_prompt": getenv(
        "LECTURE_NOTES_PROMPT",
        DEFAULT_LECTURE_NOTES_PROMPT,
    ),
    "page_chat_prompt": getenv(
        "PAGE_CHAT_PROMPT",
        DEFAULT_PAGE_CHAT_PROMPT,
    ),
}


# LLM_CONFIG_KEYS 限定当前任务允许保存和读取的 LLM 配置项。
# 后续如果新增温度、最大输出长度等配置，也应该先加入这里，再开放给 WebUI。
LLM_CONFIG_KEYS = {
    "base_url",
    "api_key",
    "model",
    "timeout_seconds",
    "course_summary_prompt",
    "lecture_notes_prompt",
    "page_chat_prompt",
}

# COURSE_SUMMARY_INPUT_LIMIT 是课程简介生成时最多发送给 LLM 的页面文本长度。
# 第一版使用固定值，避免长 PDF 让单次请求过大。
COURSE_SUMMARY_INPUT_LIMIT = 12000

# PAGE_CHAT_HISTORY_LIMIT 是当前页问答发送给 LLM 的历史消息上限。
# 第一版只取最近 20 条，避免长时间追问后 prompt 过长。
PAGE_CHAT_HISTORY_LIMIT = 20

# DEFAULT_NOTE_BLOCK_X/Y/WIDTH/HEIGHT 是讲稿文字块第一次创建时的默认阅读区坐标和尺寸。
# 第一版坐标直接使用像素，和前端 react-rnd 的位置模型保持一致。
DEFAULT_NOTE_BLOCK_X = 24.0
DEFAULT_NOTE_BLOCK_Y = 24.0
DEFAULT_NOTE_BLOCK_WIDTH = 320.0
DEFAULT_NOTE_BLOCK_HEIGHT = 240.0

# MIN_NOTE_BLOCK_WIDTH/HEIGHT 是服务端保存前的最小尺寸限制。
# 这样可以避免前端或异常请求把文字块缩放到完全不可见。
MIN_NOTE_BLOCK_WIDTH = 120.0
MIN_NOTE_BLOCK_HEIGHT = 80.0


def init_database() -> None:
    """初始化 SQLite 数据库、Document 表和 Page 表。

    返回值：
        None：这个函数只负责创建目录、表和兼容字段，不返回业务数据。
    """

    # 数据库文件位于 storage 目录下，所以要先确保 storage 目录存在。
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 使用 with 语句打开连接，可以在代码块结束时自动关闭数据库连接。
    with sqlite3.connect(DATABASE_PATH) as connection:
        # 创建 documents 表；IF NOT EXISTS 表示表已存在时不重复创建。
        # documents 表保存上传 slides 的基本信息，后续任务会继续围绕 document_id 扩展页面数据。
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                file_path TEXT NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        # 兼容任务 03 已经创建过的 documents 表。
        # SQLite 不支持直接用 IF NOT EXISTS 增加列，所以先读取已有列再决定是否 ALTER TABLE。
        document_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(documents)").fetchall()
        }
        if "error_message" not in document_columns:
            connection.execute("ALTER TABLE documents ADD COLUMN error_message TEXT")
        if "course_summary" not in document_columns:
            connection.execute("ALTER TABLE documents ADD COLUMN course_summary TEXT")
        if "course_summary_status" not in document_columns:
            connection.execute(
                "ALTER TABLE documents ADD COLUMN course_summary_status TEXT NOT NULL DEFAULT 'pending'"
            )
        if "course_summary_error" not in document_columns:
            connection.execute("ALTER TABLE documents ADD COLUMN course_summary_error TEXT")
        if "lecture_notes_paused" not in document_columns:
            connection.execute(
                "ALTER TABLE documents ADD COLUMN lecture_notes_paused INTEGER NOT NULL DEFAULT 0"
            )

        # pages 表保存 PDF 每一页的解析结果。
        # document_id 和 page_number 做唯一约束，避免同一文档同一页被重复插入。
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pages (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                text TEXT NOT NULL,
                image_path TEXT,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(document_id, page_number),
                FOREIGN KEY(document_id) REFERENCES documents(id)
            )
            """
        )
        # 兼容任务 04 已经创建过的 pages 表。
        # 任务 05 需要保存页面截图路径，因此旧数据库启动时要自动补充 image_path 字段。
        page_columns = {row[1] for row in connection.execute("PRAGMA table_info(pages)").fetchall()}
        if "image_path" not in page_columns:
            connection.execute("ALTER TABLE pages ADD COLUMN image_path TEXT")
        if "lecture_notes" not in page_columns:
            connection.execute("ALTER TABLE pages ADD COLUMN lecture_notes TEXT")
        if "lecture_notes_status" not in page_columns:
            connection.execute(
                "ALTER TABLE pages ADD COLUMN lecture_notes_status TEXT NOT NULL DEFAULT 'pending'"
            )
        if "lecture_notes_error" not in page_columns:
            connection.execute("ALTER TABLE pages ADD COLUMN lecture_notes_error TEXT")

        # note_blocks 表保存 PDF 阅读界面中可拖动的讲稿文字块。
        # page_id 使用 UNIQUE 约束，明确第一版每页只保留一个默认讲稿文字块。
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS note_blocks (
                id TEXT PRIMARY KEY,
                page_id TEXT NOT NULL,
                content TEXT NOT NULL,
                x REAL NOT NULL,
                y REAL NOT NULL,
                width REAL NOT NULL,
                height REAL NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(page_id),
                FOREIGN KEY(page_id) REFERENCES pages(id)
            )
            """
        )

        # chat_messages 表保存某一页 slides 下方的独立问答历史。
        # page_id 直接关联 pages 表，保证切换页面时可以只读取当前页自己的问答。
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                page_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(page_id) REFERENCES pages(id)
            )
            """
        )

        # app_settings 表用于保存可以通过 WebUI 修改的应用配置。
        # 当前任务先保存 LLM 配置，后续新增配置也可以复用这个 key-value 表。
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def get_database_connection() -> sqlite3.Connection:
    """创建一个 SQLite 数据库连接。

    返回值：
        sqlite3.Connection：已经设置好 row_factory 的数据库连接对象。
    """

    # row_factory 设置为 sqlite3.Row 后，可以像字典一样通过字段名读取查询结果。
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def read_app_settings() -> dict[str, str]:
    """读取应用配置表中的所有配置。

    返回值：
        dict[str, str]：以配置 key 为键、配置 value 为值的字典。
    """

    # 每次读取前确保表存在，避免测试或脚本直接调用配置接口时还没初始化数据库。
    init_database()

    with get_database_connection() as connection:
        rows = connection.execute("SELECT key, value FROM app_settings").fetchall()

    # SQLite 返回的是行对象，这里转换成普通字典，后续合并默认值更方便。
    return {row["key"]: row["value"] for row in rows}


def write_app_settings(next_settings: dict[str, str]) -> None:
    """把应用配置写入 app_settings 表。

    参数：
        next_settings：要写入的配置字典，key 必须是允许保存的配置项。

    返回值：
        None：这个函数只负责写数据库。
    """

    # 统一使用 UTC 时间记录更新时间，便于后续排查配置什么时候被修改。
    updated_at = datetime.now(UTC).isoformat()

    init_database()

    with get_database_connection() as connection:
        for key, value in next_settings.items():
            if key not in LLM_CONFIG_KEYS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"不支持的配置项：{key}",
                )

            connection.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, updated_at),
            )
        connection.commit()


def mask_secret(secret: str) -> str:
    """把密钥转换成前端可展示的掩码字符串。

    参数：
        secret：真实密钥字符串。

    返回值：
        str：不泄露完整密钥的掩码字符串。
    """

    # 没有配置密钥时返回空字符串，前端可以据此提示用户还没有配置。
    if not secret:
        return ""

    # 很短的密钥不展示首尾字符，避免掩码本身泄露太多信息。
    if len(secret) <= 8:
        return "********"

    # 较长密钥只展示开头和结尾，中间用星号代替。
    return f"{secret[:4]}{'*' * 8}{secret[-4:]}"


def normalize_base_url(base_url: str) -> str:
    """规范化 LLM 服务地址。

    参数：
        base_url：用户输入的 OpenAI-compatible API 服务地址。

    返回值：
        str：去掉首尾空白和末尾斜杠后的地址。
    """

    # 只做最小规范化，不强行补协议，避免把用户输入的错误地址悄悄变成另一个地址。
    return base_url.strip().rstrip("/")


def normalize_timeout_seconds(timeout_seconds: int | str) -> int:
    """校验并转换 LLM 请求超时时间。

    参数：
        timeout_seconds：用户或环境变量提供的超时时间。

    返回值：
        int：合法的超时时间，单位是秒。
    """

    try:
        normalized_timeout = int(timeout_seconds)
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LLM 请求超时时间必须是整数秒。",
        ) from error

    # 设置合理边界，避免用户填 0 导致请求立刻失败，或填特别大导致后端长时间卡住。
    if normalized_timeout < 5 or normalized_timeout > 300:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LLM 请求超时时间必须在 5 到 300 秒之间。",
        )

    return normalized_timeout


def get_llm_config() -> LLMConfig:
    """读取最终生效的 LLM 配置。

    返回值：
        LLMConfig：合并环境变量默认值和 WebUI 保存值后的配置对象。
    """

    # 默认值来自环境变量，数据库配置来自 WebUI；数据库配置优先级更高。
    stored_settings = read_app_settings()
    merged_settings = {**LLM_DEFAULT_CONFIG, **stored_settings}

    return LLMConfig(
        base_url=normalize_base_url(merged_settings["base_url"]),
        api_key=merged_settings["api_key"],
        model=merged_settings["model"].strip(),
        timeout_seconds=normalize_timeout_seconds(merged_settings["timeout_seconds"]),
        course_summary_prompt=merged_settings["course_summary_prompt"].strip(),
        lecture_notes_prompt=merged_settings["lecture_notes_prompt"].strip(),
        page_chat_prompt=merged_settings["page_chat_prompt"].strip(),
    )


def serialize_llm_config(config: LLMConfig) -> dict[str, str | int | bool]:
    """把 LLM 配置转换成可以返回给前端的字典。

    参数：
        config：后端内部使用的 LLM 配置对象。

    返回值：
        dict[str, str | int | bool]：隐藏真实 API Key 后的配置数据。
    """

    return {
        "base_url": config.base_url,
        "model": config.model,
        "timeout_seconds": config.timeout_seconds,
        "course_summary_prompt": config.course_summary_prompt,
        "lecture_notes_prompt": config.lecture_notes_prompt,
        "page_chat_prompt": config.page_chat_prompt,
        "api_key_configured": bool(config.api_key),
        "api_key_preview": mask_secret(config.api_key),
    }


def validate_llm_config(config: LLMConfig) -> None:
    """校验 LLM 配置是否足够发起请求。

    参数：
        config：需要校验的 LLM 配置。

    返回值：
        None：配置合法时不返回数据；配置缺失时抛出 HTTPException。
    """

    if not config.base_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先配置 LLM_BASE_URL。",
        )

    if not config.api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先配置 LLM_API_KEY。",
        )

    if not config.model:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先配置 LLM_MODEL。",
        )


def build_chat_completions_url(base_url: str) -> str:
    """根据 base_url 生成 OpenAI-compatible 的 chat completions 请求地址。

    参数：
        base_url：用户配置的模型服务基础地址。

    返回值：
        str：最终请求地址。
    """

    # 如果用户已经填到了 /chat/completions，就直接使用，兼容少数只暴露完整路径的服务。
    if base_url.endswith("/chat/completions"):
        return base_url

    # 常见 OpenAI-compatible 服务会把 base_url 配成 https://host/v1。
    return f"{base_url}/chat/completions"


def encode_image_as_data_url(image_path: Path) -> str:
    """把本地图片转换成 LLM 视觉接口常用的 data URL。

    参数：
        image_path：本地图片路径。

    返回值：
        str：形如 data:image/png;base64,... 的图片文本。
    """

    # 任务 05 生成的是 PNG，所以这里固定使用 image/png。
    encoded_image = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded_image}"


class LLMClient:
    """统一封装 OpenAI-compatible LLM 调用。

    这个类负责把项目内部的文本和图片输入转换成模型服务需要的 HTTP 请求。
    后续课程简介、逐页讲稿和当前页问答都应该调用这个类，而不是直接写请求逻辑。
    """

    def __init__(self, config: LLMConfig):
        """创建 LLMClient 实例。

        参数：
            config：当前生效的 LLM 配置。
        """

        self.config = config

    def complete_text(self, prompt: str) -> str:
        """发送纯文本提示词并返回模型文本回答。

        参数：
            prompt：要发送给模型的用户提示词。

        返回值：
            str：模型返回的文本内容。
        """

        messages = [
            {
                "role": "user",
                "content": prompt,
            }
        ]
        return self._send_chat_completion(messages)

    def complete_with_image(self, prompt: str, image_path: Path) -> str:
        """发送文本加页面截图，并返回模型文本回答。

        参数：
            prompt：要发送给模型的文字提示词。
            image_path：要发送给模型的本地 PNG 截图路径。

        返回值：
            str：模型返回的文本内容。
        """

        # OpenAI-compatible 视觉请求通常把 content 写成多个片段：文本片段和图片片段。
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": encode_image_as_data_url(image_path),
                        },
                    },
                ],
            }
        ]
        return self._send_chat_completion(messages)

    def _send_chat_completion(self, messages: list[dict[str, Any]]) -> str:
        """向 OpenAI-compatible chat completions 接口发送请求。

        参数：
            messages：符合 chat completions 格式的消息列表。

        返回值：
            str：模型返回的第一条文本回答。
        """

        validate_llm_config(self.config)

        payload = {
            "model": self.config.model,
            "messages": messages,
        }
        request_body = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            url=build_chat_completions_url(self.config.base_url),
            data=request_body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                # Accept 明确告诉模型服务，客户端期望收到 JSON 格式响应。
                # 一些 OpenAI-compatible 服务前面有网关或 WAF，缺少常见请求头时可能被误拦截。
                "Accept": "application/json",
                "Content-Type": "application/json",
                # User-Agent 用来标识当前客户端。MicuAPI 等服务可能会拒绝没有正常
                # User-Agent 的 Python 默认请求，并返回 HTTP 403 / error code 1010。
                "User-Agent": "SlidesReader/0.1 (+OpenAI-compatible client)",
            },
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.config.timeout_seconds,
            ) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            # HTTPError 代表服务端返回了 4xx 或 5xx，尽量读取响应体给用户更明确的错误。
            error_body = error.read().decode("utf-8", errors="replace")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LLM 服务返回错误：HTTP {error.code}，{error_body}",
            ) from error
        except urllib.error.URLError as error:
            # URLError 通常代表网络不可达、域名错误或连接失败。
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"无法连接 LLM 服务：{error.reason}",
            ) from error
        except TimeoutError as error:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="LLM 请求超时，请检查服务地址或调大超时时间。",
            ) from error

        try:
            data = json.loads(response_body)
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LLM 服务返回格式不符合 OpenAI-compatible chat completions：{response_body}",
            ) from error

        if not isinstance(content, str) or not content.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="LLM 服务返回了空回答。",
            )

        return content


def row_to_document(row: sqlite3.Row) -> dict[str, str | int | bool | None]:
    """把 SQLite 查询结果转换成前端可直接使用的字典。

    参数：
        row：SQLite 查询返回的一行 Document 数据。

    返回值：
        dict[str, str | int | bool | None]：包含文档 ID、标题、文件路径、状态、页数、错误信息和创建时间。
    """

    # 明确列出字段，可以避免把数据库内部字段或未来新增字段意外暴露给前端。
    return {
        "document_id": row["id"],
        "title": row["title"],
        "file_path": row["file_path"],
        "status": row["status"],
        "page_count": row["page_count"],
        "error_message": row["error_message"],
        "course_summary": row["course_summary"],
        "course_summary_status": row["course_summary_status"],
        "course_summary_error": row["course_summary_error"],
        "lecture_notes_paused": bool(row["lecture_notes_paused"]),
        "created_at": row["created_at"],
    }


def build_page_image_url(document_id: str, page_number: int) -> str:
    """生成页面截图的后端访问 URL。

    参数：
        document_id：页面所属文档 ID。
        page_number：从 1 开始的页码。

    返回值：
        str：前端或浏览器可以直接访问的页面截图接口路径。
    """

    # 只返回相对 API 路径，前端可以通过 Vite 代理或同源部署访问，不需要写死后端域名。
    return f"/api/documents/{document_id}/pages/{page_number}/image"


def row_to_note_block(row: sqlite3.Row) -> dict[str, str | float]:
    """把 SQLite 查询结果转换成讲稿文字块字典。

    参数：
        row：SQLite 查询返回的一行 note_blocks 数据。

    返回值：
        dict[str, str | float]：包含文字块 ID、所属页面、内容、坐标、尺寸和时间字段。
    """

    # 后端直接返回数字类型，前端 react-rnd 可以把这些值作为像素坐标和尺寸使用。
    return {
        "note_block_id": row["id"],
        "page_id": row["page_id"],
        "content": row["content"],
        "x": row["x"],
        "y": row["y"],
        "width": row["width"],
        "height": row["height"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def row_to_chat_message(row: sqlite3.Row) -> dict[str, str]:
    """把 SQLite 查询结果转换成前端使用的聊天消息字典。

    参数：
        row：SQLite 查询返回的一行 chat_messages 数据。

    返回值：
        dict[str, str]：包含消息 ID、页面 ID、角色、正文和创建时间。
    """

    # 数据库内部字段名 id 在前端容易和其他对象混淆，所以返回时使用 chat_message_id。
    return {
        "chat_message_id": row["id"],
        "page_id": row["page_id"],
        "role": row["role"],
        "content": row["content"],
        "created_at": row["created_at"],
    }


def list_chat_messages_for_page(page_id: str) -> list[dict[str, str]]:
    """读取某一页的全部问答历史。

    参数：
        page_id：需要读取聊天历史的页面 ID。

    返回值：
        list[dict[str, str]]：按创建时间升序排列的聊天消息列表。
    """

    with get_database_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, page_id, role, content, created_at
            FROM chat_messages
            WHERE page_id = ?
            ORDER BY created_at ASC
            """,
            (page_id,),
        ).fetchall()

    return [row_to_chat_message(row) for row in rows]


def list_chat_messages_for_pages(page_ids: list[str]) -> dict[str, list[dict[str, str]]]:
    """批量读取多个页面的问答历史，并按 page_id 分组。

    参数：
        page_ids：需要读取聊天历史的页面 ID 列表。

    返回值：
        dict[str, list[dict[str, str]]]：键是 page_id，值是该页的消息列表。
    """

    # 没有页面时直接返回空字典，避免拼出无效 SQL。
    if not page_ids:
        return {}

    placeholders = ",".join("?" for _ in page_ids)
    with get_database_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT id, page_id, role, content, created_at
            FROM chat_messages
            WHERE page_id IN ({placeholders})
            ORDER BY created_at ASC
            """,
            page_ids,
        ).fetchall()

    messages_by_page: dict[str, list[dict[str, str]]] = {page_id: [] for page_id in page_ids}
    for row in rows:
        messages_by_page.setdefault(row["page_id"], []).append(row_to_chat_message(row))

    return messages_by_page


def list_recent_chat_messages_for_prompt(page_id: str) -> list[dict[str, str]]:
    """读取构造问答 prompt 时使用的最近聊天历史。

    参数：
        page_id：需要读取聊天历史的页面 ID。

    返回值：
        list[dict[str, str]]：最多 20 条、按创建时间升序排列的聊天消息。
    """

    with get_database_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, page_id, role, content, created_at
            FROM (
                SELECT id, page_id, role, content, created_at
                FROM chat_messages
                WHERE page_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            )
            ORDER BY created_at ASC
            """,
            (page_id, PAGE_CHAT_HISTORY_LIMIT),
        ).fetchall()

    return [row_to_chat_message(row) for row in rows]


def create_chat_message(page_id: str, role: str, content: str) -> dict[str, str]:
    """向 chat_messages 表写入一条问答消息。

    参数：
        page_id：消息所属的页面 ID。
        role：消息角色，只允许 user 或 assistant。
        content：消息正文。

    返回值：
        dict[str, str]：刚写入数据库的聊天消息。
    """

    if role not in {"user", "assistant"}:
        raise ValueError(f"不支持的聊天消息角色：{role}")

    message_id = str(uuid4())
    created_at = datetime.now(UTC).isoformat()

    with get_database_connection() as connection:
        connection.execute(
            """
            INSERT INTO chat_messages (id, page_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (message_id, page_id, role, content, created_at),
        )
        connection.commit()

        row = connection.execute(
            """
            SELECT id, page_id, role, content, created_at
            FROM chat_messages
            WHERE id = ?
            """,
            (message_id,),
        ).fetchone()

    return row_to_chat_message(row)


def row_to_page(row: sqlite3.Row) -> dict[str, Any]:
    """把 SQLite 查询结果转换成页面字典。

    参数：
        row：SQLite 查询返回的一行 Page 数据。

    返回值：
        dict[str, Any]：包含页面 ID、页码、文字、截图信息、讲稿状态和讲稿文字块。
    """

    # image_path 是本地文件路径，image_url 是前端更适合使用的 HTTP 访问入口。
    image_path = row["image_path"]

    # 页面文字可能很长，但当前任务需要返回它，方便前端或后续任务验证解析结果。
    # 如果查询结果中带有 note_blocks 字段，就把它整理成嵌套对象；没有则返回 null。
    note_block = None
    if "note_block_id" in row.keys() and row["note_block_id"] is not None:
        note_block = {
            "note_block_id": row["note_block_id"],
            "page_id": row["note_block_page_id"],
            "content": row["note_block_content"],
            "x": row["note_block_x"],
            "y": row["note_block_y"],
            "width": row["note_block_width"],
            "height": row["note_block_height"],
            "created_at": row["note_block_created_at"],
            "updated_at": row["note_block_updated_at"],
        }

    return {
        "page_id": row["id"],
        "document_id": row["document_id"],
        "page_number": row["page_number"],
        "text": row["text"],
        "image_path": image_path,
        "image_url": (
            build_page_image_url(row["document_id"], row["page_number"])
            if image_path
            else None
        ),
        "status": row["status"],
        "error_message": row["error_message"],
        "lecture_notes": row["lecture_notes"],
        "lecture_notes_status": row["lecture_notes_status"],
        "lecture_notes_error": row["lecture_notes_error"],
        "note_block": note_block,
        "chat_messages": [],
        "created_at": row["created_at"],
    }


def ensure_note_block_for_ready_page(connection: sqlite3.Connection, page: sqlite3.Row) -> None:
    """为已经生成讲稿的页面补充默认讲稿文字块。

    参数：
        connection：当前正在使用的 SQLite 连接。
        page：包含页面 ID、讲稿正文和讲稿状态的页面行。

    返回值：
        None：需要创建时直接写入 note_blocks 表。
    """

    # 只有成功生成讲稿且正文非空的页面才需要讲稿文字块。
    if page["lecture_notes_status"] != "ready" or not page["lecture_notes"]:
        return

    # 每页第一版只有一个文字块；如果已经存在，就不覆盖用户保存过的位置。
    existing_note_block = connection.execute(
        "SELECT id FROM note_blocks WHERE page_id = ?",
        (page["id"],),
    ).fetchone()
    if existing_note_block is not None:
        return

    now = datetime.now(UTC).isoformat()
    connection.execute(
        """
        INSERT INTO note_blocks (
            id,
            page_id,
            content,
            x,
            y,
            width,
            height,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()),
            page["id"],
            page["lecture_notes"],
            DEFAULT_NOTE_BLOCK_X,
            DEFAULT_NOTE_BLOCK_Y,
            DEFAULT_NOTE_BLOCK_WIDTH,
            DEFAULT_NOTE_BLOCK_HEIGHT,
            now,
            now,
        ),
    )


def sync_note_block_content_for_page(
    connection: sqlite3.Connection,
    document_id: str,
    page_number: int,
    lecture_notes: str,
) -> None:
    """讲稿生成成功后同步讲稿文字块内容，并保留已有位置和尺寸。

    参数：
        connection：当前正在使用的 SQLite 连接。
        document_id：页面所属文档 ID。
        page_number：从 1 开始的页码。
        lecture_notes：最新生成成功的讲稿正文。

    返回值：
        None：这个函数只负责写数据库。
    """

    # 先根据文档和页码拿到稳定的 page_id，note_blocks 表只和 pages 表直接关联。
    page = connection.execute(
        """
        SELECT id
        FROM pages
        WHERE document_id = ? AND page_number = ?
        """,
        (document_id, page_number),
    ).fetchone()
    if page is None:
        return

    now = datetime.now(UTC).isoformat()
    existing_note_block = connection.execute(
        "SELECT id FROM note_blocks WHERE page_id = ?",
        (page["id"],),
    ).fetchone()

    if existing_note_block is None:
        # 没有旧文字块时创建默认位置，保证刚生成讲稿后进入阅读器就能看到内容。
        connection.execute(
            """
            INSERT INTO note_blocks (
                id,
                page_id,
                content,
                x,
                y,
                width,
                height,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                page["id"],
                lecture_notes,
                DEFAULT_NOTE_BLOCK_X,
                DEFAULT_NOTE_BLOCK_Y,
                DEFAULT_NOTE_BLOCK_WIDTH,
                DEFAULT_NOTE_BLOCK_HEIGHT,
                now,
                now,
            ),
        )
        return

    # 已有文字块时只更新正文和更新时间，避免覆盖用户拖动保存的位置。
    connection.execute(
        """
        UPDATE note_blocks
        SET content = ?, updated_at = ?
        WHERE page_id = ?
        """,
        (lecture_notes, now, page["id"]),
    )


def validate_note_block_position(request: NoteBlockPositionUpdateRequest) -> None:
    """校验讲稿文字块位置和尺寸是否可以保存。

    参数：
        request：前端提交的位置和尺寸请求体。

    返回值：
        None：校验失败时直接抛出 HTTPException。
    """

    values = [request.x, request.y, request.width, request.height]
    if not all(math.isfinite(value) for value in values):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文字块位置和尺寸必须是有效数字。",
        )

    if request.width < MIN_NOTE_BLOCK_WIDTH or request.height < MIN_NOTE_BLOCK_HEIGHT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文字块尺寸过小，无法保存。",
        )


def get_document_with_page_count(document_id: str) -> dict[str, str | int | None] | None:
    """查询单个文档，并附带页面数量。

    参数：
        document_id：要查询的文档 ID。

    返回值：
        dict[str, str | int | None] | None：找到文档时返回文档字典，找不到时返回 None。
    """

    # 这个函数复用文档列表的 JOIN 逻辑，保证 PATCH 返回结构和 GET /api/documents 一致。
    with get_database_connection() as connection:
        row = connection.execute(
            """
            SELECT
                documents.id,
                documents.title,
                documents.file_path,
                documents.status,
                documents.error_message,
                documents.course_summary,
                documents.course_summary_status,
                documents.course_summary_error,
                documents.lecture_notes_paused,
                documents.created_at,
                COUNT(pages.id) AS page_count
            FROM documents
            LEFT JOIN pages ON pages.document_id = documents.id
            WHERE documents.id = ?
            GROUP BY documents.id
            """,
            (document_id,),
        ).fetchone()

    if row is None:
        return None

    return row_to_document(row)


def resolve_document_file_path(file_path: str) -> Path:
    """把数据库中的文件路径解析为安全的本地 PDF 路径。

    参数：
        file_path：documents.file_path 中保存的路径字符串。

    返回值：
        Path：解析后的绝对路径。
    """

    # resolve 会把相对路径、.. 等路径片段解析成绝对路径，方便后续做目录边界检查。
    return Path(file_path).resolve()


def ensure_document_file_is_safe(file_path: Path) -> None:
    """确认待读取或待删除的 PDF 文件位于 DOCUMENT_STORAGE_DIR 内。

    参数：
        file_path：准备读取或删除的 PDF 文件绝对路径。

    返回值：
        None：路径安全时不返回数据，路径不安全时直接抛出 HTTPException。
    """

    # 读取或删除文件前必须确认路径边界，避免数据库中的异常 file_path 指向项目外文件。
    storage_root = DOCUMENT_STORAGE_DIR.resolve()

    try:
        file_path.relative_to(storage_root)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="文档文件路径不在允许访问的 storage/documents 目录内，已拒绝访问文件。",
        ) from error


def resolve_page_image_path(image_path: str) -> Path:
    """把数据库中的截图路径解析为本地 PNG 路径。

    参数：
        image_path：pages.image_path 中保存的路径字符串。

    返回值：
        Path：解析后的绝对路径。
    """

    # resolve 会把路径转换成绝对路径，后续才能可靠判断它是否位于 storage/pages 内。
    return Path(image_path).resolve()


def ensure_page_image_file_is_safe(image_path: Path) -> None:
    """确认页面截图文件位于 PAGE_IMAGE_STORAGE_DIR 内。

    参数：
        image_path：准备读取或删除的页面截图绝对路径。

    返回值：
        None：路径安全时不返回数据，路径不安全时直接抛出 HTTPException。
    """

    # 图片接口会读取本地文件，删除文档也会删除截图；两种场景都必须做目录边界检查。
    storage_root = PAGE_IMAGE_STORAGE_DIR.resolve()

    try:
        image_path.relative_to(storage_root)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="页面截图路径不在允许访问的 storage/pages 目录内，已拒绝操作。",
        ) from error


def update_document_status(
    document_id: str,
    document_status: str,
    error_message: str | None = None,
) -> None:
    """更新文档处理状态。

    参数：
        document_id：需要更新的文档 ID。
        document_status：新的文档状态，例如 processing、ready 或 failed。
        error_message：失败时保存的错误信息，成功时通常为 None。

    返回值：
        None：这个函数只负责写数据库。
    """

    # 状态更新集中在一个函数里，避免上传流程和解析流程重复写 SQL。
    with get_database_connection() as connection:
        connection.execute(
            """
            UPDATE documents
            SET status = ?, error_message = ?
            WHERE id = ?
            """,
            (document_status, error_message, document_id),
        )
        connection.commit()


def update_course_summary_status(
    document_id: str,
    summary_status: str,
    course_summary: str | None = None,
    error_message: str | None = None,
) -> None:
    """更新文档课程简介生成状态和结果。

    参数：
        document_id：需要更新课程简介状态的文档 ID。
        summary_status：新的课程简介状态，例如 processing、ready 或 failed。
        course_summary：生成成功时保存的 Markdown 简介文本；为 None 时保留已有简介文本。
        error_message：生成失败时保存的错误信息。

    返回值：
        None：这个函数只负责写数据库。
    """

    with get_database_connection() as connection:
        if course_summary is None:
            # 简介生成中或生成失败时，只更新状态和错误信息，避免重新生成失败后丢失旧简介。
            connection.execute(
                """
                UPDATE documents
                SET
                    course_summary_status = ?,
                    course_summary_error = ?
                WHERE id = ?
                """,
                (summary_status, error_message, document_id),
            )
        else:
            # 只有 LLM 成功返回新简介时，才覆盖 course_summary 文本。
            connection.execute(
                """
                UPDATE documents
                SET
                    course_summary_status = ?,
                    course_summary = ?,
                    course_summary_error = ?
                WHERE id = ?
                """,
                (summary_status, course_summary, error_message, document_id),
            )
        connection.commit()


def update_page_lecture_notes_status(
    document_id: str,
    page_number: int,
    lecture_notes_status: str,
    lecture_notes: str | None = None,
    error_message: str | None = None,
) -> None:
    """更新单页讲稿生成状态和结果。

    参数：
        document_id：页面所属文档 ID。
        page_number：从 1 开始的页码。
        lecture_notes_status：新的讲稿状态，例如 processing、ready 或 failed。
        lecture_notes：生成成功时保存的 Markdown 讲稿文本；为 None 时保留旧讲稿。
        error_message：生成失败时保存的错误信息。

    返回值：
        None：这个函数只负责写数据库。
    """

    with get_database_connection() as connection:
        if lecture_notes is None:
            # 生成中或失败时不清空旧讲稿，避免重试失败后丢失已经可用的内容。
            connection.execute(
                """
                UPDATE pages
                SET
                    lecture_notes_status = ?,
                    lecture_notes_error = ?
                WHERE document_id = ? AND page_number = ?
                """,
                (lecture_notes_status, error_message, document_id, page_number),
            )
        else:
            # 只有模型成功返回新讲稿时，才覆盖 lecture_notes 正文。
            connection.execute(
                """
                UPDATE pages
                SET
                    lecture_notes_status = ?,
                    lecture_notes = ?,
                    lecture_notes_error = ?
                WHERE document_id = ? AND page_number = ?
                """,
                (lecture_notes_status, lecture_notes, error_message, document_id, page_number),
            )
            sync_note_block_content_for_page(
                connection=connection,
                document_id=document_id,
                page_number=page_number,
                lecture_notes=lecture_notes,
            )
        connection.commit()


def get_lecture_notes_generation_lock(document_id: str) -> threading.Lock:
    """获取某个文档的整份讲稿生成锁。

    参数：
        document_id：需要生成逐页讲稿的文档 ID。

    返回值：
        threading.Lock：该文档在当前后端进程内共用的生成锁。
    """

    # 锁字典本身也需要保护，否则两个请求可能同时创建两把不同的锁。
    with LECTURE_NOTES_GENERATION_LOCKS_GUARD:
        if document_id not in LECTURE_NOTES_GENERATION_LOCKS:
            LECTURE_NOTES_GENERATION_LOCKS[document_id] = threading.Lock()
        return LECTURE_NOTES_GENERATION_LOCKS[document_id]


def set_lecture_notes_paused(document_id: str, paused: bool) -> None:
    """更新某个文档的逐页讲稿暂停状态。

    参数：
        document_id：需要更新暂停状态的文档 ID。
        paused：True 表示暂停后续页面生成，False 表示允许继续生成。

    返回值：
        None：这个函数只负责写数据库。
    """

    with get_database_connection() as connection:
        connection.execute(
            """
            UPDATE documents
            SET lecture_notes_paused = ?
            WHERE id = ?
            """,
            (1 if paused else 0, document_id),
        )
        connection.commit()


def is_lecture_notes_paused(document_id: str) -> bool:
    """读取某个文档是否已经暂停逐页讲稿生成。

    参数：
        document_id：需要检查暂停状态的文档 ID。

    返回值：
        bool：True 表示暂停，False 表示未暂停或文档不存在。
    """

    with get_database_connection() as connection:
        document = connection.execute(
            "SELECT lecture_notes_paused FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()

    return bool(document["lecture_notes_paused"]) if document is not None else False


def reset_document_lecture_notes_status(document_id: str) -> None:
    """把指定文档的所有页面讲稿状态重置为等待生成。

    参数：
        document_id：需要重置讲稿状态的文档 ID。

    返回值：
        None：这个函数只负责写数据库。
    """

    with get_database_connection() as connection:
        # 重新生成全部讲稿是一次明确的新生成任务，因此需要清除之前的暂停状态。
        connection.execute(
            """
            UPDATE documents
            SET lecture_notes_paused = 0
            WHERE id = ?
            """,
            (document_id,),
        )
        connection.execute(
            """
            UPDATE pages
            SET
                lecture_notes_status = 'pending',
                lecture_notes_error = NULL
            WHERE document_id = ?
            """,
            (document_id,),
        )
        connection.commit()


def create_page_record(
    document_id: str,
    page_number: int,
    text: str,
    image_path: Path | None,
    page_status: str,
    error_message: str | None = None,
) -> None:
    """创建或替换单页解析记录。

    参数：
        document_id：页面所属文档 ID。
        page_number：从 1 开始的页码。
        text：当前页提取出的文字；空白页使用空字符串。
        image_path：当前页 PNG 截图路径；截图失败时使用 None。
        page_status：页面解析状态，例如 ready 或 failed。
        error_message：单页解析失败时保存的错误信息。

    返回值：
        None：这个函数只负责写数据库。
    """

    # 每页记录有自己的 ID，方便后续任务把讲稿、截图或问答关联到具体页面。
    page_id = str(uuid4())
    created_at = datetime.now(UTC).isoformat()

    with get_database_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO pages (
                id,
                document_id,
                page_number,
                text,
                image_path,
                status,
                error_message,
                lecture_notes,
                lecture_notes_status,
                lecture_notes_error,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                page_id,
                document_id,
                page_number,
                text,
                str(image_path) if image_path is not None else None,
                page_status,
                error_message,
                None,
                "pending",
                None,
                created_at,
            ),
        )
        connection.commit()


def build_page_image_path(document_id: str, page_number: int) -> Path:
    """生成某一页截图应保存到的本地路径。

    参数：
        document_id：页面所属文档 ID。
        page_number：从 1 开始的页码。

    返回值：
        Path：当前页 PNG 截图的目标保存路径。
    """

    # 文件名同时包含文档 ID 和页码，可以避免不同 PDF 的同页图片互相覆盖。
    return PAGE_IMAGE_STORAGE_DIR / f"{document_id}-page-{page_number}.png"


def render_page_image(page: pymupdf.Page, document_id: str, page_number: int) -> Path:
    """把 PDF 单页渲染成 PNG 图片并保存到本地。

    参数：
        page：PyMuPDF 读取出的单页对象。
        document_id：页面所属文档 ID。
        page_number：从 1 开始的页码。

    返回值：
        Path：保存成功后的 PNG 图片路径。
    """

    # 确保截图目录存在；parents=True 表示父目录不存在时一起创建。
    PAGE_IMAGE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    # Matrix(2, 2) 表示横向和纵向都放大 2 倍渲染，第一版在清晰度和体积之间取中等值。
    render_matrix = pymupdf.Matrix(2, 2)

    # get_pixmap 会把 PDF 页面渲染成内存里的像素图，随后可以保存为 PNG。
    pixmap = page.get_pixmap(matrix=render_matrix)

    # 目标文件名由 document_id 和页码决定，保证页面截图和 PDF 页码一一对应。
    image_path = build_page_image_path(document_id=document_id, page_number=page_number)

    # save 会把像素图写成 PNG 文件；PyMuPDF 会根据后缀识别保存格式。
    pixmap.save(image_path)

    return image_path


def build_course_summary_input(document_id: str) -> tuple[dict[str, str | int | None], str, bool]:
    """读取文档页面文字，并整理成课程简介生成输入。

    参数：
        document_id：需要生成课程简介的文档 ID。

    返回值：
        tuple[dict[str, str | int | None], str, bool]：文档信息、整理后的页面文本、是否发生截断。
    """

    with get_database_connection() as connection:
        document_row = connection.execute(
            """
            SELECT
                documents.id,
                documents.title,
                documents.file_path,
                documents.status,
                documents.error_message,
                documents.course_summary,
                documents.course_summary_status,
                documents.course_summary_error,
                documents.lecture_notes_paused,
                documents.created_at,
                COUNT(pages.id) AS page_count
            FROM documents
            LEFT JOIN pages ON pages.document_id = documents.id
            WHERE documents.id = ?
            GROUP BY documents.id
            """,
            (document_id,),
        ).fetchone()

        if document_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="没有找到对应的文档。",
            )

        page_rows = connection.execute(
            """
            SELECT page_number, text
            FROM pages
            WHERE document_id = ?
            ORDER BY page_number ASC
            """,
            (document_id,),
        ).fetchall()

    page_text_blocks: list[str] = []
    for row in page_rows:
        page_text = row["text"].strip() if row["text"] else "（本页没有可提取文字）"
        page_text_blocks.append(f"第 {row['page_number']} 页：\n{page_text}")

    full_pages_text = "\n\n".join(page_text_blocks)
    was_truncated = len(full_pages_text) > COURSE_SUMMARY_INPUT_LIMIT
    if was_truncated:
        full_pages_text = full_pages_text[:COURSE_SUMMARY_INPUT_LIMIT]

    return row_to_document(document_row), full_pages_text, was_truncated


def build_course_summary_prompt(
    document: dict[str, str | int | None],
    pages_text: str,
    was_truncated: bool,
) -> str:
    """构造发送给 LLM 的课程简介生成 prompt。

    参数：
        document：文档基本信息。
        pages_text：已经整理并可能截断过的页面文字。
        was_truncated：页面文字是否因为过长发生截断。

    返回值：
        str：完整 prompt 文本。
    """

    llm_config = get_llm_config()
    truncation_note = (
        "注意：由于文档较长，下面的页面文字已按 12000 字符上限截断。请基于已提供内容生成课程导读。"
        if was_truncated
        else "下面包含当前文档全部已提取页面文字。"
    )

    return f"""{llm_config.course_summary_prompt}

文档标题：{document["title"]}
总页数：{document["page_count"]}
{truncation_note}

页面文字：
{pages_text}
"""


def build_lecture_notes_prompt(
    document: sqlite3.Row,
    page: sqlite3.Row,
) -> str:
    """构造发送给 LLM 的单页讲稿生成 prompt。

    参数：
        document：包含文档标题、页数和课程简介的数据库行。
        page：包含当前页页码和页面文字的数据库行。

    返回值：
        str：完整 prompt 文本。
    """

    llm_config = get_llm_config()
    page_text = page["text"].strip() if page["text"] else "（本页没有可提取文字）"

    return f"""{llm_config.lecture_notes_prompt}

文档标题：{document["title"]}
总页数：{document["page_count"]}
当前页码：第 {page["page_number"]} 页

课程简介：
{document["course_summary"]}

当前页提取文字：
{page_text}
"""


def get_page_context_for_chat(page_id: str) -> sqlite3.Row:
    """读取当前页问答需要的页面、文档和讲稿上下文。

    参数：
        page_id：用户正在提问的页面 ID。

    返回值：
        sqlite3.Row：包含页面文字、讲稿、文档标题和课程简介的数据行。
    """

    with get_database_connection() as connection:
        page_context = connection.execute(
            """
            SELECT
                pages.id AS page_id,
                pages.document_id,
                pages.page_number,
                pages.text,
                pages.lecture_notes,
                pages.lecture_notes_status,
                documents.title AS document_title,
                documents.course_summary,
                documents.course_summary_status
            FROM pages
            INNER JOIN documents ON documents.id = pages.document_id
            WHERE pages.id = ?
            """,
            (page_id,),
        ).fetchone()

    if page_context is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的页面，无法进行当前页问答。",
        )

    return page_context


def format_chat_history_for_prompt(messages: list[dict[str, str]]) -> str:
    """把当前页历史问答整理成适合放入 prompt 的文本。

    参数：
        messages：当前页最近的聊天消息列表。

    返回值：
        str：带角色标签的历史问答文本。
    """

    if not messages:
        return "（本页还没有历史问答）"

    role_labels = {
        "user": "学生",
        "assistant": "AI 老师",
    }
    history_lines: list[str] = []
    for message in messages:
        role_label = role_labels.get(message["role"], message["role"])
        history_lines.append(f"{role_label}：{message['content']}")

    return "\n\n".join(history_lines)


def build_page_chat_prompt(
    page_context: sqlite3.Row,
    history_messages: list[dict[str, str]],
    question: str,
) -> str:
    """构造当前页问答发送给 LLM 的 prompt。

    参数：
        page_context：当前页、所属文档和课程简介上下文。
        history_messages：当前页最近的问答历史。
        question：用户最新提交的问题。

    返回值：
        str：完整的当前页问答 prompt 文本。
    """

    llm_config = get_llm_config()
    page_text = page_context["text"].strip() if page_context["text"] else "（本页没有可提取文字）"
    lecture_notes = (
        page_context["lecture_notes"].strip()
        if page_context["lecture_notes"]
        else "（本页讲稿尚未生成或为空）"
    )
    course_summary = (
        page_context["course_summary"].strip()
        if page_context["course_summary"]
        else "（课程简介尚未生成或为空）"
    )
    chat_history = format_chat_history_for_prompt(history_messages)

    return f"""{llm_config.page_chat_prompt}

文档标题：{page_context["document_title"]}
当前页码：第 {page_context["page_number"]} 页

课程简介：
{course_summary}

当前页提取文字：
{page_text}

当前页讲稿：
{lecture_notes}

当前页最近 {PAGE_CHAT_HISTORY_LIMIT} 条历史问答：
{chat_history}

学生最新问题：
{question}
"""


def get_document_ready_for_lecture_notes(document_id: str) -> sqlite3.Row:
    """读取可以生成逐页讲稿的文档记录。

    参数：
        document_id：需要生成讲稿的文档 ID。

    返回值：
        sqlite3.Row：包含课程简介和总页数的文档行。
    """

    with get_database_connection() as connection:
        document = connection.execute(
            """
            SELECT
                documents.id,
                documents.title,
                documents.course_summary,
                documents.course_summary_status,
                COUNT(pages.id) AS page_count
            FROM documents
            LEFT JOIN pages ON pages.document_id = documents.id
            WHERE documents.id = ?
            GROUP BY documents.id
            """,
            (document_id,),
        ).fetchone()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的文档。",
        )

    if document["course_summary_status"] != "ready" or not document["course_summary"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="课程简介尚未生成成功，无法生成逐页讲稿。",
        )

    if document["page_count"] == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前文档还没有页面记录，无法生成逐页讲稿。",
        )

    return document


def list_pages_for_lecture_notes(
    document_id: str,
    only_unfinished: bool = False,
) -> list[sqlite3.Row]:
    """读取指定文档的所有页面，供逐页讲稿生成使用。

    参数：
        document_id：需要读取页面的文档 ID。
        only_unfinished：为 True 时只读取还没有成功生成讲稿的页面。

    返回值：
        list[sqlite3.Row]：按页码升序排列的页面列表。
    """

    lecture_notes_filter = ""
    if only_unfinished:
        # 继续生成时不覆盖 ready 页面，只接管 pending、failed 和异常残留 processing 页面。
        lecture_notes_filter = "AND lecture_notes_status != 'ready'"

    with get_database_connection() as connection:
        return connection.execute(
            f"""
            SELECT
                id,
                document_id,
                page_number,
                text,
                image_path,
                status,
                error_message,
                lecture_notes,
                lecture_notes_status,
                lecture_notes_error,
                created_at
            FROM pages
            WHERE document_id = ?
            {lecture_notes_filter}
            ORDER BY page_number ASC
            """,
            (document_id,),
        ).fetchall()


def get_page_for_lecture_notes(document_id: str, page_number: int) -> sqlite3.Row:
    """读取指定页面，供单页讲稿生成使用。

    参数：
        document_id：页面所属文档 ID。
        page_number：从 1 开始的页码。

    返回值：
        sqlite3.Row：页面记录。
    """

    if page_number < 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的页面。",
        )

    with get_database_connection() as connection:
        page = connection.execute(
            """
            SELECT
                id,
                document_id,
                page_number,
                text,
                image_path,
                status,
                error_message,
                lecture_notes,
                lecture_notes_status,
                lecture_notes_error,
                created_at
            FROM pages
            WHERE document_id = ? AND page_number = ?
            """,
            (document_id, page_number),
        ).fetchone()

    if page is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的页面。",
        )

    return page


def get_page_for_lecture_notes_by_id(page_id: str) -> sqlite3.Row:
    """通过 page_id 读取指定页面，供任务 12 的单页重试接口使用。

    参数：
        page_id：页面记录的唯一 ID。

    返回值：
        sqlite3.Row：页面记录。
    """

    with get_database_connection() as connection:
        page = connection.execute(
            """
            SELECT
                id,
                document_id,
                page_number,
                text,
                image_path,
                status,
                error_message,
                lecture_notes,
                lecture_notes_status,
                lecture_notes_error,
                created_at
            FROM pages
            WHERE id = ?
            """,
            (page_id,),
        ).fetchone()

    if page is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的页面。",
        )

    return page


def generate_single_page_lecture_notes(
    document: sqlite3.Row,
    page: sqlite3.Row,
) -> None:
    """为单页生成讲稿，并把结果写入数据库。

    参数：
        document：已确认课程简介 ready 的文档行。
        page：需要生成讲稿的页面行。

    返回值：
        None：生成结果会写入 pages 表。
    """

    document_id = document["id"]
    page_number = page["page_number"]

    try:
        update_page_lecture_notes_status(
            document_id=document_id,
            page_number=page_number,
            lecture_notes_status="processing",
            lecture_notes=None,
            error_message=None,
        )

        if page["status"] != "ready":
            raise ValueError(page["error_message"] or "当前页面解析失败，无法生成讲稿。")

        if not page["image_path"]:
            raise ValueError("当前页面还没有生成截图，无法生成讲稿。")

        image_path = resolve_page_image_path(page["image_path"])
        ensure_page_image_file_is_safe(image_path)
        if not image_path.exists():
            raise ValueError("页面截图文件不存在，可能已被手动删除。")

        prompt = build_lecture_notes_prompt(document=document, page=page)
        client = LLMClient(get_llm_config())
        lecture_notes = client.complete_with_image(prompt=prompt, image_path=image_path)

        update_page_lecture_notes_status(
            document_id=document_id,
            page_number=page_number,
            lecture_notes_status="ready",
            lecture_notes=lecture_notes,
            error_message=None,
        )
    except Exception as error:
        update_page_lecture_notes_status(
            document_id=document_id,
            page_number=page_number,
            lecture_notes_status="failed",
            lecture_notes=None,
            error_message=f"逐页讲稿生成失败：{error}",
        )


def generate_document_lecture_notes(document_id: str) -> None:
    """按页码顺序为整份文档生成逐页讲稿。

    参数：
        document_id：需要生成逐页讲稿的文档 ID。

    返回值：
        None：每页结果会分别写入 pages 表。
    """

    generation_lock = get_lecture_notes_generation_lock(document_id)
    if not generation_lock.acquire(blocking=False):
        # 已有同一文档的整份讲稿生成任务在运行时，不再启动第二条并发生成任务。
        return

    try:
        try:
            document = get_document_ready_for_lecture_notes(document_id)
        except HTTPException:
            # 课程简介未 ready 或文档不存在时，不能可靠生成逐页讲稿。
            return

        pages = list_pages_for_lecture_notes(document_id, only_unfinished=True)
        for page in pages:
            if is_lecture_notes_paused(document_id):
                # 暂停采用协作式控制：不打断当前 LLM 请求，只阻止下一页继续开始。
                return

            generate_single_page_lecture_notes(document=document, page=page)
    finally:
        generation_lock.release()


def generate_course_summary(document_id: str) -> None:
    """为指定文档生成课程简介并写入数据库。

    参数：
        document_id：需要生成课程简介的文档 ID。

    返回值：
        None：生成结果会写入 documents 表。
    """

    try:
        update_course_summary_status(
            document_id=document_id,
            summary_status="processing",
            course_summary=None,
            error_message=None,
        )

        document, pages_text, was_truncated = build_course_summary_input(document_id)
        prompt = build_course_summary_prompt(
            document=document,
            pages_text=pages_text,
            was_truncated=was_truncated,
        )

        client = LLMClient(get_llm_config())
        course_summary = client.complete_text(prompt)

        update_course_summary_status(
            document_id=document_id,
            summary_status="ready",
            course_summary=course_summary,
            error_message=None,
        )

        reset_document_lecture_notes_status(document_id)
        generate_document_lecture_notes(document_id)
    except Exception as error:
        update_course_summary_status(
            document_id=document_id,
            summary_status="failed",
            course_summary=None,
            error_message=f"课程简介生成失败：{error}",
        )


def parse_pdf_pages(document_id: str, saved_path: Path) -> None:
    """解析 PDF 页数、每页文字和每页截图，并写入 pages 表。

    参数：
        document_id：当前 PDF 对应的文档 ID。
        saved_path：已经保存到本地的 PDF 文件路径。

    返回值：
        None：解析结果和截图路径会直接写入 SQLite。
    """

    # 如果 PDF 文件损坏或不是合法 PDF，pymupdf.open 会抛出异常。
    try:
        with pymupdf.open(saved_path) as pdf_document:
            has_page_error = False
            page_error_messages: list[str] = []

            # enumerate 从 0 开始，所以通过 start=1 让 page_number 符合用户习惯。
            for page_number, page in enumerate(pdf_document, start=1):
                try:
                    # get_text("text", sort=True) 会按阅读顺序尽量提取页面文字。
                    # 空白页会得到空字符串，但仍然需要创建页面记录。
                    page_text = page.get_text("text", sort=True)

                    # 页面截图会供前端直接展示，也会供后续 LLM 视觉理解图表、公式和排版。
                    image_path = render_page_image(
                        page=page,
                        document_id=document_id,
                        page_number=page_number,
                    )

                    create_page_record(
                        document_id=document_id,
                        page_number=page_number,
                        text=page_text,
                        image_path=image_path,
                        page_status="ready",
                    )
                except Exception as error:
                    # 单页失败时仍然写入记录，避免页面数量和 PDF 实际页码不一致。
                    # 这里把文字和截图放在同一个页级处理块里，保证任一环节失败都会被清楚标记。
                    has_page_error = True
                    error_message = f"第 {page_number} 页解析或截图生成失败：{error}"
                    page_error_messages.append(error_message)
                    create_page_record(
                        document_id=document_id,
                        page_number=page_number,
                        text="",
                        image_path=None,
                        page_status="failed",
                        error_message=error_message,
                    )

            if has_page_error:
                update_document_status(
                    document_id=document_id,
                    document_status="failed",
                    error_message="；".join(page_error_messages),
                )
                return

            # 所有页面都创建成功后，把文档状态更新为 ready。
            update_document_status(document_id=document_id, document_status="ready")
    except Exception as error:
        # 整个 PDF 无法打开或无法读取时，记录失败状态，不让后端服务崩溃。
        update_document_status(
            document_id=document_id,
            document_status="failed",
            error_message=f"PDF 无法打开或解析：{error}",
        )


@app.on_event("startup")
def startup() -> None:
    """后端启动时初始化数据库。

    返回值：
        None：这个函数由 FastAPI 在应用启动时自动调用。
    """

    # 启动时建库建表，保证第一次运行项目时不需要手动准备数据库文件。
    init_database()


# 配置开发环境 CORS。
# CORS 是浏览器的跨域访问控制机制；前端开发服务器和后端端口不同，所以需要显式允许。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def read_health() -> dict[str, str]:
    """返回后端健康状态。

    返回值：
        dict[str, str]：包含后端当前状态的 JSON 数据。
    """

    # 这里返回固定状态，供前端确认后端服务已经正常启动。
    return {"status": "ok", "service": "slides-reader-api"}


@app.get("/api/documents")
def list_documents() -> list[dict[str, str | int | None]]:
    """返回已经上传过的文档列表。

    返回值：
        list[dict[str, str | int | None]]：按创建时间倒序排列的文档记录列表。
    """

    # 查询前先确保数据库已初始化，方便在测试或直接导入 app 时也能正常工作。
    init_database()

    # 每次请求单独打开数据库连接，请求结束后自动关闭，适合当前小型本地应用。
    with get_database_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                documents.id,
                documents.title,
                documents.file_path,
                documents.status,
                documents.error_message,
                documents.course_summary,
                documents.course_summary_status,
                documents.course_summary_error,
                documents.lecture_notes_paused,
                documents.created_at,
                COUNT(pages.id) AS page_count
            FROM documents
            LEFT JOIN pages ON pages.document_id = documents.id
            GROUP BY documents.id
            ORDER BY documents.created_at DESC
            """
        ).fetchall()

    # 将数据库行转换为普通字典，方便 FastAPI 自动序列化为 JSON。
    return [row_to_document(row) for row in rows]


@app.get("/api/documents/{document_id}/file")
def read_document_file(document_id: str) -> FileResponse:
    """返回某个文档对应的系统实际使用的 PDF 文件。

    参数：
        document_id：需要读取 PDF 的文档 ID。

    返回值：
        FileResponse：找到文件时直接返回 PDF 文件内容，供前端 PDF 阅读器渲染。
    """

    # 查询前先确保数据库表存在，方便第一次启动后端后直接访问接口也能得到稳定错误。
    init_database()

    with get_database_connection() as connection:
        document = connection.execute(
            """
            SELECT title, file_path
            FROM documents
            WHERE id = ?
            """,
            (document_id,),
        ).fetchone()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的文档。",
        )

    # file_path 来自数据库，返回文件前必须解析为绝对路径并检查目录边界。
    document_file_path = resolve_document_file_path(document["file_path"])
    ensure_document_file_is_safe(document_file_path)

    if not document_file_path.exists() or not document_file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF 文件不存在，可能已经被手动删除。",
        )

    # FileResponse 会让 FastAPI 直接读取并返回静态文件。
    # content-disposition 设置为 inline，表示浏览器和 PDF 阅读器可以直接展示，而不是优先下载。
    response = FileResponse(
        path=document_file_path,
        media_type="application/pdf",
        filename=document_file_path.name,
    )
    response.headers["content-disposition"] = (
        f'inline; filename="{document_file_path.name}"'
    )
    return response


@app.get("/api/documents/{document_id}/status")
def read_document_status(document_id: str) -> dict[str, Any]:
    """返回指定文档的处理进度和页级错误状态。

    参数：
        document_id：需要查询处理状态的文档 ID。

    返回值：
        dict[str, Any]：包含文档状态、课程简介状态、讲稿完成数量和每页状态。
    """

    init_database()

    with get_database_connection() as connection:
        document = connection.execute(
            """
            SELECT
                id,
                title,
                status,
                error_message,
                course_summary_status,
                course_summary_error,
                course_summary,
                lecture_notes_paused
            FROM documents
            WHERE id = ?
            """,
            (document_id,),
        ).fetchone()

        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="没有找到对应的文档。",
            )

        page_rows = connection.execute(
            """
            SELECT
                id,
                page_number,
                status,
                error_message,
                lecture_notes_status,
                lecture_notes_error
            FROM pages
            WHERE document_id = ?
            ORDER BY page_number ASC
            """,
            (document_id,),
        ).fetchall()

    pages = [
        {
            "page_id": row["id"],
            "page_number": row["page_number"],
            "status": row["status"],
            "error_message": row["error_message"],
            "lecture_notes_status": row["lecture_notes_status"],
            "lecture_notes_error": row["lecture_notes_error"],
        }
        for row in page_rows
    ]
    total_pages = len(pages)
    lecture_notes_ready_count = sum(
        1 for page in pages if page["lecture_notes_status"] == "ready"
    )
    lecture_notes_failed_count = sum(
        1 for page in pages if page["lecture_notes_status"] == "failed"
    )
    lecture_notes_processing_count = sum(
        1 for page in pages if page["lecture_notes_status"] == "processing"
    )
    lecture_notes_pending_count = sum(
        1 for page in pages if page["lecture_notes_status"] == "pending"
    )

    lecture_notes_paused = bool(document["lecture_notes_paused"])

    # 只要文档解析、课程简介或未暂停的逐页讲稿仍在处理中，前端就需要继续轮询。
    should_poll = (
        document["status"] == "processing"
        or document["course_summary_status"] == "processing"
        or (not lecture_notes_paused and lecture_notes_processing_count > 0)
        or (
            not lecture_notes_paused
            and
            document["course_summary_status"] == "ready"
            and lecture_notes_pending_count > 0
        )
    )

    return {
        "document_id": document["id"],
        "title": document["title"],
        "status": document["status"],
        "error_message": document["error_message"],
        "course_summary_status": document["course_summary_status"],
        "course_summary_error": document["course_summary_error"],
        "course_summary_ready": document["course_summary_status"] == "ready"
        and bool(document["course_summary"]),
        "total_pages": total_pages,
        "lecture_notes_ready_count": lecture_notes_ready_count,
        "lecture_notes_failed_count": lecture_notes_failed_count,
        "lecture_notes_processing_count": lecture_notes_processing_count,
        "lecture_notes_pending_count": lecture_notes_pending_count,
        "lecture_notes_paused": lecture_notes_paused,
        "should_poll": should_poll,
        "pages": pages,
    }


@app.get("/api/documents/{document_id}/pages")
def list_document_pages(document_id: str) -> list[dict[str, Any]]:
    """返回某个文档的所有页面解析记录。

    参数：
        document_id：需要查询页面的文档 ID。

    返回值：
        list[dict[str, str | int | None]]：按页码升序排列的页面记录列表。
    """

    # 查询前先确保数据库已初始化，方便第一次请求也能正常返回空列表或结果。
    init_database()

    with get_database_connection() as connection:
        document = connection.execute(
            "SELECT id FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()

        # 如果文档不存在，返回 404，避免前端误以为只是没有页面。
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="没有找到对应的文档。",
            )

        pages = connection.execute(
            """
            SELECT
                id,
                document_id,
                page_number,
                text,
                image_path,
                status,
                error_message,
                lecture_notes,
                lecture_notes_status,
                lecture_notes_error,
                created_at
            FROM pages
            WHERE document_id = ?
            ORDER BY page_number ASC
            """,
            (document_id,),
        ).fetchall()

        # 历史数据中可能已有 ready 讲稿但还没有 note_blocks。
        # 这里在读取页面时补齐默认文字块，避免额外要求用户重新生成讲稿。
        for page in pages:
            ensure_note_block_for_ready_page(connection, page)
        connection.commit()

        rows = connection.execute(
            """
            SELECT
                pages.id,
                pages.document_id,
                pages.page_number,
                pages.text,
                pages.image_path,
                pages.status,
                pages.error_message,
                pages.lecture_notes,
                pages.lecture_notes_status,
                pages.lecture_notes_error,
                pages.created_at,
                note_blocks.id AS note_block_id,
                note_blocks.page_id AS note_block_page_id,
                note_blocks.content AS note_block_content,
                note_blocks.x AS note_block_x,
                note_blocks.y AS note_block_y,
                note_blocks.width AS note_block_width,
                note_blocks.height AS note_block_height,
                note_blocks.created_at AS note_block_created_at,
                note_blocks.updated_at AS note_block_updated_at
            FROM pages
            LEFT JOIN note_blocks ON note_blocks.page_id = pages.id
            WHERE pages.document_id = ?
            ORDER BY pages.page_number ASC
            """,
            (document_id,),
        ).fetchall()

    serialized_pages = [row_to_page(row) for row in rows]
    messages_by_page = list_chat_messages_for_pages(
        [page["page_id"] for page in serialized_pages]
    )

    for page in serialized_pages:
        page["chat_messages"] = messages_by_page.get(page["page_id"], [])

    return serialized_pages


@app.get("/api/documents/{document_id}/pages/{page_number}/image")
def read_page_image(document_id: str, page_number: int) -> FileResponse:
    """返回某个文档某一页的 PNG 截图。

    参数：
        document_id：需要读取截图的文档 ID。
        page_number：从 1 开始的页码。

    返回值：
        FileResponse：找到截图时直接返回 PNG 文件内容。
    """

    # 页码从用户视角必须从 1 开始，0 或负数没有对应的 PDF 页面。
    if page_number < 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的页面。",
        )

    init_database()

    with get_database_connection() as connection:
        document = connection.execute(
            "SELECT id FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()

        # 文档不存在时先返回文档级 404，避免把不存在文档误判成图片丢失。
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="没有找到对应的文档。",
            )

        page = connection.execute(
            """
            SELECT image_path
            FROM pages
            WHERE document_id = ? AND page_number = ?
            """,
            (document_id, page_number),
        ).fetchone()

    if page is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的页面。",
        )

    if not page["image_path"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="当前页面还没有生成截图。",
        )

    image_path = resolve_page_image_path(page["image_path"])
    ensure_page_image_file_is_safe(image_path)

    if not image_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="页面截图文件不存在，可能已被手动删除。",
        )

    # FileResponse 会让 FastAPI 直接读取并返回静态文件，适合图片、PDF 这类本地文件。
    return FileResponse(
        path=image_path,
        media_type="image/png",
        filename=image_path.name,
    )


@app.post("/api/pages/{page_id}/chat")
def chat_with_page(page_id: str, request: PageChatRequest) -> dict[str, Any]:
    """围绕某一页 slides 向 LLM 老师提问，并保存当前页问答历史。

    参数：
        page_id：用户当前正在阅读的页面 ID。
        request：包含用户问题的请求体。

    返回值：
        dict[str, Any]：用户消息、AI 老师回答和当前页完整问答历史。
    """

    question = request.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="问题不能为空。",
        )

    init_database()
    page_context = get_page_context_for_chat(page_id)

    # 先保存用户问题。即使后续 LLM 调用失败，用户提问也不会因为网络或配置错误丢失。
    user_message = create_chat_message(
        page_id=page_context["page_id"],
        role="user",
        content=question,
    )

    try:
        history_messages = [
            message
            for message in list_recent_chat_messages_for_prompt(page_context["page_id"])
            if message["chat_message_id"] != user_message["chat_message_id"]
        ]
        prompt = build_page_chat_prompt(
            page_context=page_context,
            history_messages=history_messages,
            question=question,
        )
        client = LLMClient(get_llm_config())
        answer = client.complete_text(prompt)
        assistant_message = create_chat_message(
            page_id=page_context["page_id"],
            role="assistant",
            content=answer,
        )
    except HTTPException:
        # LLMClient 已经把配置、网络或服务端错误整理成明确 HTTPException，保持原样返回给前端。
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"当前页问答失败：{error}",
        ) from error

    return {
        "status": "ok",
        "page_id": page_context["page_id"],
        "user_message": user_message,
        "assistant_message": assistant_message,
        "messages": list_chat_messages_for_page(page_context["page_id"]),
    }


@app.get("/api/llm/config")
def read_llm_config() -> dict[str, str | int | bool]:
    """返回当前 LLM 配置，供前端 WebUI 展示。

    返回值：
        dict[str, str | int | bool]：不包含明文 API Key 的 LLM 配置。
    """

    # API Key 属于敏感信息，只返回是否已配置和掩码，不把明文发回浏览器。
    return serialize_llm_config(get_llm_config())


@app.patch("/api/llm/config")
def update_llm_config(request: LLMConfigUpdateRequest) -> dict[str, str | int | bool]:
    """保存用户从 WebUI 修改的 LLM 配置。

    参数：
        request：前端提交的新配置。

    返回值：
        dict[str, str | int | bool]：保存后的配置，API Key 仍然只返回掩码。
    """

    # base_url 和 model 是发起请求必须使用的普通配置，允许用户随时覆盖。
    base_url = normalize_base_url(request.base_url)
    model = request.model.strip()
    timeout_seconds = normalize_timeout_seconds(request.timeout_seconds)

    if not base_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LLM_BASE_URL 不能为空。",
        )

    if not model:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LLM_MODEL 不能为空。",
        )

    next_settings = {
        "base_url": base_url,
        "model": model,
        "timeout_seconds": str(timeout_seconds),
    }

    # course_summary_prompt 为 None 表示旧客户端没有提交这个新增字段，此时保留旧 prompt。
    # 如果前端或用户明确提交了 prompt，就必须保证它不是空字符串。
    if request.course_summary_prompt is not None:
        course_summary_prompt = request.course_summary_prompt.strip()
        if not course_summary_prompt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="课程简介 prompt 不能为空。",
            )
        next_settings["course_summary_prompt"] = course_summary_prompt

    # lecture_notes_prompt 为 None 表示旧客户端没有提交这个新增字段，此时保留旧 prompt。
    # 如果前端或用户明确提交了 prompt，就必须保证它不是空字符串。
    if request.lecture_notes_prompt is not None:
        lecture_notes_prompt = request.lecture_notes_prompt.strip()
        if not lecture_notes_prompt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="逐页讲稿 prompt 不能为空。",
            )
        next_settings["lecture_notes_prompt"] = lecture_notes_prompt

    # page_chat_prompt 为 None 表示旧客户端没有提交这个新增字段，此时保留旧 prompt。
    # 如果前端或用户明确提交了 prompt，就必须保证它不是空字符串。
    if request.page_chat_prompt is not None:
        page_chat_prompt = request.page_chat_prompt.strip()
        if not page_chat_prompt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="当前页问答 prompt 不能为空。",
            )
        next_settings["page_chat_prompt"] = page_chat_prompt

    # api_key 为 None 表示前端没有提交新密钥，要保留旧密钥。
    # api_key 为空字符串表示用户明确清空密钥。
    if request.api_key is not None:
        next_settings["api_key"] = request.api_key.strip()

    write_app_settings(next_settings)

    return serialize_llm_config(get_llm_config())


@app.post("/api/llm/test")
def test_llm_config(request: LLMTestRequest) -> dict[str, str]:
    """使用当前配置向 LLM 发起一次文本测试请求。

    参数：
        request：包含测试提示词的请求体。

    返回值：
        dict[str, str]：模型返回的测试回答。
    """

    prompt = request.prompt.strip()
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="测试提示词不能为空。",
        )

    client = LLMClient(get_llm_config())
    answer = client.complete_text(prompt)

    return {
        "status": "ok",
        "answer": answer,
    }


@app.post("/api/documents/{document_id}/course-summary/regenerate")
def regenerate_course_summary(
    document_id: str,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """重新生成指定文档的课程简介。

    参数：
        document_id：需要重新生成课程简介的文档 ID。
        background_tasks：FastAPI 提供的后台任务管理对象。

    返回值：
        dict[str, str]：表示后台任务已经提交的结果。
    """

    init_database()

    with get_database_connection() as connection:
        document = connection.execute(
            "SELECT id FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="没有找到对应的文档。",
            )

        page_count = connection.execute(
            "SELECT COUNT(id) AS page_count FROM pages WHERE document_id = ?",
            (document_id,),
        ).fetchone()["page_count"]

    if page_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前文档还没有页面记录，无法生成课程简介。",
        )

    update_course_summary_status(
        document_id=document_id,
        summary_status="processing",
        course_summary=None,
        error_message=None,
    )
    background_tasks.add_task(generate_course_summary, document_id)

    return {
        "status": "processing",
        "document_id": document_id,
    }


@app.post("/api/documents/{document_id}/lecture-notes/regenerate")
def regenerate_document_lecture_notes(
    document_id: str,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """重新生成指定文档的所有页面讲稿。

    参数：
        document_id：需要重新生成逐页讲稿的文档 ID。
        background_tasks：FastAPI 提供的后台任务管理对象。

    返回值：
        dict[str, str]：表示后台任务已经提交的结果。
    """

    init_database()
    document = get_document_ready_for_lecture_notes(document_id)
    reset_document_lecture_notes_status(document_id)
    background_tasks.add_task(generate_document_lecture_notes, document["id"])

    return {
        "status": "processing",
        "document_id": document_id,
    }


@app.post("/api/documents/{document_id}/lecture-notes/pause")
def pause_document_lecture_notes(document_id: str) -> dict[str, str | bool]:
    """暂停指定文档后续页面的讲稿生成。

    参数：
        document_id：需要暂停逐页讲稿生成的文档 ID。

    返回值：
        dict[str, str | bool]：包含文档 ID 和最新暂停状态。
    """

    init_database()

    with get_database_connection() as connection:
        document = connection.execute(
            "SELECT id FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的文档。",
        )

    # 暂停只阻止下一页开始生成，已经发给 LLM 的当前页请求会自然完成。
    set_lecture_notes_paused(document_id=document_id, paused=True)

    return {
        "status": "paused",
        "document_id": document_id,
        "lecture_notes_paused": True,
    }


@app.post("/api/documents/{document_id}/lecture-notes/resume")
def resume_document_lecture_notes(
    document_id: str,
    background_tasks: BackgroundTasks,
) -> dict[str, str | bool]:
    """继续指定文档未完成页面的讲稿生成。

    参数：
        document_id：需要继续逐页讲稿生成的文档 ID。
        background_tasks：FastAPI 提供的后台任务管理对象。

    返回值：
        dict[str, str | bool]：表示后台继续生成任务已经提交。
    """

    init_database()
    document = get_document_ready_for_lecture_notes(document_id)

    # 先清除暂停标记，再提交后台任务；如果旧任务还在运行，文档级锁会避免重复并发生成。
    set_lecture_notes_paused(document_id=document_id, paused=False)
    background_tasks.add_task(generate_document_lecture_notes, document["id"])

    return {
        "status": "processing",
        "document_id": document_id,
        "lecture_notes_paused": False,
    }


@app.post("/api/documents/{document_id}/pages/{page_number}/lecture-notes/regenerate")
def regenerate_page_lecture_notes(
    document_id: str,
    page_number: int,
    background_tasks: BackgroundTasks,
) -> dict[str, str | int]:
    """重新生成指定页面的讲稿。

    参数：
        document_id：页面所属文档 ID。
        page_number：从 1 开始的页码。
        background_tasks：FastAPI 提供的后台任务管理对象。

    返回值：
        dict[str, str | int]：表示后台任务已经提交的结果。
    """

    init_database()
    document = get_document_ready_for_lecture_notes(document_id)
    page = get_page_for_lecture_notes(document_id=document_id, page_number=page_number)

    update_page_lecture_notes_status(
        document_id=document_id,
        page_number=page_number,
        lecture_notes_status="processing",
        lecture_notes=None,
        error_message=None,
    )
    background_tasks.add_task(generate_single_page_lecture_notes, document, page)

    return {
        "status": "processing",
        "document_id": document_id,
        "page_number": page_number,
    }


@app.post("/api/pages/{page_id}/regenerate")
def regenerate_page_lecture_notes_by_id(
    page_id: str,
    background_tasks: BackgroundTasks,
) -> dict[str, str | int]:
    """通过 page_id 重新生成指定页面讲稿。

    参数：
        page_id：需要重新生成讲稿的页面 ID。
        background_tasks：FastAPI 提供的后台任务管理对象。

    返回值：
        dict[str, str | int]：表示后台任务已经提交的结果。
    """

    init_database()
    page = get_page_for_lecture_notes_by_id(page_id)
    document = get_document_ready_for_lecture_notes(page["document_id"])

    update_page_lecture_notes_status(
        document_id=page["document_id"],
        page_number=page["page_number"],
        lecture_notes_status="processing",
        lecture_notes=None,
        error_message=None,
    )
    background_tasks.add_task(generate_single_page_lecture_notes, document, page)

    return {
        "status": "processing",
        "document_id": page["document_id"],
        "page_id": page["id"],
        "page_number": page["page_number"],
    }


@app.patch("/api/note-blocks/{note_block_id}")
def update_note_block_position(
    note_block_id: str,
    request: NoteBlockPositionUpdateRequest,
) -> dict[str, str | float]:
    """保存讲稿文字块拖动或缩放后的新位置。

    参数：
        note_block_id：需要更新的讲稿文字块 ID。
        request：前端提交的坐标和尺寸数据。

    返回值：
        dict[str, str | float]：更新后的讲稿文字块数据。
    """

    # PATCH 接口只负责保存位置和尺寸，不允许前端通过这个接口修改讲稿正文。
    validate_note_block_position(request)
    init_database()

    with get_database_connection() as connection:
        note_block = connection.execute(
            """
            SELECT id
            FROM note_blocks
            WHERE id = ?
            """,
            (note_block_id,),
        ).fetchone()

        if note_block is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="没有找到对应的讲稿文字块。",
            )

        updated_at = datetime.now(UTC).isoformat()
        connection.execute(
            """
            UPDATE note_blocks
            SET
                x = ?,
                y = ?,
                width = ?,
                height = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                request.x,
                request.y,
                request.width,
                request.height,
                updated_at,
                note_block_id,
            ),
        )
        connection.commit()

        updated_note_block = connection.execute(
            """
            SELECT
                id,
                page_id,
                content,
                x,
                y,
                width,
                height,
                created_at,
                updated_at
            FROM note_blocks
            WHERE id = ?
            """,
            (note_block_id,),
        ).fetchone()

    return row_to_note_block(updated_note_block)


@app.patch("/api/documents/{document_id}")
def rename_document(
    document_id: str,
    request: RenameDocumentRequest,
) -> dict[str, str | int | None]:
    """重命名文档显示标题。

    参数：
        document_id：需要重命名的文档 ID。
        request：包含新标题的请求体。

    返回值：
        dict[str, str | int | None]：更新后的文档记录。
    """

    # 去掉首尾空白，避免保存看起来为空的标题。
    next_title = request.title.strip()

    if not next_title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文档标题不能为空。",
        )

    init_database()

    with get_database_connection() as connection:
        result = connection.execute(
            """
            UPDATE documents
            SET title = ?
            WHERE id = ?
            """,
            (next_title, document_id),
        )
        connection.commit()

    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的文档。",
        )

    document = get_document_with_page_count(document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的文档。",
        )

    return document


@app.delete("/api/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str) -> Response:
    """删除文档记录、页面记录、本地 PDF 文件和页面截图文件。

    参数：
        document_id：需要删除的文档 ID。

    返回值：
        Response：删除成功时返回 204 空响应。
    """

    init_database()

    with get_database_connection() as connection:
        document = connection.execute(
            "SELECT id, file_path FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()

        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="没有找到对应的文档。",
            )

        # 删除数据库记录前先计算 PDF 文件路径并完成安全检查。
        # 这样一旦路径异常，不会出现数据库已删但文件未处理的状态。
        document_file_path = resolve_document_file_path(document["file_path"])
        ensure_document_file_is_safe(document_file_path)

        page_image_rows = connection.execute(
            """
            SELECT image_path
            FROM pages
            WHERE document_id = ? AND image_path IS NOT NULL
            """,
            (document_id,),
        ).fetchall()

        # 截图路径同样来自数据库，删除前需要逐个做目录边界检查。
        page_image_paths = [
            resolve_page_image_path(row["image_path"])
            for row in page_image_rows
            if row["image_path"]
        ]
        for page_image_path in page_image_paths:
            ensure_page_image_file_is_safe(page_image_path)

        # 先删问答历史和讲稿文字块，再删 pages 和 documents，避免留下孤立页面记录。
        connection.execute(
            """
            DELETE FROM chat_messages
            WHERE page_id IN (
                SELECT id
                FROM pages
                WHERE document_id = ?
            )
            """,
            (document_id,),
        )
        connection.execute(
            """
            DELETE FROM note_blocks
            WHERE page_id IN (
                SELECT id
                FROM pages
                WHERE document_id = ?
            )
            """,
            (document_id,),
        )
        connection.execute("DELETE FROM pages WHERE document_id = ?", (document_id,))
        connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        connection.commit()

    # 如果文件已经不存在，说明本地文件可能被手动删除过；此时数据库删除仍然算成功。
    if document_file_path.exists():
        try:
            document_file_path.unlink()
        except OSError as error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"数据库记录已删除，但本地 PDF 文件删除失败：{error}",
            ) from error

    # 页面截图和系统使用的 PDF 一样属于运行数据；如果文件已不存在，删除接口仍然算成功。
    for page_image_path in page_image_paths:
        if page_image_path.exists():
            try:
                page_image_path.unlink()
            except OSError as error:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"数据库记录已删除，但页面截图删除失败：{error}",
                ) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)


def get_upload_file_extension(file: UploadFile) -> str:
    """读取上传文件的小写后缀名。

    参数：
        file：FastAPI 接收到的上传文件对象，里面包含原始文件名。

    返回值：
        str：包含点号的小写后缀名，例如 `.pdf`、`.ppt`、`.pptx`；没有文件名时返回空字符串。
    """

    # filename 可能为空，所以先使用空字符串兜底。
    filename = file.filename or ""

    # Path(...).suffix 会返回最后一个后缀，并保留开头的点号。
    return Path(filename).suffix.lower()


def is_supported_slides_upload(file: UploadFile) -> bool:
    """判断上传文件是否是当前支持的 slides 格式。

    参数：
        file：FastAPI 接收到的上传文件对象，里面包含文件名、文件类型和文件内容读取方法。

    返回值：
        bool：文件名后缀是 `.pdf`、`.ppt` 或 `.pptx` 时返回 True，否则返回 False。
    """

    # 浏览器对 PPT/PPTX 的 content-type 声明并不稳定，所以这里以后缀作为主校验。
    return get_upload_file_extension(file) in {".pdf", ".ppt", ".pptx"}


def resolve_soffice_path() -> Path | None:
    """查找 LibreOffice 的 soffice.exe 路径。

    返回值：
        Path | None：找到时返回 soffice.exe 的绝对路径；找不到时返回 None。
    """

    # 候选路径按优先级排列：环境变量、项目内 Portable、系统安装路径。
    candidate_paths = [
        getenv("SLIDES_READER_SOFFICE_PATH", ""),
        str(BASE_DIR.parent / "tools" / "libreoffice" / "LibreOfficePortable" / "App" / "libreoffice" / "program" / "soffice.exe"),
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]

    # 逐个检查候选路径，找到第一个存在的文件就返回。
    for candidate_path in candidate_paths:
        if not candidate_path:
            continue

        resolved_path = Path(candidate_path).resolve()
        if resolved_path.exists() and resolved_path.is_file():
            return resolved_path

    # 如果用户已经把 soffice.exe 放进 PATH，也允许通过系统查找结果使用。
    try:
        command_result = subprocess.run(
            ["where", "soffice.exe"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    # where 可能返回多行，取第一条存在的路径。
    for output_line in command_result.stdout.splitlines():
        resolved_path = Path(output_line.strip()).resolve()
        if resolved_path.exists() and resolved_path.is_file():
            return resolved_path

    return None


def convert_slides_to_pdf(source_path: Path, output_pdf_path: Path) -> None:
    """使用 LibreOffice 把 PPT/PPTX 转换成 PDF。

    参数：
        source_path：临时保存的原始 PPT/PPTX 文件路径。
        output_pdf_path：转换成功后系统实际使用的 PDF 路径。

    返回值：
        None：转换成功时不返回数据，失败时抛出 HTTPException。
    """

    # 查找 LibreOffice 命令行入口；找不到时给出可执行的修复提示。
    soffice_path = resolve_soffice_path()
    if soffice_path is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="没有找到 LibreOffice 的 soffice.exe，无法转换 PPT/PPTX。请先运行项目根目录下的 setup-env.ps1，或设置 SLIDES_READER_SOFFICE_PATH。",
        )

    # 确保输出目录和 LibreOffice 独立 profile 目录存在。
    output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    LIBREOFFICE_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    # LibreOffice 使用 file URI 作为 UserInstallation 参数。
    profile_uri = LIBREOFFICE_PROFILE_DIR.resolve().as_uri()

    # LibreOffice 默认会按源文件名生成 PDF，因此先转换到源文件所在临时目录，再移动成 document_id.pdf。
    conversion_output_path = source_path.with_suffix(".pdf")
    if conversion_output_path.exists():
        conversion_output_path.unlink()

    # 组装命令行参数；--headless 表示不打开图形界面。
    command = [
        str(soffice_path),
        f"-env:UserInstallation={profile_uri}",
        "--headless",
        "--nologo",
        "--nodefault",
        "--nofirststartwizard",
        "--nolockcheck",
        "--convert-to",
        "pdf",
        "--outdir",
        str(source_path.parent),
        str(source_path),
    ]

    try:
        process = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LibreOffice 转换 PPT/PPTX 超时，请确认文件没有损坏或过大。",
        ) from error
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"无法启动 LibreOffice 转换进程：{error}",
        ) from error

    # soffice.exe 在 Windows 上有时不会稳定返回退出码，所以优先检查 PDF 产物是否生成。
    if not conversion_output_path.exists() or not conversion_output_path.is_file():
        error_output = (process.stderr or process.stdout or "").strip()
        if process.returncode not in (0, None):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"LibreOffice 转换失败，退出码 {process.returncode}：{error_output or '没有返回错误详情'}",
            )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LibreOffice 转换命令已执行，但没有生成 PDF：{error_output or '没有返回错误详情'}",
        )

    # 如果目标 PDF 已经存在，先删除再移动，避免旧文件残留。
    if output_pdf_path.exists():
        output_pdf_path.unlink()

    # replace 会把临时输出 PDF 移动到系统统一使用的 documents 目录。
    conversion_output_path.replace(output_pdf_path)


@app.post("/api/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> dict[str, str | int | None]:
    """接收用户上传的 PDF/PPT/PPTX slides，并保存为系统实际使用的 PDF。

    参数：
        file：前端通过 multipart/form-data 上传的 PDF、PPT 或 PPTX 文件。

    返回值：
        dict[str, str | int | None]：包含文档记录、页数、错误信息和保存后的文件名。
    """

    # 先校验文件类型，不合格时直接返回 400，避免把错误文件写入 storage。
    if not is_supported_slides_upload(file):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只支持上传 PDF、PPT 或 PPTX 文件，请选择 .pdf、.ppt 或 .pptx 格式的 slides。",
        )

    # 为当前上传生成唯一 document_id，后续任务会用它关联页面、讲稿和问答记录。
    document_id = str(uuid4())

    # 读取上传文件后缀，决定是直接保存 PDF 还是先转换 PPT/PPTX。
    upload_extension = get_upload_file_extension(file)

    # 创建保存目录；parents=True 表示父目录不存在时一起创建。
    DOCUMENT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    # 使用后端生成的 ID 作为最终 PDF 文件名，避免用户原始文件名重复或包含不安全字符。
    saved_filename = f"{document_id}.pdf"
    saved_path = DOCUMENT_STORAGE_DIR / saved_filename

    # 读取上传内容；后续会根据格式直接写入 PDF 或先写入临时 PPT/PPTX。
    file_bytes = await file.read()

    if upload_extension == ".pdf":
        # PDF 上传保持原有行为，直接保存为系统使用的 PDF。
        saved_path.write_bytes(file_bytes)
    else:
        # PPT/PPTX 不长期保存原文件，只写入临时目录用于 LibreOffice 转换。
        CONVERSION_TEMP_DIR.mkdir(parents=True, exist_ok=True)
        temporary_source_path = CONVERSION_TEMP_DIR / f"{document_id}{upload_extension}"

        try:
            temporary_source_path.write_bytes(file_bytes)
            convert_slides_to_pdf(
                source_path=temporary_source_path,
                output_pdf_path=saved_path,
            )
        finally:
            # 原始 PPT/PPTX 只用于转换，转换成功或失败后都尽量删除。
            if temporary_source_path.exists():
                temporary_source_path.unlink()
            temporary_pdf_path = temporary_source_path.with_suffix(".pdf")
            if temporary_pdf_path.exists():
                temporary_pdf_path.unlink()

    # created_at 使用 UTC 时间，方便后续不同地区或部署环境统一排序。
    created_at = datetime.now(UTC).isoformat()

    # 当前任务中，上传成功后会立即解析 PDF，所以初始状态设为 processing。
    document_status = "processing"

    # 确保数据库和 documents 表已经存在。
    init_database()

    # 上传文件保存成功后，把文档记录写入 SQLite。
    with get_database_connection() as connection:
        connection.execute(
            """
            INSERT INTO documents (
                id,
                title,
                file_path,
                status,
                error_message,
                course_summary,
                course_summary_status,
                course_summary_error,
                lecture_notes_paused,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                file.filename or "unknown.pdf",
                str(saved_path),
                document_status,
                None,
                None,
                "pending",
                None,
                0,
                created_at,
            ),
        )
        connection.commit()

    # 同步解析 PDF 页数、文字和页面截图。
    # 任务 05 暂不使用后台任务，后续 LLM 生成阶段再引入后台处理。
    parse_pdf_pages(document_id=document_id, saved_path=saved_path)

    # PDF 解析成功后，后台生成整份课程简介。
    # 生成失败只影响课程简介字段，不影响文档和页面记录继续可用。
    document_after_parse = get_document_with_page_count(document_id)
    if document_after_parse is not None and document_after_parse["status"] == "ready":
        update_course_summary_status(
            document_id=document_id,
            summary_status="processing",
            course_summary=None,
            error_message=None,
        )
        background_tasks.add_task(generate_course_summary, document_id)
    elif document_after_parse is not None and document_after_parse["status"] == "failed":
        update_course_summary_status(
            document_id=document_id,
            summary_status="failed",
            course_summary=None,
            error_message="PDF 解析失败，无法生成课程简介。",
        )

    # 解析后重新读取文档记录和页数，保证接口返回的是最终状态。
    with get_database_connection() as connection:
        document = connection.execute(
            """
            SELECT
                documents.id,
                documents.title,
                documents.file_path,
                documents.status,
                documents.error_message,
                documents.course_summary,
                documents.course_summary_status,
                documents.course_summary_error,
                documents.lecture_notes_paused,
                documents.created_at,
                COUNT(pages.id) AS page_count
            FROM documents
            LEFT JOIN pages ON pages.document_id = documents.id
            WHERE documents.id = ?
            GROUP BY documents.id
            """,
            (document_id,),
        ).fetchone()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PDF 已保存，但无法读取文档记录。",
        )

    return {
        **row_to_document(document),
        "filename": file.filename or "unknown.pdf",
        "saved_filename": saved_filename,
    }
