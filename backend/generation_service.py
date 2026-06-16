"""课程简介、逐页讲稿和当前页问答的生成流程。"""

from fastapi import HTTPException, status

from config import (
    COURSE_SUMMARY_INPUT_LIMIT,
    LECTURE_NOTES_GENERATION_LOCKS,
    LECTURE_NOTES_GENERATION_LOCKS_GUARD,
    PAGE_CHAT_HISTORY_LIMIT,
)
from llm_client import LLMClient, get_llm_config
from pdf_service import ensure_page_image_file_is_safe, resolve_page_image_path
from repositories.chat_messages import (
    create_chat_message,
    list_chat_messages_for_page,
    list_recent_chat_messages_for_prompt,
)
from repositories.documents import (
    get_document_ready_for_lecture_notes,
    is_lecture_notes_paused,
    reset_document_lecture_notes_status,
    update_course_summary_status,
)
from repositories.pages import (
    get_page_context_for_chat,
    list_pages_for_lecture_notes,
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


def format_chat_history_for_prompt(messages: list[dict[str, str]]) -> str:
    """把当前页历史问答整理成适合放入 prompt 的文本。"""

    if not messages:
        return "（本页还没有历史问答）"

    role_labels = {"user": "学生", "assistant": "AI 老师"}
    history_lines: list[str] = []
    for message in messages:
        role_label = role_labels.get(message["role"], message["role"])
        history_lines.append(f"{role_label}：{message['content']}")

    return "\n\n".join(history_lines)


def build_page_chat_prompt(
    page_context,
    history_messages: list[dict[str, str]],
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
    """按页码顺序为整份文档生成逐页讲稿。"""

    generation_lock = get_lecture_notes_generation_lock(document_id)
    if not generation_lock.acquire(blocking=False):
        return

    try:
        try:
            document = get_document_ready_for_lecture_notes(document_id)
        except HTTPException:
            return

        pages = list_pages_for_lecture_notes(document_id)
        for page in pages:
            if page["lecture_notes_status"] == "ready":
                continue

            if is_lecture_notes_paused(document_id):
                return

            generate_single_page_lecture_notes(document=document, page=page)
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

        reset_document_lecture_notes_status(document_id)
        generate_document_lecture_notes(document_id)
    except Exception as error:
        update_course_summary_status(
            document_id=document_id,
            summary_status="failed",
            course_summary=None,
            error_message=f"课程简介生成失败：{error}",
        )


def answer_page_question(page_id: str, question: str) -> dict[str, object]:
    """保存用户问题，调用 LLM，并返回当前页完整问答历史。"""

    normalized_question = question.strip()
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

    history_messages = list_recent_chat_messages_for_prompt(page_id)
    prompt = build_page_chat_prompt(
        page_context=page_context,
        history_messages=history_messages,
        question=normalized_question,
    )
    client = LLMClient(get_llm_config())
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
