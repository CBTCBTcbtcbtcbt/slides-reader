"""错题本数据访问层。"""

import json
import uuid
from datetime import datetime, timezone

from database import get_database_connection


def create_wrong_question(
    question_id: str,
    exam_id: str,
    attempt_id: str,
    user_answer: str | None,
) -> dict[str, str | int | None]:
    """记录一道错题。"""

    wrong_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    with get_database_connection() as connection:
        connection.execute(
            """
            INSERT INTO wrong_questions (id, question_id, exam_id, attempt_id, user_answer, created_at, reviewed)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (wrong_id, question_id, exam_id, attempt_id, user_answer, created_at, 0),
        )

    return {
        "id": wrong_id,
        "question_id": question_id,
        "exam_id": exam_id,
        "attempt_id": attempt_id,
        "user_answer": user_answer,
        "created_at": created_at,
        "reviewed": 0,
    }


def delete_wrong_question(wrong_id: str) -> None:
    """从错题本中移除一道错题。"""

    with get_database_connection() as connection:
        connection.execute("DELETE FROM wrong_questions WHERE id = ?", (wrong_id,))


def list_wrong_questions() -> list[dict[str, str | int | None]]:
    """获取所有错题，按任务分组所需的基础列表。"""

    with get_database_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                wrong_questions.*,
                exam_questions.content AS question_content,
                exam_questions.options AS question_options,
                exam_questions.answer AS correct_answer,
                exam_questions.explanation AS explanation,
                exam_questions.question_type,
                exam_questions.score,
                exam_questions.source_page,
                exam_questions.knowledge_tag,
                documents.id AS document_id,
                documents.title AS document_title
            FROM wrong_questions
            JOIN exam_questions ON exam_questions.id = wrong_questions.question_id
            JOIN exams ON exams.id = wrong_questions.exam_id
            JOIN documents ON documents.id = exams.document_id
            ORDER BY documents.created_at DESC, wrong_questions.created_at DESC
            """
        ).fetchall()

    results = []
    for row in rows:
        item = dict(row)
        if item.get("question_options"):
            item["question_options"] = json.loads(item["question_options"])
        results.append(item)

    return results


def list_wrong_questions_for_document(document_id: str) -> list[dict[str, str | int | None]]:
    """获取某任务下的所有错题。"""

    with get_database_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                wrong_questions.*,
                exam_questions.content AS question_content,
                exam_questions.options AS question_options,
                exam_questions.answer AS correct_answer,
                exam_questions.explanation AS explanation,
                exam_questions.question_type,
                exam_questions.score,
                exam_questions.source_page,
                exam_questions.knowledge_tag
            FROM wrong_questions
            JOIN exam_questions ON exam_questions.id = wrong_questions.question_id
            JOIN exams ON exams.id = wrong_questions.exam_id
            WHERE exams.document_id = ?
            ORDER BY wrong_questions.created_at DESC
            """,
            (document_id,),
        ).fetchall()

    results = []
    for row in rows:
        item = dict(row)
        if item.get("question_options"):
            item["question_options"] = json.loads(item["question_options"])
        results.append(item)

    return results


def mark_as_reviewed(wrong_id: str) -> None:
    """标记错题已复习。"""

    with get_database_connection() as connection:
        connection.execute(
            "UPDATE wrong_questions SET reviewed = 1 WHERE id = ?",
            (wrong_id,),
        )


def get_wrong_question_by_id(wrong_id: str) -> dict[str, str | int | None] | None:
    """根据 ID 获取错题记录。"""

    with get_database_connection() as connection:
        row = connection.execute(
            """
            SELECT
                wrong_questions.*,
                exam_questions.content AS question_content,
                exam_questions.options AS question_options,
                exam_questions.answer AS correct_answer,
                exam_questions.explanation AS explanation,
                exam_questions.question_type,
                exam_questions.score,
                exam_questions.source_page,
                exam_questions.knowledge_tag,
                documents.id AS document_id
            FROM wrong_questions
            JOIN exam_questions ON exam_questions.id = wrong_questions.question_id
            JOIN exams ON exams.id = wrong_questions.exam_id
            JOIN documents ON documents.id = exams.document_id
            WHERE wrong_questions.id = ?
            """,
            (wrong_id,),
        ).fetchone()

    if row is None:
        return None

    item = dict(row)
    if item.get("question_options"):
        item["question_options"] = json.loads(item["question_options"])
    return item


def get_knowledge_tag_statistics(document_id: str | None = None) -> list[dict[str, str | int]]:
    """统计错题知识点分布，用于阶段考试加权。

    参数：
        document_id：可选，只统计某个任务的错题；为 None 则统计全部。

    返回值：
        每个知识点标签的错题数量列表，按数量降序排列。
    """

    query = """
        SELECT exam_questions.knowledge_tag, COUNT(*) AS wrong_count
        FROM wrong_questions
        JOIN exam_questions ON exam_questions.id = wrong_questions.question_id
        JOIN exams ON exams.id = wrong_questions.exam_id
    """
    params: tuple = ()
    if document_id is not None:
        query += " WHERE exams.document_id = ?"
        params = (document_id,)
    query += " GROUP BY exam_questions.knowledge_tag ORDER BY wrong_count DESC"

    with get_database_connection() as connection:
        rows = connection.execute(query, params).fetchall()

    return [dict(row) for row in rows]
