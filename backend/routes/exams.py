"""试卷生成、查看和答题路由。"""

import logging
import threading
from typing import Any

from fastapi import APIRouter, HTTPException, status

from database import init_database
from exam_service import generate_exam
from repositories.documents import document_exists
from repositories.exams import (
    create_exam_attempt,
    delete_exam,
    get_exam_attempt_by_id,
    get_exam_by_id,
    get_exam_questions,
    get_exam_with_questions,
    list_all_exams,
    list_exam_attempts,
    list_exams_for_document,
)
from schemas import ExamAnswerRequest, ExamGenerateRequest


router = APIRouter()
logger = logging.getLogger(__name__)


def _grade_answer(question: dict[str, Any], user_answer: str) -> bool:
    """判断用户答案是否正确。"""

    q_type = question.get("question_type")
    correct_answer = str(question.get("answer", "")).strip()
    user_answer = user_answer.strip()

    if not user_answer:
        return False

    if q_type == "choice":
        return user_answer.upper() == correct_answer.upper()

    if q_type == "fill_in":
        expected_type = question.get("expected_type")
        if expected_type == "number":
            try:
                user_num = float(user_answer)
                correct_num = float(correct_answer)
                return user_num == correct_num
            except ValueError:
                return False
        return user_answer == correct_answer

    return user_answer == correct_answer


def _build_attempt_result(
    exam: dict[str, Any],
    attempt: dict[str, Any],
) -> dict[str, Any]:
    """根据试卷题目和一次答题记录构造可返回给前端的判分结果。"""

    answers = attempt.get("answers") or {}
    questions = exam.get("questions", [])
    total_score = 0
    max_score = 0
    question_results = []

    for question in questions:
        question_score = int(question["score"])
        max_score += question_score
        question_id = str(question["id"])
        user_answer = str(answers.get(question_id, "")).strip()
        is_correct = _grade_answer(question, user_answer)
        awarded_score = question_score if is_correct else 0

        if is_correct:
            total_score += question_score

        question_results.append(
            {
                "question_id": question_id,
                "user_answer": user_answer,
                "correct_answer": question.get("answer"),
                "is_correct": is_correct,
                "score": awarded_score,
                "max_score": question_score,
            }
        )

    return {
        "status": "ok",
        "attempt": attempt,
        "total_score": total_score,
        "max_score": max_score,
        "questions": questions,
        "question_results": question_results,
    }


@router.get("/api/exams")
def list_exams() -> list[dict[str, str | int | None]]:
    """返回所有试卷列表。"""

    init_database()
    return list_all_exams()


@router.get("/api/documents/{document_id}/exams")
def list_document_exams(document_id: str) -> list[dict[str, str | int | None]]:
    """返回某份文档下的所有试卷。"""

    init_database()
    if not document_exists(document_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的文档。",
        )

    return list_exams_for_document(document_id)


@router.post("/api/documents/{document_id}/exams/generate")
def generate_exam_for_document(
    document_id: str,
    request: ExamGenerateRequest | None = None,
) -> dict[str, str]:
    """为指定文档生成一份新试卷。"""

    init_database()
    if not document_exists(document_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的文档。",
        )

    difficulty = "medium"
    if request is not None and request.difficulty:
        difficulty = request.difficulty

    # 先创建 pending 记录，拿到 exam_id 后在线程中异步生成，避免阻塞 FastAPI 事件循环。
    from repositories.exams import create_exam_record

    exam_record = create_exam_record(
        document_id=document_id,
        title="生成中...",
        description=None,
        total_score=100,
        exam_status="pending",
    )
    exam_id = exam_record["id"]

    threading.Thread(
        target=_generate_exam_safely,
        args=(exam_id, document_id, difficulty),
        daemon=True,
    ).start()

    return {"status": "processing", "exam_id": exam_id}


