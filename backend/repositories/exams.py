"""试卷、题目和答题记录的数据访问层。"""

import json
import uuid
from datetime import datetime, timezone

from database import get_database_connection


def create_exam_record(
    document_id: str,
    title: str,
    description: str | None,
    total_score: int,
    exam_status: str = "pending",
) -> dict[str, str | int | None]:
    """创建一份新的试卷记录。"""

    exam_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    with get_database_connection() as connection:
        connection.execute(
            """
            INSERT INTO exams (id, document_id, title, description, status, total_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (exam_id, document_id, title, description, exam_status, total_score, created_at),
        )

    return {
        "id": exam_id,
        "document_id": document_id,
        "title": title,
        "description": description,
        "status": exam_status,
        "total_score": total_score,
        "created_at": created_at,
    }


def update_exam_status(
    exam_id: str,
    exam_status: str,
    error_message: str | None,
) -> None:
    """更新试卷的生成状态。"""

    with get_database_connection() as connection:
        connection.execute(
            """
            UPDATE exams
            SET status = ?, error_message = ?
            WHERE id = ?
            """,
            (exam_status, error_message, exam_id),
        )


def update_exam_content(
    exam_id: str,
    title: str,
    description: str | None,
    total_score: int,
) -> None:
    """更新试卷的标题、说明和总分。"""

    with get_database_connection() as connection:
        connection.execute(
            """
            UPDATE exams
            SET title = ?, description = ?, total_score = ?
            WHERE id = ?
            """,
            (title, description, total_score, exam_id),
        )


def create_exam_question(
    exam_id: str,
    question_number: int,
    section: str,
    question_type: str,
    score: int,
    content: str,
    options: list[str] | None,
    answer: str | None,
    explanation: str | None,
    source_page: int | None = None,
    expected_type: str | None = None,
    difficulty: str | None = None,
    knowledge_tag: str | None = None,
) -> dict[str, str | int | None]:
    """创建一道试卷题目。"""

    question_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    options_json = json.dumps(options, ensure_ascii=False) if options is not None else None

    with get_database_connection() as connection:
        connection.execute(
            """
            INSERT INTO exam_questions
            (id, exam_id, question_number, section, question_type, score, content, options,
             answer, explanation, source_page, expected_type, difficulty, knowledge_tag, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                question_id,
                exam_id,
                question_number,
                section,
                question_type,
                score,
                content,
                options_json,
                answer,
                explanation,
                source_page,
                expected_type,
                difficulty,
                knowledge_tag,
                created_at,
            ),
        )

    return {
        "id": question_id,
        "exam_id": exam_id,
        "question_number": question_number,
        "section": section,
        "question_type": question_type,
        "score": score,
        "content": content,
        "options": options,
        "answer": answer,
        "explanation": explanation,
        "source_page": source_page,
        "expected_type": expected_type,
        "difficulty": difficulty,
        "knowledge_tag": knowledge_tag,
        "created_at": created_at,
    }


def get_exam_by_id(exam_id: str) -> dict[str, str | int | None] | None:
    """根据 ID 获取试卷基本信息。"""

    with get_database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM exams WHERE id = ?",
            (exam_id,),
        ).fetchone()

    if row is None:
        return None

    return dict(row)


def list_exams_for_document(document_id: str) -> list[dict[str, str | int | None]]:
    """获取某份文档下的所有试卷，并附带最近一次答题得分。"""

    with get_database_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                e.*,
                (SELECT score FROM exam_attempts
                 WHERE exam_id = e.id ORDER BY started_at DESC LIMIT 1
                ) AS latest_attempt_score
            FROM exams e
            WHERE e.document_id = ?
            ORDER BY e.created_at DESC
            """,
            (document_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def list_all_exams() -> list[dict[str, str | int | None]]:
    """获取所有试卷列表，并附带最近一次答题得分。"""

    with get_database_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                e.*,
                (SELECT score FROM exam_attempts
                 WHERE exam_id = e.id ORDER BY started_at DESC LIMIT 1
                ) AS latest_attempt_score
            FROM exams e
            ORDER BY e.created_at DESC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def get_exam_questions(exam_id: str) -> list[dict[str, str | int | None]]:
    """获取某份试卷的所有题目。"""

    with get_database_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM exam_questions
            WHERE exam_id = ?
            ORDER BY section ASC, question_number ASC
            """,
            (exam_id,),
        ).fetchall()

    questions = []
    for row in rows:
        question = dict(row)
        if question.get("options"):
            question["options"] = json.loads(question["options"])
        else:
            question["options"] = None
        questions.append(question)

    return questions


def get_exam_with_questions(exam_id: str) -> dict[str, object] | None:
    """获取一份完整试卷（含题目）。"""

    exam = get_exam_by_id(exam_id)
    if exam is None:
        return None

    questions = get_exam_questions(exam_id)
    return {
        **exam,
        "questions": questions,
    }


def delete_exam(exam_id: str) -> None:
    """删除试卷及其题目和答题记录。"""

    with get_database_connection() as connection:
        connection.execute("DELETE FROM wrong_questions WHERE exam_id = ?", (exam_id,))
        connection.execute("DELETE FROM exam_attempts WHERE exam_id = ?", (exam_id,))
        connection.execute("DELETE FROM exam_questions WHERE exam_id = ?", (exam_id,))
        connection.execute("DELETE FROM exams WHERE id = ?", (exam_id,))


def create_exam_attempt(
    exam_id: str,
    answers: dict[str, str],
    score: int | None = None,
) -> dict[str, str | int | None]:
    """创建一次答题记录。"""

    attempt_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    answers_json = json.dumps(answers, ensure_ascii=False)

    with get_database_connection() as connection:
        connection.execute(
            """
            INSERT INTO exam_attempts (id, exam_id, started_at, finished_at, score, answers)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (attempt_id, exam_id, started_at, None, score, answers_json),
        )

    return {
        "id": attempt_id,
        "exam_id": exam_id,
        "started_at": started_at,
        "finished_at": None,
        "score": score,
        "answers": answers,
    }


def get_exam_attempt_by_id(exam_id: str, attempt_id: str) -> dict[str, str | int | None] | None:
    """根据试卷 ID 和答题记录 ID 获取一次答题记录。"""

    with get_database_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM exam_attempts
            WHERE id = ? AND exam_id = ?
            """,
            (attempt_id, exam_id),
        ).fetchone()

    if row is None:
        return None

    attempt = dict(row)
    if attempt.get("answers"):
        attempt["answers"] = json.loads(attempt["answers"])
    return attempt


def list_exam_attempts(exam_id: str) -> list[dict[str, str | int | None]]:
    """获取某份试卷的所有答题记录。"""

    with get_database_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM exam_attempts WHERE exam_id = ? ORDER BY started_at DESC",
            (exam_id,),
        ).fetchall()

    attempts = []
    for row in rows:
        attempt = dict(row)
        if attempt.get("answers"):
            attempt["answers"] = json.loads(attempt["answers"])
        attempts.append(attempt)

    return attempts
