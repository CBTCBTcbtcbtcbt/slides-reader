"""页面、当前页问答和讲稿文字块路由。"""

from fastapi import APIRouter

from generation_service import answer_page_question
from repositories.note_blocks import update_note_block_position as update_note_block_position_record
from schemas import NoteBlockPositionUpdateRequest, PageChatRequest


router = APIRouter()


@router.post("/api/pages/{page_id}/chat")
def chat_with_page(page_id: str, request: PageChatRequest) -> dict[str, object]:
    """围绕当前页面向 LLM 提问，并保存问答历史。"""

    return answer_page_question(page_id=page_id, question=request.question)


@router.patch("/api/note-blocks/{note_block_id}")
def update_note_block_position(
    note_block_id: str,
    request: NoteBlockPositionUpdateRequest,
) -> dict[str, str | float]:
    """保存讲稿文字块拖动或缩放后的新位置。"""

    return update_note_block_position_record(note_block_id=note_block_id, request=request)
