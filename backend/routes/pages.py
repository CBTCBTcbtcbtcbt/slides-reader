"""页面、当前页问答和讲稿文字块路由。"""

import json

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from starlette.datastructures import UploadFile as StarletteUploadFile

from generation_service import answer_page_question, stream_page_question
from repositories.chat_attachments import ChatAttachmentUpload
from repositories.chat_attachments import (
    get_chat_attachment_file_row,
    normalize_attachment_uploads,
    resolve_chat_attachment_path,
    ensure_chat_attachment_file_is_safe,
)
from repositories.note_blocks import update_note_block_position as update_note_block_position_record
from schemas import NoteBlockPositionUpdateRequest, PageChatRequest


router = APIRouter()


async def parse_page_chat_payload(request: Request) -> tuple[str, list[ChatAttachmentUpload]]:
    """把 JSON 或 multipart 当前页问答请求解析成统一参数。

    参数：
        request：FastAPI 提供的原始请求对象。

    返回值：
        tuple：第一个值是问题文本，第二个值是已校验的图片附件列表。
    """

    # multipart/form-data 用于带图片的请求；JSON 用于没有附件的旧请求。
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form_data = await request.form()
        raw_question = form_data.get("question")
        question = raw_question if isinstance(raw_question, str) else ""
        uploaded_files: list[tuple[str, bytes]] = []
        for attachment in form_data.getlist("attachments"):
            if not isinstance(attachment, StarletteUploadFile):
                continue
            uploaded_files.append((attachment.filename or "image", await attachment.read()))

        return question or "", normalize_attachment_uploads(uploaded_files)

    json_body = await request.json()
    parsed_request = PageChatRequest(**json_body)
    return parsed_request.question, []


@router.post("/api/pages/{page_id}/chat")
async def chat_with_page(
    page_id: str,
    request: Request,
) -> dict[str, object]:
    """围绕当前页面向 LLM 提问，并保存问答历史。"""

    question, attachments = await parse_page_chat_payload(request)
    return answer_page_question(page_id=page_id, question=question, attachments=attachments)


@router.post("/api/pages/{page_id}/chat/stream")
async def stream_chat_with_page(
    page_id: str,
    request: Request,
) -> StreamingResponse:
    """围绕当前页面向 LLM 提问，并用 NDJSON 流式返回回答增量。"""

    question, attachments = await parse_page_chat_payload(request)
    event_iterator = stream_page_question(
        page_id=page_id,
        question=question,
        attachments=attachments,
    )
    first_event = next(event_iterator)

    def generate_ndjson_lines():
        """把业务事件转换成前端容易逐行解析的 NDJSON 字节流。"""

        # 先输出路由层预取的第一条事件，再继续输出后续模型增量。
        yield json.dumps(first_event, ensure_ascii=False).encode("utf-8") + b"\n"
        for event in event_iterator:
            # ensure_ascii=False 保留中文，前端收到后可以直接展示，不需要二次转义。
            yield json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n"

    return StreamingResponse(
        generate_ndjson_lines(),
        media_type="application/x-ndjson",
    )


@router.get("/api/chat-attachments/{attachment_id}/file")
def read_chat_attachment_file(attachment_id: str) -> FileResponse:
    """返回当前页问答中已保存的图片附件。"""

    attachment = get_chat_attachment_file_row(attachment_id)
    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的聊天附件。",
        )

    attachment_path = resolve_chat_attachment_path(attachment["file_path"])
    ensure_chat_attachment_file_is_safe(attachment_path)
    if not attachment_path.exists() or not attachment_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="聊天附件文件不存在，可能已经被手动删除。",
        )

    return FileResponse(
        path=attachment_path,
        media_type=attachment["mime_type"],
        filename=attachment["original_filename"],
    )


@router.patch("/api/note-blocks/{note_block_id}")
def update_note_block_position(
    note_block_id: str,
    request: NoteBlockPositionUpdateRequest,
) -> dict[str, str | float]:
    """保存讲稿文字块拖动或缩放后的新位置。"""

    return update_note_block_position_record(note_block_id=note_block_id, request=request)
