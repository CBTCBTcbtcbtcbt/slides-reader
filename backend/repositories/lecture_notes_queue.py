"""逐页讲稿生成队列的数据访问函数。"""

from datetime import datetime, timezone
from uuid import uuid4

from database import get_database_connection


def _utc_now_text() -> str:
    """返回用于数据库记录的 UTC ISO 时间字符串。"""

    # SQLite 里这里直接存文本，便于调试时从数据库文件中阅读。
    return datetime.now(timezone.utc).isoformat()


def enqueue_pages_for_lecture_notes(pages) -> int:
    """把一组页面加入逐页讲稿待生成队列。

    参数：
        pages：包含 id、document_id、page_number 字段的页面行列表。

    返回值：
        int：本次请求处理的页面数量，包含新增和重新置为 waiting 的页面。
    """

    now = _utc_now_text()
    with get_database_connection() as connection:
        for page in pages:
            # UNIQUE(page_id) 保证同一页不会在队列中出现多次。
            # 已存在的记录会被重新置为 waiting，并更新页码和时间。
            connection.execute(
                """
                INSERT INTO lecture_notes_queue (
                    id,
                    document_id,
                    page_id,
                    page_number,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, 'waiting', ?, ?)
                ON CONFLICT(page_id) DO UPDATE SET
                    document_id = excluded.document_id,
                    page_number = excluded.page_number,
                    status = 'waiting',
                    updated_at = excluded.updated_at
                """,
                (
                    str(uuid4()),
                    page["document_id"],
                    page["id"],
                    page["page_number"],
                    now,
                    now,
                ),
            )
        connection.commit()

    return len(pages)


def dequeue_next_lecture_notes_page(document_id: str):
    """取出指定文档下一条待生成页面，并把队列记录标记为 processing。"""

    now = _utc_now_text()
    with get_database_connection() as connection:
        while True:
            queue_row = connection.execute(
                """
                SELECT
                    id,
                    page_id
                FROM lecture_notes_queue
                WHERE document_id = ? AND status = 'waiting'
                ORDER BY page_number ASC, created_at ASC
                LIMIT 1
                """,
                (document_id,),
            ).fetchone()

            if queue_row is None:
                connection.commit()
                return None

            connection.execute(
                """
                UPDATE lecture_notes_queue
                SET status = 'processing', updated_at = ?
                WHERE id = ?
                """,
                (now, queue_row["id"]),
            )

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
                    pages.lecture_notes_status,
                    pages.lecture_notes_error,
                    documents.course_summary,
                    documents.course_summary_status
                FROM pages
                JOIN documents ON documents.id = pages.document_id
                WHERE pages.id = ?
                """,
                (queue_row["page_id"],),
            ).fetchone()

            if page is not None:
                connection.commit()
                return page

            # 理论上删除文档会同步清队列；这里防御手动改库造成的孤儿队列项。
            connection.execute(
                "DELETE FROM lecture_notes_queue WHERE id = ?",
                (queue_row["id"],),
            )

    return page


def complete_lecture_notes_queue_item(page_id: str) -> None:
    """删除指定页面的队列记录，表示这页已经处理完毕。"""

    with get_database_connection() as connection:
        connection.execute(
            "DELETE FROM lecture_notes_queue WHERE page_id = ?",
            (page_id,),
        )
        connection.commit()


def reset_processing_lecture_notes_queue_items(document_id: str) -> None:
    """把指定文档卡在 processing 的队列记录恢复为 waiting。"""

    now = _utc_now_text()
    with get_database_connection() as connection:
        connection.execute(
            """
            UPDATE lecture_notes_queue
            SET status = 'waiting', updated_at = ?
            WHERE document_id = ? AND status = 'processing'
            """,
            (now, document_id),
        )
        connection.commit()


def clear_waiting_lecture_notes_queue(document_id: str) -> int:
    """清空指定文档尚未开始处理的讲稿队列。"""

    with get_database_connection() as connection:
        result = connection.execute(
            """
            DELETE FROM lecture_notes_queue
            WHERE document_id = ? AND status = 'waiting'
            """,
            (document_id,),
        )
        connection.commit()

    return result.rowcount


def count_lecture_notes_queue_by_status(document_id: str) -> dict[str, int]:
    """统计指定文档队列中 waiting 和 processing 的数量。"""

    with get_database_connection() as connection:
        rows = connection.execute(
            """
            SELECT status, COUNT(id) AS item_count
            FROM lecture_notes_queue
            WHERE document_id = ?
            GROUP BY status
            """,
            (document_id,),
        ).fetchall()

    counts = {"waiting": 0, "processing": 0}
    for row in rows:
        if row["status"] in counts:
            counts[row["status"]] = int(row["item_count"])

    return counts

