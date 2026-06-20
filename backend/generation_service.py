"""课程简介、逐页讲稿和当前页问答的生成流程。"""

from pathlib import Path
from typing import Iterator

from fastapi import HTTPException, status

from config import (
    COURSE_SUMMARY_INPUT_LIMIT,
    LECTURE_NOTES_GENERATION_LOCKS,
    LECTURE_NOTES_GENERATION_LOCKS_GUARD,
    PAGE_CHAT_HISTORY_LIMIT,
    PAGE_CHAT_RECENT_IMAGE_LIMIT,
)
from llm_client import LLMClient, get_llm_config
from pdf_service import ensure_page_image_file_is_safe, resolve_page_image_path
from repositories.chat_attachments import (
    ChatAttachmentUpload,
    ensure_chat_attachment_file_is_safe,
    list_image_attachments_for_message,
    list_recent_image_attachments_for_prompt,
    resolve_chat_attachment_path,
    save_chat_attachments,
)
from repositories.chat_messages import (
    create_chat_message,
    list_chat_messages_for_page,
    list_recent_chat_messages_for_prompt,
)
from repositories.documents import (
    get_document_ready_for_lecture_notes,
    is_lecture_notes_paused,
    update_course_summary_status,
)
from repositories.lecture_notes_queue import (
    complete_lecture_notes_queue_item,
    dequeue_next_lecture_notes_page,
    reset_processing_lecture_notes_queue_items,
)
from repositories.pages import (
    get_page_context_for_chat,
    update_page_lecture_notes_status,
)
from database import get_database_connection
from repositories.documents import row_to_document


def build_course_summary_input(document_id: str) -> tuple[dict[str, str | int | bool | None], str, bool]:
    """读取文档页面文字，并整理成课程简介生成输入。"""

    with get_database_connection() as connection:
        document_row = connection.execute(
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

        if document_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="没有找到对应的文档。",
            )

        page_rows = connection.execute(
            """
            SELECT page_number, text
            FROM pages
            WHERE document_id = ?
            ORDER BY page_number ASC
            """,
            (document_id,),
        ).fetchall()

    page_text_blocks: list[str] = []
    for row in page_rows:
        page_text = row["text"].strip() if row["text"] else "（本页没有可提取文字）"
        page_text_blocks.append(f"第 {row['page_number']} 页：\n{page_text}")

    full_pages_text = "\n\n".join(page_text_blocks)
    was_truncated = len(full_pages_text) > COURSE_SUMMARY_INPUT_LIMIT
    if was_truncated:
        full_pages_text = full_pages_text[:COURSE_SUMMARY_INPUT_LIMIT]

    return row_to_document(document_row), full_pages_text, was_truncated


def build_course_summary_prompt(
    document: dict[str, str | int | bool | None],
    pages_text: str,
    was_truncated: bool,
) -> str:
    """构造发送给 LLM 的课程简介生成 prompt。"""

    llm_config = get_llm_config()
    truncation_note = (
        "注意：由于文档较长，下面的页面文字已按 12000 字符上限截断。请基于已提供内容生成课程导读。"
        if was_truncated
        else "下面包含当前文档全部已提取页面文字。"
    )

    return f"""{llm_config.course_summary_prompt}

文档标题：{document["title"]}
总页数：{document["page_count"]}
{truncation_note}

页面文字：
{pages_text}
"""


def build_lecture_notes_prompt(document, page) -> str:
    """构造发送给 LLM 的单页讲稿生成 prompt。"""

    llm_config = get_llm_config()
    page_text = page["text"].strip() if page["text"] else "（本页没有可提取文字）"

    return f"""{llm_config.lecture_notes_prompt}

文档标题：{document["title"]}
总页数：{document["page_count"]}
当前页码：第 {page["page_number"]} 页

课程简介：
{document["course_summary"]}

当前页提取文字：
{page_text}
"""


def format_chat_history_for_prompt(messages: list[dict[str, object]]) -> str:
    """把当前页历史问答整理成适合放入 prompt 的文本。"""

    if not messages:
        return "（本页还没有历史问答）"

    role_labels = {"user": "学生", "assistant": "AI 老师"}
    history_lines: list[str] = []
    for message in messages:
        role = str(message["role"])
        role_label = role_labels.get(role, role)
        attachment_count = len(message.get("attachments", []))
        attachment_note = f"\n（这条消息附带了 {attachment_count} 张图片）" if attachment_count else ""
        history_lines.append(f"{role_label}：{message['content']}{attachment_note}")

    return "\n\n".join(history_lines)


