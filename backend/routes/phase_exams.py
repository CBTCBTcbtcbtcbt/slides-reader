"""阶段考试相关路由。"""

import logging
import threading
from typing import Any

from fastapi import APIRouter, HTTPException, status

from database import init_database
from phase_exam_service import generate_phase_exam
from repositories.phase_exams import (
    delete_phase_exam,
    get_phase_exam_by_id,
    list_phase_exams,
)
from schemas import PhaseExamGenerateRequest


router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/phase-exams")
def read_phase_exams() -> list[dict[str, Any]]:
    """返回所有阶段考试列表。"""

    init_database()
    return list_phase_exams()


@router.post("/api/phase-exams/generate")
def create_phase_exam(request: PhaseExamGenerateRequest) -> dict[str, Any]:
    """创建阶段考试，在线程中异步生成。"""

    init_database()
    if len(request.document_ids) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少需要选择一份课件。",
        )

    from repositories.phase_exams import create_phase_exam_record

    phase_exam_record = create_phase_exam_record(
        name=request.name,
        document_ids=request.document_ids,
        difficulty=request.difficulty,
        phase_exam_status="processing",
    )
    phase_exam_id = phase_exam_record["id"]

    threading.Thread(
        target=_generate_phase_exam_safely,
        args=(phase_exam_id, request.document_ids, request.name, request.difficulty),
        daemon=True,
    ).start()

    return {
        "status": "processing",
        "phase_exam_id": phase_exam_id,
        "exam_id": None,
    }


def _generate_phase_exam_safely(
    phase_exam_id: str,
    document_ids: list[str],
    name: str,
    difficulty: str,
) -> None:
    """后台任务包装：确保异常被捕获并更新状态。"""

    try:
        generate_phase_exam(
            document_ids=document_ids,
            name=name,
            difficulty=difficulty,
            phase_exam_id=phase_exam_id,
        )
    except Exception as error:
        logger.exception("阶段考试后台生成任务失败：phase_exam_id=%s", phase_exam_id)

        # 正常路径下 service 会自己写入 failed；这里作为最后防线，处理 service 还没来得及写状态就崩溃的情况。
        from repositories.phase_exams import update_phase_exam_status

        update_phase_exam_status(
            phase_exam_id=phase_exam_id,
            phase_exam_status="failed",
            error_message=f"阶段考试生成失败：{error}",
        )


@router.get("/api/phase-exams/{phase_exam_id}")
def read_phase_exam(phase_exam_id: str) -> dict[str, Any]:
    """返回阶段考试详情。"""

    init_database()
    phase_exam = get_phase_exam_by_id(phase_exam_id)
    if phase_exam is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的阶段考试。",
        )

    return phase_exam


@router.delete("/api/phase-exams/{phase_exam_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_phase_exam(phase_exam_id: str) -> None:
    """删除阶段考试记录。"""

    init_database()
    if get_phase_exam_by_id(phase_exam_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的阶段考试。",
        )

    delete_phase_exam(phase_exam_id)
