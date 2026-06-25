"""阶段考试数据访问层。"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from database import get_database_connection


def create_phase_exam_record(
    name: str,
    document_ids: list[str],
    difficulty: str,
    phase_exam_status: str = "pending",
) -> dict[str, str | int | None]:
    """创建阶段考试记录。"""

    phase_exam_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    document_ids_json = json.dumps(document_ids, ensure_ascii=False)

    with get_database_connection() as connection:
        connection.execute(
            """
            INSERT INTO phase_exams (id, name, document_ids, difficulty, exam_id, status, error_message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (phase_exam_id, name, document_ids_json, difficulty, None, phase_exam_status, None, created_at),
        )

    return {
        "id": phase_exam_id,
        "name": name,
        "document_ids": document_ids,
        "difficulty": difficulty,
        "exam_id": None,
        "status": phase_exam_status,
        "error_message": None,
        "created_at": created_at,
    }


def update_phase_exam_exam_id(phase_exam_id: str, exam_id: str) -> None:
    """更新阶段考试关联的 exam_id。"""

    with get_database_connection() as connection:
        connection.execute(
            "UPDATE phase_exams SET exam_id = ? WHERE id = ?",
            (exam_id, phase_exam_id),
        )


def update_phase_exam_status(
    phase_exam_id: str,
    phase_exam_status: str,
    error_message: str | None,
) -> None:
    """更新阶段考试状态。"""

    with get_database_connection() as connection:
        connection.execute(
            "UPDATE phase_exams SET status = ?, error_message = ? WHERE id = ?",
            (phase_exam_status, error_message, phase_exam_id),
        )


def get_phase_exam_by_id(phase_exam_id: str) -> dict[str, Any] | None:
    """根据 ID 获取阶段考试记录。"""

    with get_database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM phase_exams WHERE id = ?",
            (phase_exam_id,),
        ).fetchone()

    if row is None:
        return None

    item = dict(row)
    item["document_ids"] = json.loads(item["document_ids"])
    return item


def list_phase_exams() -> list[dict[str, Any]]:
    """获取所有阶段考试列表。"""

    with get_database_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM phase_exams ORDER BY created_at DESC"
        ).fetchall()

    results = []
    for row in rows:
        item = dict(row)
        item["document_ids"] = json.loads(item["document_ids"])
        results.append(item)

    return results


def delete_phase_exam(phase_exam_id: str) -> None:
    """删除阶段考试记录，并同步清理它关联的普通试卷数据。"""

    with get_database_connection() as connection:
        phase_exam = connection.execute(
            "SELECT exam_id FROM phase_exams WHERE id = ?",
            (phase_exam_id,),
        ).fetchone()
        linked_exam_id = phase_exam["exam_id"] if phase_exam is not None else None

        if linked_exam_id is not None:
            # 阶段考试底层复用 exams / exam_questions / exam_attempts / wrong_questions 表；
            # 删除阶段考试时必须一起清理这些记录，避免列表里留下不可追踪的孤儿试卷。
            connection.execute("DELETE FROM wrong_questions WHERE exam_id = ?", (linked_exam_id,))
            connection.execute("DELETE FROM exam_attempts WHERE exam_id = ?", (linked_exam_id,))
            connection.execute("DELETE FROM exam_questions WHERE exam_id = ?", (linked_exam_id,))
            connection.execute("DELETE FROM exams WHERE id = ?", (linked_exam_id,))

        connection.execute("DELETE FROM phase_exams WHERE id = ?", (phase_exam_id,))