def build_page_chat_prompt(
    page_context,
    history_messages: list[dict[str, object]],
    question: str,
) -> str:
    """构造当前页问答发送给 LLM 的 prompt。"""

    llm_config = get_llm_config()
    page_text = page_context["text"].strip() if page_context["text"] else "（本页没有可提取文字）"
    lecture_notes = (
        page_context["lecture_notes"].strip()
        if page_context["lecture_notes"]
        else "（本页讲稿尚未生成或为空）"
    )
    course_summary = (
        page_context["course_summary"].strip()
        if page_context["course_summary"]
        else "（课程简介尚未生成或为空）"
    )
    chat_history = format_chat_history_for_prompt(history_messages)

    return f"""{llm_config.page_chat_prompt}

文档标题：{page_context["document_title"]}
当前页码：第 {page_context["page_number"]} 页

课程简介：
{course_summary}

当前页提取文字：
{page_text}

当前页讲稿：
{lecture_notes}

当前页最近 {PAGE_CHAT_HISTORY_LIMIT} 条历史问答：
{chat_history}

学生最新问题：
{question}
"""


def build_page_chat_images(
    page_id: str,
    current_message_id: str,
    current_message_images: list[dict[str, str]],
) -> list[tuple[Path, str]]:
    """整理当前页问答需要带给 LLM 的图片列表。"""

    images: list[tuple[Path, str]] = []
    history_attachments = list_recent_image_attachments_for_prompt(
        page_id=page_id,
        limit=PAGE_CHAT_RECENT_IMAGE_LIMIT,
        exclude_chat_message_id=current_message_id,
    )

    for attachment in history_attachments:
        image_path = resolve_chat_attachment_path(attachment["file_path"])
        ensure_chat_attachment_file_is_safe(image_path)
        if image_path.exists() and image_path.is_file():
            images.append((image_path, attachment["mime_type"]))

    for attachment in current_message_images:
        image_path = resolve_chat_attachment_path(attachment["file_path"])
        ensure_chat_attachment_file_is_safe(image_path)
        if image_path.exists() and image_path.is_file():
            images.append((image_path, attachment["mime_type"]))

    return images


def prepare_page_chat_request(
    page_id: str,
    question: str,
    attachments: list[ChatAttachmentUpload] | None = None,
) -> tuple[dict[str, object], str, list[tuple[Path, str]]]:
    """保存用户消息和附件，并构造当前页问答的 prompt 与图片输入。

    参数：
        page_id：当前提问所属的页面 ID。
        question：用户输入的问题文本。
        attachments：已经通过后端校验的本轮图片附件。

    返回值：
        tuple：依次包含已保存的用户消息、发给 LLM 的 prompt、发给 LLM 的图片列表。
    """

    # 流式和非流式接口必须共享同一段准备逻辑，避免历史图片和附件保存规则出现差异。
    normalized_question = question.strip()
    normalized_attachments = attachments or []
    if not normalized_question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="问题不能为空。",
        )

    page_context = get_page_context_for_chat(page_id)
    user_message = create_chat_message(
        page_id=page_id,
        role="user",
        content=normalized_question,
    )
    user_attachments = save_chat_attachments(
        page_id=page_id,
        chat_message_id=str(user_message["chat_message_id"]),
        uploads=normalized_attachments,
    )
    user_message["attachments"] = user_attachments

    history_messages = list_recent_chat_messages_for_prompt(page_id)
    prompt = build_page_chat_prompt(
        page_context=page_context,
        history_messages=history_messages,
        question=normalized_question,
    )
    current_message_images = list_image_attachments_for_message(str(user_message["chat_message_id"]))
    image_inputs = build_page_chat_images(
        page_id=page_id,
        current_message_id=str(user_message["chat_message_id"]),
        current_message_images=current_message_images,
    )

    return user_message, prompt, image_inputs


def get_lecture_notes_generation_lock(document_id: str):
    """获取某个文档的整份讲稿生成锁。"""

    # 保护锁字典本身，避免两个请求同时创建两把不同的锁。
    with LECTURE_NOTES_GENERATION_LOCKS_GUARD:
        if document_id not in LECTURE_NOTES_GENERATION_LOCKS:
            import threading

            LECTURE_NOTES_GENERATION_LOCKS[document_id] = threading.Lock()
        return LECTURE_NOTES_GENERATION_LOCKS[document_id]


def generate_single_page_lecture_notes(document, page) -> None:
    """为单页生成讲稿，并把结果写入数据库。"""

    document_id = document["id"]
    page_number = page["page_number"]

    try:
        update_page_lecture_notes_status(
            document_id=document_id,
            page_number=page_number,
            lecture_notes_status="processing",
            lecture_notes=None,
            error_message=None,
        )

        if page["status"] != "ready":
            raise ValueError(page["error_message"] or "当前页面解析失败，无法生成讲稿。")

        if not page["image_path"]:
            raise ValueError("当前页面还没有生成截图，无法生成讲稿。")

        image_path = resolve_page_image_path(page["image_path"])
        ensure_page_image_file_is_safe(image_path)
        if not image_path.exists():
            raise ValueError("页面截图文件不存在，可能已被手动删除。")

        prompt = build_lecture_notes_prompt(document=document, page=page)
        client = LLMClient(get_llm_config())
        lecture_notes = client.complete_with_image(prompt=prompt, image_path=image_path)

        update_page_lecture_notes_status(
            document_id=document_id,
            page_number=page_number,
            lecture_notes_status="ready",
            lecture_notes=lecture_notes,
            error_message=None,
        )
    except Exception as error:
        update_page_lecture_notes_status(
            document_id=document_id,
            page_number=page_number,
            lecture_notes_status="failed",
            lecture_notes=None,
            error_message=f"逐页讲稿生成失败：{error}",
        )


