"""页面表的数据访问函数。"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from database import get_database_connection
from repositories.chat_messages import list_chat_messages_for_pages
from repositories.note_blocks import ensure_note_block_for_ready_page, sync_note_block_content_for_page


def build_page_image_url(document_id: str, page_number: int) -> str:
    """生成页面截图的后端访问 URL。"""

    return f"/api/documents/{document_id}/pages/{page_number}/image"


def row_to_page(row) -> dict[str, Any]:
    """把 SQLite 查询结果转换成页面字典。"""

    image_path = row["image_path"]

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


def create_page_record(
    document_id: str,
    page_number: int,
    text: str,
    image_path: Path | None,
    page_status: str,
    error_message: str | None = None,
) -> None:
    """创建或替换单页解析记录。"""

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


def update_page_lecture_notes_status(
    document_id: str,
    page_number: int,
    lecture_notes_status: str,
    lecture_notes: str | None = None,
    error_message: str | None = None,
) -> None:
    """更新单页讲稿生成状态和结果。"""

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


def get_document_status_page_rows(document_id: str):
    """读取状态接口需要的页面状态行。"""

    with get_database_connection() as connection:
        return connection.execute(
            """
            SELECT
                pages.id,
                pages.page_number,
                pages.status,
                pages.error_message,
                pages.lecture_notes,
                CASE
                    WHEN lecture_notes_queue.status = 'waiting' THEN 'pending'
                    WHEN lecture_notes_queue.status = 'processing' THEN 'processing'
                    ELSE pages.lecture_notes_status
                END AS lecture_notes_status,
                pages.lecture_notes_error
            FROM pages
            LEFT JOIN lecture_notes_queue ON lecture_notes_queue.page_id = pages.id
            WHERE pages.document_id = ?
            ORDER BY pages.page_number ASC
            """,
            (document_id,),
        ).fetchall()


def list_document_pages_with_blocks_and_chat(document_id: str) -> list[dict[str, Any]]:
    """返回某个文档的所有页面、讲稿文字块和问答历史。"""

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
            WHERE pages.document_id = ?
            ORDER BY page_number ASC
            """,
            (document_id,),
        ).fetchall()

        # 历史数据可能已有 ready 讲稿但缺少 note_blocks，这里读取时补齐。
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
                CASE
                    WHEN lecture_notes_queue.status = 'waiting' THEN 'pending'
                    WHEN lecture_notes_queue.status = 'processing' THEN 'processing'
                    ELSE pages.lecture_notes_status
                END AS lecture_notes_status,
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
            LEFT JOIN lecture_notes_queue ON lecture_notes_queue.page_id = pages.id
            WHERE pages.document_id = ?
            ORDER BY pages.page_number ASC
            """,
            (document_id,),
        ).fetchall()

    page_items = [row_to_page(row) for row in rows]
    chat_messages_by_page = list_chat_messages_for_pages([page["page_id"] for page in page_items])

    for page_item in page_items:
        page_item["chat_messages"] = chat_messages_by_page.get(page_item["page_id"], [])

    return page_items


def get_page_image_row(document_id: str, page_number: int):
    """读取页面截图接口需要的页面行。"""

    with get_database_connection() as connection:
        return connection.execute(
            """
            SELECT image_path
            FROM pages
            WHERE document_id = ? AND page_number = ?
            """,
            (document_id, page_number),
        ).fetchone()


def get_page_context_for_chat(page_id: str):
    """读取当前页问答构造 prompt 所需的上下文。"""

    with get_database_connection() as connection:
        page = connection.execute(
            """
            SELECT
                pages.id AS page_id,
                pages.document_id,
                pages.page_number,
                pages.text,
                pages.lecture_notes,
                documents.title AS document_title,
                documents.course_summary
            FROM pages
            JOIN documents ON documents.id = pages.document_id
            WHERE pages.id = ?
            """,
            (page_id,),
        ).fetchone()

    if page is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的页面。",
        )

    return page


def list_pages_for_lecture_notes(document_id: str):
    """读取需要生成讲稿的页面列表。"""

    with get_database_connection() as connection:
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
                lecture_notes_status,
                lecture_notes_error
            FROM pages
            WHERE document_id = ?
            ORDER BY page_number ASC
            """,
            (document_id,),
        ).fetchall()

    return pages


def list_all_pages_for_lecture_notes_queue(document_id: str):
    """读取指定文档所有页面，用于重新生成全部讲稿时入队。"""

    with get_database_connection() as connection:
        return connection.execute(
            """
            SELECT
                id,
                document_id,
                page_number
            FROM pages
            WHERE document_id = ?
            ORDER BY page_number ASC
            """,
            (document_id,),
        ).fetchall()


def list_pages_without_lecture_notes_for_queue(document_id: str):
    """读取还没有可用讲稿且尚未入队的页面，用于补齐剩余讲稿队列。"""

    with get_database_connection() as connection:
        return connection.execute(
            """
            SELECT
                pages.id,
                pages.document_id,
                pages.page_number
            FROM pages
            LEFT JOIN lecture_notes_queue ON lecture_notes_queue.page_id = pages.id
            WHERE pages.document_id = ?
              AND (pages.lecture_notes IS NULL OR TRIM(pages.lecture_notes) = '')
              AND lecture_notes_queue.id IS NULL
            ORDER BY pages.page_number ASC
            """,
            (document_id,),
        ).fetchall()


def get_page_for_lecture_notes(document_id: str, page_number: int):
    """按文档 ID 和页码读取单页讲稿生成上下文。"""

    with get_database_connection() as connection:
        page = connection.execute(
            """
            SELECT
                pages.id,
                pages.document_id,
                pages.page_number,
                pages.text,
                pages.image_path,
                pages.status,
                pages.error_message,
                documents.course_summary,
                documents.course_summary_status
            FROM pages
            JOIN documents ON documents.id = pages.document_id
            WHERE pages.document_id = ? AND pages.page_number = ?
            """,
            (document_id, page_number),
        ).fetchone()

    if page is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的页面。",
        )

    if page["course_summary_status"] != "ready" or not page["course_summary"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="课程简介还没有生成成功，无法生成本页讲稿。",
        )

    return page


def get_page_for_lecture_notes_by_id(page_id: str):
    """按页面 ID 读取单页讲稿生成上下文。"""

    with get_database_connection() as connection:
        page = connection.execute(
            """
            SELECT
                pages.id,
                pages.document_id,
                pages.page_number,
                pages.text,
                pages.image_path,
                pages.status,
                pages.error_message,
                documents.course_summary,
                documents.course_summary_status
            FROM pages
            JOIN documents ON documents.id = pages.document_id
            WHERE pages.id = ?
            """,
            (page_id,),
        ).fetchone()

    if page is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的页面。",
        )

    if page["course_summary_status"] != "ready" or not page["course_summary"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="课程简介还没有生成成功，无法生成本页讲稿。",
        )

    return page


def list_page_image_paths_for_document(document_id: str) -> list[str]:
    """读取某个文档所有页面截图路径。"""

    with get_database_connection() as connection:
        rows = connection.execute(
            """
            SELECT image_path
            FROM pages
            WHERE document_id = ? AND image_path IS NOT NULL
            """,
            (document_id,),
        ).fetchall()

    return [row["image_path"] for row in rows if row["image_path"]]
