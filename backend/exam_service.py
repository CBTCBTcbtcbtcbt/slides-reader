"""试卷生成功能。

本模块负责根据 slides 文档内容调用 LLM 生成期末考试卷，
并把结果持久化到数据库。
"""

import json
import re

from fastapi import HTTPException, status

from config import COURSE_SUMMARY_INPUT_LIMIT
from database import get_database_connection
from generation_service import build_course_summary_input
from llm_client import LLMClient, get_llm_config
from repositories.documents import row_to_document
from repositories.exams import (
    create_exam_question,
    create_exam_record,
    get_exam_by_id,
    update_exam_content,
    update_exam_status,
)


def build_exam_generation_input(document_id: str) -> tuple[dict[str, str | int | bool | None], str, bool]:
    """读取文档页面文字和课程简介，整理成试卷生成输入。"""

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

    document = row_to_document(document_row)

    page_text_blocks: list[str] = []
    for row in page_rows:
        page_text = row["text"].strip() if row["text"] else "（本页没有可提取文字）"
        page_text_blocks.append(f"第 {row['page_number']} 页：\n{page_text}")

    full_pages_text = "\n\n".join(page_text_blocks)
    was_truncated = len(full_pages_text) > COURSE_SUMMARY_INPUT_LIMIT
    if was_truncated:
        full_pages_text = full_pages_text[:COURSE_SUMMARY_INPUT_LIMIT]

    # 把课程简介也放进输入，帮助 LLM 把握重点
    course_summary = document.get("course_summary") or "（课程简介尚未生成）"
    input_text = f"课程简介：\n{course_summary}\n\n页面文字：\n{full_pages_text}"

    return document, input_text, was_truncated


def build_exam_generation_prompt(
    document: dict[str, str | int | bool | None],
    pages_text: str,
    was_truncated: bool,
    difficulty: str = "medium",
) -> str:
    """构造发送给 LLM 的试卷生成 prompt。"""

    llm_config = get_llm_config()
    truncation_note = (
        "注意：由于文档较长，下面的页面文字已按 12000 字符上限截断。请基于已提供内容生成试卷。"
        if was_truncated
        else "下面包含当前文档全部已提取页面文字。"
    )

    difficulty_note = {
        "easy": "难度要求：整体偏简单，重点考查基础概念和直接记忆性内容。",
        "medium": "难度要求：中等难度，兼顾概念理解和简单应用。",
        "hard": "难度要求：整体偏难，注重综合应用和易混淆知识点的辨析。",
    }.get(difficulty, "难度要求：中等难度。")

    return f"""{llm_config.exam_generation_prompt}

文档标题：{document["title"]}
总页数：{document["page_count"]}
难度：{difficulty}
{difficulty_note}
{truncation_note}

{pages_text}

必须只输出合法 JSON 对象，不要包裹在 markdown 代码块里，也不要添加任何额外说明文字。
"""


def _extract_balanced_json(text: str) -> dict:
    """从文本中按括号平衡原则提取最外层 JSON 对象。"""

    start = text.find("{")
    if start == -1:
        raise ValueError("LLM 返回中未找到 JSON 对象起始位置。")

    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : index + 1])
                except json.JSONDecodeError as error:
                    raise ValueError(f"提取的 JSON 无法解析：{error}") from error

    raise ValueError("LLM 返回中的 JSON 对象括号不匹配。")