def generate_document_lecture_notes(document_id: str) -> None:
    """按页码顺序消费指定文档的逐页讲稿生成队列。"""

    generation_lock = get_lecture_notes_generation_lock(document_id)
    if not generation_lock.acquire(blocking=False):
        return

    try:
        # 上一次服务中断可能留下 processing 队列项，重新启动处理器时先恢复为 waiting。
        reset_processing_lecture_notes_queue_items(document_id)

        try:
            document = get_document_ready_for_lecture_notes(document_id)
        except HTTPException:
            return

        while True:
            if is_lecture_notes_paused(document_id):
                return

            page = dequeue_next_lecture_notes_page(document_id)
            if page is None:
                return

            try:
                generate_single_page_lecture_notes(document=document, page=page)
            finally:
                # 无论单页生成成功还是失败，这次队列项都已经处理完毕。
                # 失败信息写在 pages.lecture_notes_error 中，用户可再次把本页加入队列重试。
                complete_lecture_notes_queue_item(page["id"])
    finally:
        generation_lock.release()


def generate_course_summary(document_id: str) -> None:
    """为指定文档生成课程简介并写入数据库。"""

    try:
        update_course_summary_status(
            document_id=document_id,
            summary_status="processing",
            course_summary=None,
            error_message=None,
        )

        document, pages_text, was_truncated = build_course_summary_input(document_id)
        prompt = build_course_summary_prompt(
            document=document,
            pages_text=pages_text,
            was_truncated=was_truncated,
        )

        client = LLMClient(get_llm_config())
        course_summary = client.complete_text(prompt)

        update_course_summary_status(
            document_id=document_id,
            summary_status="ready",
            course_summary=course_summary,
            error_message=None,
        )
        # 课程简介和逐页讲稿现在是两个独立的手动操作，简介生成成功后不再自动重置或生成讲稿。
    except Exception as error:
        update_course_summary_status(
            document_id=document_id,
            summary_status="failed",
            course_summary=None,
            error_message=f"课程简介生成失败：{error}",
        )


def answer_page_question(
    page_id: str,
    question: str,
    attachments: list[ChatAttachmentUpload] | None = None,
) -> dict[str, object]:
    """保存用户问题，调用 LLM，并返回当前页完整问答历史。"""

    user_message, prompt, image_inputs = prepare_page_chat_request(
        page_id=page_id,
        question=question,
        attachments=attachments,
    )
    client = LLMClient(get_llm_config())

    if image_inputs:
        answer = client.complete_with_images(prompt, image_inputs)
    else:
        answer = client.complete_text(prompt)

    assistant_message = create_chat_message(
        page_id=page_id,
        role="assistant",
        content=answer,
    )

    return {
        "status": "ok",
        "page_id": page_id,
        "user_message": user_message,
        "assistant_message": assistant_message,
        "messages": list_chat_messages_for_page(page_id),
    }


def stream_page_question(
    page_id: str,
    question: str,
    attachments: list[ChatAttachmentUpload] | None = None,
) -> Iterator[dict[str, object]]:
    """保存用户问题，并把 LLM 回答按增量事件流式返回。

    参数：
        page_id：当前提问所属的页面 ID。
        question：用户输入的问题文本。
        attachments：已经通过后端校验的本轮图片附件。

    返回值：
        Iterator[dict[str, object]]：逐个产出 user_message、delta、done 或 error 事件。
    """

    user_message, prompt, image_inputs = prepare_page_chat_request(
        page_id=page_id,
        question=question,
        attachments=attachments,
    )
    yield {
        "type": "user_message",
        "message": user_message,
    }

    answer_parts: list[str] = []
    client = LLMClient(get_llm_config())

    try:
        # 有本轮图片或历史图片时走图文流式请求，否则继续走纯文本流式请求。
        answer_stream = (
            client.stream_with_images(prompt, image_inputs)
            if image_inputs
            else client.stream_text(prompt)
        )
        for delta in answer_stream:
            answer_parts.append(delta)
            yield {
                "type": "delta",
                "content": delta,
            }
    except HTTPException as error:
        yield {
            "type": "error",
            "message": str(error.detail),
        }
        return
    except Exception as error:
        yield {
            "type": "error",
            "message": f"当前页问答失败：{error}",
        }
        return

    answer = "".join(answer_parts).strip()
    if not answer:
        yield {
            "type": "error",
            "message": "LLM 服务返回了空回答。",
        }
        return

    assistant_message = create_chat_message(
        page_id=page_id,
        role="assistant",
        content=answer,
    )

    yield {
        "type": "done",
        "assistant_message": assistant_message,
        "messages": list_chat_messages_for_page(page_id),
    }
