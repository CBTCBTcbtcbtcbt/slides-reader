"""讲稿文字块的数据访问和校验函数。"""

import math
import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, status

from config import (
    DEFAULT_NOTE_BLOCK_HEIGHT,
    DEFAULT_NOTE_BLOCK_WIDTH,
    DEFAULT_NOTE_BLOCK_X,
    DEFAULT_NOTE_BLOCK_Y,
    MIN_NOTE_BLOCK_HEIGHT,
    MIN_NOTE_BLOCK_WIDTH,
)
from database import get_database_connection
from schemas import NoteBlockPositionUpdateRequest


def row_to_note_block(row) -> dict[str, str | float]:
    """把 SQLite 行转换成讲稿文字块字典。"""

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


def ensure_note_block_for_ready_page(connection: sqlite3.Connection, page) -> None:
    """为已经生成讲稿的页面补充默认讲稿文字块。"""

    # 只有讲稿 ready 且正文非空的页面才需要文字块。
    if page["lecture_notes_status"] != "ready" or not page["lecture_notes"]:
        return

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
    """讲稿生成成功后同步讲稿文字块内容，并保留已有位置和尺寸。"""

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
        # 没有旧文字块时创建默认位置，保证阅读器能立即展示新讲稿。
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

    # 已有文字块时只更新内容和更新时间，不覆盖用户拖动后的布局。
    connection.execute(
        """
        UPDATE note_blocks
        SET content = ?, updated_at = ?
        WHERE page_id = ?
        """,
        (lecture_notes, now, page["id"]),
    )


def validate_note_block_position(request: NoteBlockPositionUpdateRequest) -> None:
    """校验讲稿文字块位置和尺寸是否可以保存。"""

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


def update_note_block_position(note_block_id: str, request: NoteBlockPositionUpdateRequest):
    """保存讲稿文字块拖动或缩放后的新位置。"""

    validate_note_block_position(request)

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
