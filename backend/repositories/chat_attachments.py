"""当前页问答图片附件的数据访问和文件保存函数。"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, status

from config import (
    CHAT_ATTACHMENT_STORAGE_DIR,
    PAGE_CHAT_MAX_ATTACHMENT_BYTES,
    PAGE_CHAT_MAX_ATTACHMENTS_PER_MESSAGE,
)
from database import get_database_connection


@dataclass(frozen=True)
class ChatAttachmentUpload:
    """已经校验过、可以写入 storage 的会话图片。"""

    # original_filename 是浏览器上传时带来的原始文件名，用于前端展示。
    original_filename: str
    # mime_type 是根据文件头识别出的真实图片 MIME 类型。
    mime_type: str
    # extension 是根据真实 MIME 类型决定的保存后缀。
    extension: str
    # content 是完整图片二进制内容。
    content: bytes


def detect_supported_image(content: bytes) -> tuple[str, str] | None:
    """根据文件头判断图片是否属于 PNG、JPEG 或 WebP。

    参数：
        content：图片二进制内容。

    返回值：
        tuple[str, str] | None：合法时返回 MIME 类型和文件后缀；非法时返回 None。
    """

    # PNG 文件固定以 8 字节签名开头。
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"

    # JPEG 文件以 FF D8 开头，通常以 FF D9 结尾；这里只用开头识别主类型。
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"

    # WebP 是 RIFF 容器，前 12 字节中包含 RIFF 和 WEBP 标记。
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp", ".webp"

    return None


def normalize_attachment_uploads(files: list[tuple[str, bytes]]) -> list[ChatAttachmentUpload]:
    """校验上传图片列表，并转换成统一的保存对象。

    参数：
        files：由路由层读取出的文件名和二进制内容列表。

    返回值：
        list[ChatAttachmentUpload]：通过校验的图片列表。
    """

    if len(files) > PAGE_CHAT_MAX_ATTACHMENTS_PER_MESSAGE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"每次最多只能上传 {PAGE_CHAT_MAX_ATTACHMENTS_PER_MESSAGE} 张图片。",
        )

    uploads: list[ChatAttachmentUpload] = []
    for index, (filename, content) in enumerate(files, start=1):
        # 文件为空时通常代表浏览器或请求构造出错，直接给出明确提示。
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"第 {index} 个附件是空文件，请重新选择图片。",
            )

        if len(content) > PAGE_CHAT_MAX_ATTACHMENT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="单张图片不能超过 10MB。",
            )

        detected_image = detect_supported_image(content)
        if detected_image is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="只支持上传 PNG、JPEG 或 WebP 图片。",
            )

        mime_type, extension = detected_image
        safe_filename = Path(filename or f"image-{index}{extension}").name
        uploads.append(
            ChatAttachmentUpload(
                original_filename=safe_filename,
                mime_type=mime_type,
                extension=extension,
                content=content,
            )
        )

    return uploads


def build_chat_attachment_file_url(attachment_id: str) -> str:
    """生成聊天附件文件的后端访问 URL。"""

    return f"/api/chat-attachments/{attachment_id}/file"


def row_to_chat_attachment(row) -> dict[str, str | int]:
    """把 SQLite 行转换成前端使用的附件字典。"""

    return {
        "attachment_id": row["id"],
        "chat_message_id": row["chat_message_id"],
        "page_id": row["page_id"],
        "kind": row["kind"],
        "filename": row["original_filename"],
        "mime_type": row["mime_type"],
        "file_size": row["file_size"],
        "file_url": build_chat_attachment_file_url(row["id"]),
        "created_at": row["created_at"],
    }


def resolve_chat_attachment_path(file_path: str) -> Path:
    """把数据库中的附件路径解析为本地绝对路径。"""

    return Path(file_path).resolve()


def ensure_chat_attachment_file_is_safe(file_path: Path) -> None:
    """确认附件文件位于 storage/chat-attachments 目录内。"""

    storage_root = CHAT_ATTACHMENT_STORAGE_DIR.resolve()
    try:
        file_path.relative_to(storage_root)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="聊天附件路径不在允许访问的 storage/chat-attachments 目录内，已拒绝操作。",
        ) from error


def save_chat_attachments(
    page_id: str,
    chat_message_id: str,
    uploads: list[ChatAttachmentUpload],
) -> list[dict[str, str | int]]:
    """保存用户消息关联的图片附件，并返回前端展示对象。"""

    if not uploads:
        return []

    CHAT_ATTACHMENT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(timezone.utc).isoformat()
    attachment_rows: list[dict[str, str | int]] = []

    with get_database_connection() as connection:
        for display_order, upload in enumerate(uploads):
            attachment_id = str(uuid4())
            saved_path = (CHAT_ATTACHMENT_STORAGE_DIR / f"{attachment_id}{upload.extension}").resolve()
            saved_path.write_bytes(upload.content)

            connection.execute(
                """
                INSERT INTO chat_attachments (
                    id,
                    chat_message_id,
                    page_id,
                    kind,
                    original_filename,
                    mime_type,
                    file_path,
                    file_size,
                    display_order,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attachment_id,
                    chat_message_id,
                    page_id,
                    "image",
                    upload.original_filename,
                    upload.mime_type,
                    str(saved_path),
                    len(upload.content),
                    display_order,
                    created_at,
                ),
            )

            row = connection.execute(
                """
                SELECT
                    id,
                    chat_message_id,
                    page_id,
                    kind,
                    original_filename,
                    mime_type,
                    file_size,
                    created_at
                FROM chat_attachments
                WHERE id = ?
                """,
                (attachment_id,),
            ).fetchone()
            attachment_rows.append(row_to_chat_attachment(row))

        connection.commit()

    return attachment_rows


