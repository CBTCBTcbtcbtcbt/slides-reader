"""阶段考试生成功能。

阶段考试综合多份课件内容，并根据用户在这些课件上的历史错题
调整知识点权重，生成一份综合测试卷。
"""

import json
from typing import Any

from fastapi import HTTPException, status

from config import COURSE_SUMMARY_INPUT_LIMIT
from database import get_database_connection
from exam_service import generate_validated_exam_data
from llm_client import LLMClient, get_llm_config
from repositories.documents import row_to_document
from repositories.exams import (
    create_exam_question,
    create_exam_record,
    update_exam_content,
    update_exam_status,
)
from repositories.phase_exams import get_phase_exam_by_id
from repositories.wrong_questions import get_knowledge_tag_statistics


def build_phase_exam_input(document_ids: list[str]) -> tuple[list[dict[str, Any]], str, bool]:
    """读取多份文档的课程简介和代表性页面文字，整理成阶段考试输入。

    为了控制 prompt 长度、降低长上下文模型压力，这里不再塞入全部页面文字，
    而是把课程简介作为核心依据，并只补充每份课件的前几页关键文字。
    """

    documents = []
    all_blocks: list[str] = []
    # 每份课件最多带几页原文；课程简介已经覆盖核心知识点，前几页通常包含
    # 主题、定义和示例，足够出题使用。
    max_pages_per_document = 5

    with get_database_connection() as connection:
        for document_id in document_ids:
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
                    detail=f"没有找到文档：{document_id}",
                )

            document = row_to_document(document_row)
            documents.append(document)

            course_summary = document.get("course_summary") or "（课程简介尚未生成）"
            block_lines = [f"=== 课件：{document_row['title']} ===", f"课程简介：\n{course_summary}"]

            page_rows = connection.execute(
                """
                SELECT page_number, text
                FROM pages
                WHERE document_id = ?
                ORDER BY page_number ASC
                LIMIT ?
                """,
                (document_id, max_pages_per_document),
            ).fetchall()

            if page_rows:
                page_blocks = []
                for row in page_rows:
                    page_text = row["text"].strip() if row["text"] else "（本页没有可提取文字）"
                    page_blocks.append(f"第 {row['page_number']} 页：\n{page_text}")
                block_lines.append("代表性页面文字：\n" + "\n\n".join(page_blocks))

            all_blocks.append("\n\n".join(block_lines))

    full_text = "\n\n\n".join(all_blocks)
    was_truncated = len(full_text) > COURSE_SUMMARY_INPUT_LIMIT
    if was_truncated:
        full_text = full_text[:COURSE_SUMMARY_INPUT_LIMIT]

    return documents, full_text, was_truncated


def build_phase_exam_prompt(
    documents: list[dict[str, Any]],
    pages_text: str,
    was_truncated: bool,
    wrong_tag_stats: list[dict[str, Any]],
    difficulty: str = "medium",
) -> str:
    """构造阶段考试生成 prompt。"""

    llm_config = get_llm_config()
    truncation_note = (
        "注意：由于合并的文档较长，下面的页面文字已按字符上限截断。请基于已提供内容生成试卷。"
        if was_truncated
        else "下面包含所选课件的全部已提取页面文字。"
    )

    difficulty_note = {
        "easy": "难度要求：整体偏简单，重点考查基础概念。",
        "medium": "难度要求：中等难度，兼顾概念理解和简单应用。",
        "hard": "难度要求：整体偏难，注重综合应用和易混淆知识点。",
    }.get(difficulty, "难度要求：中等难度。")

    # 构造错题知识点加权提示
    if wrong_tag_stats:
        weighted_tags = "\n".join(
            f"- {item['knowledge_tag']}：错题 {item['wrong_count']} 次"
            for item in wrong_tag_stats[:10]
        )
        weight_note = f"""以下知识点用户过去错题较多，请在阶段考试中适当增加这些知识点的题目权重（但仍是新题，不要重复原题）：

{weighted_tags}
"""
    else:
        weight_note = "用户暂无历史错题记录，请均匀覆盖各课件的核心知识点。"

    document_titles = "\n".join(f"- {doc['title']}" for doc in documents)

    return f"""{llm_config.exam_generation_prompt}

阶段考试说明：本次考试综合以下课件内容：
{document_titles}

{difficulty_note}
{truncation_note}

{weight_note}

{pages_text}

为了避免长 JSON 被截断，请使用紧凑 JSON：不要缩进、不要空行、不要 markdown。
每道题的 explanation 控制在 60 个中文字符以内，只写判题所需的核心原因。
所有 fill_in 题的 answer 必须是纯数字；如果答案是符号、关键字、概念名或代码片段，必须改成 choice 题。

必须只输出完整合法 JSON 对象，不要包裹在 markdown 代码块里，也不要添加任何额外说明文字。
"""


