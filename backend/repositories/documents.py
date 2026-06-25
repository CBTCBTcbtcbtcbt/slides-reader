"""文档表的数据访问函数。"""

import json
from datetime import datetime, timezone

from fastapi import HTTPException, status

from database import get_database_connection


def row_to_document(row) -> dict[str, str | int | bool | None]:
    """把 SQLite 查询结果转换成前端可直接使用的文档字典。"""

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


def list_documents_with_page_count() -> list[dict[str, str | int | bool | None]]:
    """按创建时间倒序返回文档列表。"""

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

    return [row_to_document(row) for row in rows]


def get_document_with_page_count(document_id: str) -> dict[str, str | int | bool | None] | None:
    """查询单个文档，并附带页面数量。"""

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

    return None if row is None else row_to_document(row)


def get_document_file_row(document_id: str):
    """读取文档标题和 PDF 文件路径。"""

    with get_database_connection() as connection:
        return connection.execute(
            """
            SELECT title, file_path
            FROM documents
            WHERE id = ?
            """,
            (document_id,),
        ).fetchone()


def get_document_for_status(document_id: str):
    """读取状态接口需要的文档字段。"""

    with get_database_connection() as connection:
        return connection.execute(
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


def get_document_ready_for_lecture_notes(document_id: str):
    """读取重新生成整份讲稿需要的文档信息。"""

    with get_database_connection() as connection:
        document = connection.execute(
            """
            SELECT
                documents.id,
                documents.title,
                documents.status,
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

    if document["status"] != "ready":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文档还没有解析完成，无法生成逐页讲稿。",
        )

    if document["course_summary_status"] != "ready" or not document["course_summary"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="课程简介还没有生成成功，无法生成逐页讲稿。",
        )

    if document["page_count"] == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前文档还没有页面记录，无法生成逐页讲稿。",
        )

    return document


def document_exists(document_id: str) -> bool:
    """判断文档是否存在。"""

    with get_database_connection() as connection:
        row = connection.execute(
            "SELECT id FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()

    return row is not None


def count_document_pages(document_id: str) -> int:
    """统计某个文档的页面数量。"""

    with get_database_connection() as connection:
        row = connection.execute(
            "SELECT COUNT(id) AS page_count FROM pages WHERE document_id = ?",
            (document_id,),
        ).fetchone()

    return int(row["page_count"])


def create_document_record(
    document_id: str,
    title: str,
    file_path: str,
    document_status: str,
) -> None:
    """创建上传后的文档记录。"""

    created_at = datetime.now(timezone.utc).isoformat()

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
                title,
                file_path,
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


def update_document_status(
    document_id: str,
    document_status: str,
    error_message: str | None = None,
) -> None:
    """更新文档处理状态。"""

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
    """更新文档课程简介生成状态和结果。"""

    with get_database_connection() as connection:
        if course_summary is None:
            # 生成中或失败时不覆盖旧简介，避免重试失败后丢失可用内容。
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


def set_lecture_notes_paused(document_id: str, paused: bool) -> None:
    """更新某个文档的逐页讲稿暂停状态。"""

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
    """读取某个文档是否已经暂停逐页讲稿生成。"""

    with get_database_connection() as connection:
        document = connection.execute(
            "SELECT lecture_notes_paused FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()

    return bool(document["lecture_notes_paused"]) if document is not None else False


def reset_document_lecture_notes_status(document_id: str) -> None:
    """把指定文档的所有页面讲稿状态重置为等待生成。"""

    with get_database_connection() as connection:
        # 重跑整份讲稿时清除暂停状态，确保后台任务能继续处理。
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


def rename_document_record(document_id: str, next_title: str):
    """更新文档显示标题并返回更新后的文档对象。"""

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


def delete_document_records(document_id: str) -> None:
    """删除某个文档相关的数据库记录。"""

    with get_database_connection() as connection:
        exam_id_rows = connection.execute(
            "SELECT id FROM exams WHERE document_id = ?",
            (document_id,),
        ).fetchall()
        exam_ids = {row["id"] for row in exam_id_rows}

        phase_exam_rows = connection.execute(
            "SELECT id, document_ids, exam_id FROM phase_exams"
        ).fetchall()
        for phase_exam in phase_exam_rows:
            try:
                phase_document_ids = json.loads(phase_exam["document_ids"])
            except json.JSONDecodeError:
                phase_document_ids = []

            if document_id in phase_document_ids or phase_exam["exam_id"] in exam_ids:
                connection.execute(
                    "DELETE FROM phase_exams WHERE id = ?",
                    (phase_exam["id"],),
                )

        connection.execute(
            "DELETE FROM lecture_notes_queue WHERE document_id = ?",
            (document_id,),
        )
        connection.execute(
            """
            DELETE FROM chat_attachments
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
        connection.execute(
            """
            DELETE FROM wrong_questions
            WHERE exam_id IN (
                SELECT id
                FROM exams
                WHERE document_id = ?
            )
            """,
            (document_id,),
        )
        connection.execute(
            """
            DELETE FROM exam_attempts
            WHERE exam_id IN (
                SELECT id
                FROM exams
                WHERE document_id = ?
            )
            """,
            (document_id,),
        )
        connection.execute(
            """
            DELETE FROM exam_questions
            WHERE exam_id IN (
                SELECT id
                FROM exams
                WHERE document_id = ?
            )
            """,
            (document_id,),
        )
        connection.execute("DELETE FROM exams WHERE document_id = ?", (document_id,))
        connection.execute("DELETE FROM pages WHERE document_id = ?", (document_id,))
        connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        connection.commit()