def extract_json_from_llm_response(response: str) -> dict:
    """从 LLM 返回的文本中提取 JSON 对象。"""

    cleaned = response.strip()

    # 先尝试直接解析
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ... ``` 代码块
    code_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    if code_match:
        inner = code_match.group(1).strip()
        try:
            return json.loads(inner)
        except json.JSONDecodeError:
            try:
                return _extract_balanced_json(inner)
            except ValueError as error:
                raise ValueError(f"从代码块提取的 JSON 无法解析：{error}") from error

    # 按括号平衡提取最外层对象
    try:
        return _extract_balanced_json(cleaned)
    except ValueError as error:
        raise ValueError(f"LLM 返回中未找到可解析的 JSON：{error}") from error


def _clean_choice_option(option: str) -> str:
    """去除选项里可能带有的 A/B/C/D 前缀，只保留选项正文。"""

    text = str(option).strip()
    match = re.match(r"^[A-Da-d][\.\)\s]\s*(.*)$", text)
    if match:
        return match.group(1).strip()
    return text


def validate_exam_data(data: dict) -> None:
    """校验并规范化 LLM 返回的试卷 JSON 结构。"""

    if not isinstance(data, dict):
        raise ValueError("试卷 JSON 必须是对象。")

    if "title" not in data or not data["title"]:
        raise ValueError("试卷 JSON 必须包含非空 title。")
    if "sections" not in data:
        raise ValueError("试卷 JSON 缺少 sections 字段。")

    data.setdefault("description", None)
    data.setdefault("total_score", 100)

    if not isinstance(data["sections"], list) or not data["sections"]:
        raise ValueError("sections 必须是非空数组。")

    seen_numbers: set[tuple[str, int]] = set()
    computed_total = 0
    for section in data["sections"]:
        if not isinstance(section, dict):
            raise ValueError("section 必须是对象。")

        section.setdefault("name", "A")
        section.setdefault("title", section["name"])
        if "questions" not in section:
            continue

        for raw_question in section["questions"]:
            if not isinstance(raw_question, dict):
                raise ValueError("题目必须是对象。")

            question = raw_question
            question.setdefault("number", 1)
            question.setdefault("score", 5)
            question.setdefault("content", "")
            question.setdefault("explanation", "")
            question.setdefault("source_page", None)
            question.setdefault("expected_type", "text")
            question.setdefault("difficulty", "medium")
            question.setdefault("knowledge_tag", "general")

            if "type" not in question:
                raise ValueError("题目缺少 type 字段。")
            if "answer" not in question:
                raise ValueError("题目缺少 answer 字段。")

            q_type = question["type"]
            if q_type not in {"choice", "fill_in"}:
                raise ValueError(f"MVP 只支持 choice 和 fill_in 题型，不支持：{q_type}")

            if q_type == "choice":
                options = question.get("options")
                if not isinstance(options, list) or len(options) < 2:
                    raise ValueError("选择题必须提供至少 2 个选项。")
                question["options"] = [_clean_choice_option(option) for option in options[:4]]
                while len(question["options"]) < 4:
                    question["options"].append("（选项未提供）")

                answer = str(question["answer"]).strip().upper()
                if len(answer) > 1:
                    # 如果答案被写成 "A. xxx" 或 "A) xxx"，只取首字母。
                    answer = answer[0]
                if answer not in {"A", "B", "C", "D"}:
                    raise ValueError(f"选择题答案必须是 A/B/C/D 之一，得到：{answer}")
                question["answer"] = answer
                question["expected_type"] = "text"
            elif q_type == "fill_in":
                answer = str(question["answer"]).strip()
                if not answer:
                    raise ValueError("填空题答案不能为空。")

                if question.get("expected_type") != "number" or not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", answer):
                    # Kimi 偶尔会把符号、关键字或 NULL 生成为填空题答案。
                    # 这类题不能按数字填空判分，直接转成单选题比整份试卷失败更稳。
                    original_answer = answer if answer else "未提供"
                    question["type"] = "choice"
                    question["options"] = [
                        original_answer,
                        "0",
                        "1",
                        "2",
                    ]
                    question["answer"] = "A"
                    question["expected_type"] = "text"
                    explanation = str(question.get("explanation") or "").strip()
                    if explanation:
                        question["explanation"] = f"{explanation} 原填空答案不是纯数字，已改为单选题。"
                    else:
                        question["explanation"] = "原填空答案不是纯数字，已改为单选题。"
                else:
                    question["answer"] = answer

            try:
                question["score"] = int(question["score"])
            except (TypeError, ValueError):
                question["score"] = 5

            try:
                source_page = question.get("source_page")
                question["source_page"] = int(source_page) if source_page is not None else None
            except (TypeError, ValueError):
                question["source_page"] = None

            computed_total += question["score"]

            key = (section["name"], question["number"])
            if key in seen_numbers:
                raise ValueError(f"重复的题号：{key}")
            seen_numbers.add(key)

    if computed_total > 0:
        data["total_score"] = computed_total


def generate_validated_exam_data(client: LLMClient, prompt: str) -> dict:
    """调用 LLM 生成试卷 JSON，并在输出不合格时自动重试。"""

    last_error: Exception | None = None
    retry_instruction = """

上一次输出不符合系统校验，必须重新生成完整 JSON。
为了避免输出过长被截断，这一次必须使用紧凑 JSON：不要缩进、不要空行、不要 markdown。
强制要求：
- 输出必须是完整合法 JSON 对象，不能截断。
- 总题数仍为 18 题，总分仍为 100 分。
- 每道题 explanation 控制在 60 个中文字符以内，只写判题所需的核心原因。
- 所有 fill_in 题的 expected_type 必须是 "number"。
- 所有 fill_in 题的 answer 必须完整匹配纯数字，例如 "0", "1", "3.14"。
- answer 不能是 NULL、null、None、%、if、for、list、first、函数名、变量名、单位或任何非数字文本。
- 如果答案不是纯数字，必须把该题改成 choice 题。
"""

    for attempt in range(3):
        active_prompt = prompt if attempt == 0 else f"{prompt}{retry_instruction}\n上一次错误：{last_error}"
        response = client.complete_text(
            active_prompt,
            max_tokens=4096,
            response_format={"type": "json_object"},
            timeout_seconds=180,
        )
        try:
            exam_data = extract_json_from_llm_response(response)
            validate_exam_data(exam_data)
            return exam_data
        except Exception as error:
            last_error = error

    raise ValueError(f"LLM 连续生成不合格试卷：{last_error}")


def generate_exam(
    document_id: str,
    exam_id: str | None = None,
    difficulty: str = "medium",
) -> dict[str, str | int | None]:
    """为指定文档生成试卷并写入数据库。

    参数：
        document_id：要生成试卷的文档 ID。
        exam_id：可选，如果提供则更新该试卷记录；否则创建新记录。
        difficulty：试卷难度，可选 easy / medium / hard。

    返回值：
        dict：生成的试卷记录。
    """

    if exam_id is None:
        exam_record = create_exam_record(
            document_id=document_id,
            title="生成中...",
            description=None,
            total_score=100,
            exam_status="processing",
        )
        exam_id = exam_record["id"]
    else:
        update_exam_status(
            exam_id=exam_id,
            exam_status="processing",
            error_message=None,
        )

    try:
        document, pages_text, was_truncated = build_exam_generation_input(document_id)
        prompt = build_exam_generation_prompt(
            document=document,
            pages_text=pages_text,
            was_truncated=was_truncated,
            difficulty=difficulty,
        )

        client = LLMClient(get_llm_config())
        exam_data = generate_validated_exam_data(client, prompt)

        update_exam_content(
            exam_id=exam_id,
            title=exam_data["title"],
            description=exam_data.get("description"),
            total_score=int(exam_data.get("total_score", 100)),
        )

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

        update_exam_status(
            exam_id=exam_id,
            exam_status="ready",
            error_message=None,
        )
    except Exception as error:
        update_exam_status(
            exam_id=exam_id,
            exam_status="failed",
            error_message=f"试卷生成失败：{error}",
        )
        raise

    return get_exam_by_id(exam_id)
