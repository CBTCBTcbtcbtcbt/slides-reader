"""错题本相关路由。"""

from typing import Any

from fastapi import APIRouter, HTTPException, status

from database import init_database
from repositories.wrong_questions import (
    delete_wrong_question,
    get_knowledge_tag_statistics,
    get_wrong_question_by_id,
    list_wrong_questions,
    list_wrong_questions_for_document,
    mark_as_reviewed,
)


router = APIRouter()


@router.get("/api/wrong-questions")
def read_all_wrong_questions() -> list[dict[str, Any]]:
    """获取所有错题，前端可按任务分组。"""

    init_database()
    return list_wrong_questions()


@router.get("/api/documents/{document_id}/wrong-questions")
def read_document_wrong_questions(document_id: str) -> list[dict[str, Any]]:
    """获取某任务下的所有错题。"""

    init_database()
    return list_wrong_questions_for_document(document_id)


@router.delete("/api/wrong-questions/{wrong_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_wrong_question(wrong_id: str) -> None:
    """从错题本中移除一道错题。"""

    init_database()
    if get_wrong_question_by_id(wrong_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的错题记录。",
        )

    delete_wrong_question(wrong_id)


@router.post("/api/wrong-questions/{wrong_id}/review")
def review_wrong_question(wrong_id: str) -> dict[str, str]:
    """标记错题已复习。"""

    init_database()
    if get_wrong_question_by_id(wrong_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的错题记录。",
        )

    mark_as_reviewed(wrong_id)
    return {"status": "ok"}


@router.get("/api/wrong-questions/statistics")
def read_wrong_question_statistics(document_id: str | None = None) -> list[dict[str, Any]]:
    """获取错题知识点统计，用于阶段考试加权。"""

    init_database()
    return get_knowledge_tag_statistics(document_id)