def _generate_exam_safely(exam_id: str, document_id: str, difficulty: str = "medium") -> None:
    """后台任务包装：确保异常被捕获并更新状态。"""

    try:
        generate_exam(document_id=document_id, exam_id=exam_id, difficulty=difficulty)
    except Exception as error:
        logger.exception("试卷后台生成任务失败：exam_id=%s document_id=%s", exam_id, document_id)

        # 正常路径下 service 会自己写入 failed；这里作为最后防线，处理 service 还没来得及写状态就崩溃的情况。
        from repositories.exams import update_exam_status

        update_exam_status(
            exam_id=exam_id,
            exam_status="failed",
            error_message=f"试卷生成失败：{error}",
        )


@router.get("/api/exams/{exam_id}")
def read_exam(exam_id: str, include_questions: bool = True) -> dict[str, Any]:
    """返回试卷详情，可选是否包含题目与答案。"""

    init_database()
    if include_questions:
        exam = get_exam_with_questions(exam_id)
    else:
        exam = get_exam_by_id(exam_id)

    if exam is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的试卷。",
        )

    return exam


@router.get("/api/exams/{exam_id}/questions")
def read_exam_questions(exam_id: str, include_answer: bool = True) -> list[dict[str, Any]]:
    """返回试卷题目，可选是否包含答案。"""

    init_database()
    if get_exam_by_id(exam_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的试卷。",
        )

    questions = get_exam_questions(exam_id)
    if not include_answer:
        for question in questions:
            question.pop("answer", None)
            question.pop("explanation", None)

    return questions


@router.post("/api/exams/{exam_id}/attempts")
def submit_exam_attempt(exam_id: str, request: ExamAnswerRequest) -> dict[str, Any]:
    """提交一次答题记录。"""

    init_database()
    exam = get_exam_with_questions(exam_id)
    if exam is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的试卷。",
        )

    if exam["status"] != "ready":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="试卷尚未生成完成，无法答题。",
        )

    answers = request.answers
    wrong_entries = []

    from repositories.wrong_questions import create_wrong_question

    for question in exam.get("questions", []):
        qid = question["id"]
        user_answer = answers.get(qid, "").strip()
        is_correct = _grade_answer(question, user_answer)

        if not is_correct:
            wrong_entries.append({
                "question_id": qid,
                "user_answer": user_answer,
            })

    draft_attempt = {"answers": answers}
    draft_result = _build_attempt_result(exam, draft_attempt)

    attempt = create_exam_attempt(
        exam_id=exam_id,
        answers=answers,
        score=draft_result["total_score"],
    )

    # 记录错题
    for entry in wrong_entries:
        create_wrong_question(
            question_id=entry["question_id"],
            exam_id=exam_id,
            attempt_id=attempt["id"],
            user_answer=entry["user_answer"],
        )

    return _build_attempt_result(exam, attempt)


@router.get("/api/exams/{exam_id}/attempts")
def read_exam_attempts(exam_id: str) -> list[dict[str, Any]]:
    """返回某份试卷的所有答题记录。"""

    init_database()
    if get_exam_by_id(exam_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的试卷。",
        )

    return list_exam_attempts(exam_id)


@router.get("/api/exams/{exam_id}/attempts/{attempt_id}/result")
def read_exam_attempt_result(exam_id: str, attempt_id: str) -> dict[str, Any]:
    """返回一次答题记录的完整判分结果，供结果页刷新后恢复。"""

    init_database()
    exam = get_exam_with_questions(exam_id)
    if exam is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的试卷。",
        )

    attempt = get_exam_attempt_by_id(exam_id=exam_id, attempt_id=attempt_id)
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的答题记录。",
        )

    return _build_attempt_result(exam, attempt)


@router.delete("/api/exams/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_exam(exam_id: str) -> None:
    """删除试卷及其关联数据。"""

    init_database()
    if get_exam_by_id(exam_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的试卷。",
        )

    delete_exam(exam_id)
