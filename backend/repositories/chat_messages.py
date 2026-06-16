"""当前页问答消息的数据访问函数。"""

from datetime import UTC, datetime
from uuid import uuid4

from config import PAGE_CHAT_HISTORY_LIMIT
from database import get_database_connection


def row_to_chat_message(row) -> dict[str, str]:
    """把 SQLite 行转换成前端使用的聊天消息字典。"""

    # 数据库内部字段 id 在前端容易和其他对象混淆，所以返回 chat_message_id。
    return {
        "chat_message_id": row["id"],
        "page_id": row["page_id"],
        "role": row["role"],
        "content": row["content"],
        "created_at": row["created_at"],
    }


def list_chat_messages_for_page(page_id: str) -> list[dict[str, str]]:
    """读取某一页的全部问答历史。"""

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
    """批量读取多个页面的问答历史，并按 page_id 分组。"""

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
    """读取构造问答 prompt 时使用的最近聊天历史。"""

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
    """向 chat_messages 表写入一条问答消息。"""

    # role 只允许这两个值，防止后续 prompt 构造出现未知身份。
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