def list_chat_attachments_for_messages(
    chat_message_ids: list[str],
) -> dict[str, list[dict[str, str | int]]]:
    """批量读取多条消息的附件，并按 chat_message_id 分组。"""

    if not chat_message_ids:
        return {}

    placeholders = ",".join("?" for _ in chat_message_ids)
    with get_database_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT
                id,
                chat_message_id,
                page_id,
                kind,
                original_filename,
                mime_type,
                file_size,
                created_at
            FROM chat_attachments
            WHERE chat_message_id IN ({placeholders})
            ORDER BY created_at ASC, display_order ASC
            """,
            chat_message_ids,
        ).fetchall()

    attachments_by_message: dict[str, list[dict[str, str | int]]] = {
        chat_message_id: [] for chat_message_id in chat_message_ids
    }
    for row in rows:
        attachments_by_message.setdefault(row["chat_message_id"], []).append(
            row_to_chat_attachment(row)
        )

    return attachments_by_message


def attach_attachments_to_messages(
    messages: list[dict[str, object]],
) -> list[dict[str, object]]:
    """给聊天消息列表补上 attachments 字段。"""

    message_ids = [str(message["chat_message_id"]) for message in messages]
    attachments_by_message = list_chat_attachments_for_messages(message_ids)

    for message in messages:
        message["attachments"] = attachments_by_message.get(str(message["chat_message_id"]), [])

    return messages


def list_recent_image_attachments_for_prompt(
    page_id: str,
    limit: int,
    exclude_chat_message_id: str | None = None,
) -> list[dict[str, str]]:
    """读取后续追问自动带入模型的最近历史图片。"""

    parameters: list[str | int] = [page_id]
    exclude_clause = ""
    if exclude_chat_message_id is not None:
        exclude_clause = "AND chat_message_id != ?"
        parameters.append(exclude_chat_message_id)

    parameters.append(limit)
    with get_database_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT id, mime_type, file_path
            FROM (
                SELECT id, mime_type, file_path, created_at, display_order
                FROM chat_attachments
                WHERE page_id = ? AND kind = 'image' {exclude_clause}
                ORDER BY created_at DESC, display_order DESC
                LIMIT ?
            )
            ORDER BY created_at ASC, display_order ASC
            """,
            parameters,
        ).fetchall()

    return [
        {
            "attachment_id": row["id"],
            "mime_type": row["mime_type"],
            "file_path": row["file_path"],
        }
        for row in rows
    ]


def list_image_attachments_for_message(chat_message_id: str) -> list[dict[str, str]]:
    """读取某条消息自己的图片附件，用于把本轮图片加入 LLM 请求。"""

    with get_database_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, mime_type, file_path
            FROM chat_attachments
            WHERE chat_message_id = ? AND kind = 'image'
            ORDER BY display_order ASC
            """,
            (chat_message_id,),
        ).fetchall()

    return [
        {
            "attachment_id": row["id"],
            "mime_type": row["mime_type"],
            "file_path": row["file_path"],
        }
        for row in rows
    ]


def get_chat_attachment_file_row(attachment_id: str):
    """读取附件文件接口需要的附件行。"""

    with get_database_connection() as connection:
        return connection.execute(
            """
            SELECT id, original_filename, mime_type, file_path
            FROM chat_attachments
            WHERE id = ?
            """,
            (attachment_id,),
        ).fetchone()


def list_chat_attachment_paths_for_document(document_id: str) -> list[str]:
    """读取某个文档下全部聊天附件路径，用于删除文档时清理本地文件。"""

    with get_database_connection() as connection:
        rows = connection.execute(
            """
            SELECT chat_attachments.file_path
            FROM chat_attachments
            JOIN pages ON pages.id = chat_attachments.page_id
            WHERE pages.document_id = ?
            """,
            (document_id,),
        ).fetchall()

    return [row["file_path"] for row in rows]