def generate_phase_exam(
    document_ids: list[str],
    name: str,
    difficulty: str = "medium",
    phase_exam_id: str | None = None,
) -> dict[str, str | int | None]:
    """生成阶段考试并写入数据库。

    参数：
        document_ids：参与阶段考试的文档 ID 列表。
        name：阶段考试名称。
        difficulty：难度。
        phase_exam_id：可选，复用已有的 phase_exam 记录 ID。

    返回值：
        dict：生成的考试记录。
    """

    from repositories.phase_exams import (
        create_phase_exam_record,
        update_phase_exam_exam_id,
        update_phase_exam_status,
    )

    if phase_exam_id is None:
        phase_exam_record = create_phase_exam_record(
            name=name,
            document_ids=document_ids,
            difficulty=difficulty,
            phase_exam_status="processing",
        )
        phase_exam_id = phase_exam_record["id"]

    # 先创建一个对应的普通 exam 记录，作为题目容器
    exam_record = create_exam_record(
        document_id=document_ids[0],  # 主文档取第一个
        title=name,
        description=f"阶段考试，包含课件：{', '.join(document_ids)}",
        total_score=100,
        exam_status="processing",
    )
    exam_id = exam_record["id"]
    update_phase_exam_exam_id(
        phase_exam_id=phase_exam_id,
        exam_id=exam_id,
    )

    try:
        documents, pages_text, was_truncated = build_phase_exam_input(document_ids)
        wrong_tag_stats = get_knowledge_tag_statistics()

        prompt = build_phase_exam_prompt(
            documents=documents,
            pages_text=pages_text,
            was_truncated=was_truncated,
            wrong_tag_stats=wrong_tag_stats,
            difficulty=difficulty,
        )

        client = LLMClient(get_llm_config())
        exam_data = generate_validated_exam_data(client, prompt)

        for section in exam_data["sections"]:
            section_name = section["name"]
            for question in section["questions"]:
                answer = str(question["answer"]).strip()
                if question["type"] == "choice":
                    answer = answer.upper()

                create_exam_question(
                    exam_id=exam_id,
                    question_number=int(question["number"]),
                    section=section_name,
                    question_type=question["type"],
                    score=int(question["score"]),
                    content=question["content"],
                    options=question.get("options"),
                    answer=answer,
                    explanation=question["explanation"],
                    source_page=int(question["source_page"]) if question.get("source_page") is not None else None,
                    expected_type=question.get("expected_type"),
                    difficulty=question.get("difficulty"),
                    knowledge_tag=question.get("knowledge_tag"),
                )

        # 阶段考试题目写入成功后，同步更新关联 exam 的标题、总分和状态，
        # 否则答题接口会因为 exam.status 仍是 processing 而拒绝。
        update_exam_content(
            exam_id=exam_id,
            title=exam_data["title"],
            description=exam_data.get("description"),
            total_score=int(exam_data.get("total_score", 100)),
        )
        update_exam_status(
            exam_id=exam_id,
            exam_status="ready",
            error_message=None,
        )

        # 更新 phase_exam 的生成状态；exam_id 已在创建普通 exam 后立即写入，
        # 这样失败任务也能通过 phase_exam 找到并清理对应的 failed exam。
        update_phase_exam_status(
            phase_exam_id=phase_exam_id,
            phase_exam_status="ready",
            error_message=None,
        )
    except Exception as error:
        update_exam_status(
            exam_id=exam_id,
            exam_status="failed",
            error_message=f"阶段考试生成失败：{error}",
        )
        update_phase_exam_status(
            phase_exam_id=phase_exam_id,
            phase_exam_status="failed",
            error_message=f"阶段考试生成失败：{error}",
        )
        raise

    return get_phase_exam_by_id(phase_exam_id)
