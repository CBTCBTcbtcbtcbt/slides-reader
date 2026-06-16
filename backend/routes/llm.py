"""LLM 配置和测试路由。"""

from fastapi import APIRouter, HTTPException, status

from llm_client import LLMClient, get_llm_config, normalize_base_url, normalize_timeout_seconds, serialize_llm_config
from repositories.settings import write_app_settings
from schemas import LLMConfigUpdateRequest, LLMTestRequest


router = APIRouter()


@router.get("/api/llm/config")
def read_llm_config() -> dict[str, str | int | bool]:
    """返回当前 LLM 配置，API Key 只返回掩码。"""

    return serialize_llm_config(get_llm_config())


@router.patch("/api/llm/config")
def update_llm_config(request: LLMConfigUpdateRequest) -> dict[str, str | int | bool]:
    """保存 WebUI 提交的 LLM 配置。"""

    base_url = normalize_base_url(request.base_url)
    if not base_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LLM 服务地址不能为空。",
        )

    model = request.model.strip()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LLM 模型名称不能为空。",
        )

    timeout_seconds = normalize_timeout_seconds(request.timeout_seconds)

    current_config = get_llm_config()
    next_settings: dict[str, str] = {
        "base_url": base_url,
        "model": model,
        "timeout_seconds": str(timeout_seconds),
    }

    # api_key 为 None 表示保留旧值；空字符串表示清空旧值。
    if request.api_key is not None:
        next_settings["api_key"] = request.api_key
    else:
        next_settings["api_key"] = current_config.api_key

    if request.course_summary_prompt is not None:
        course_summary_prompt = request.course_summary_prompt.strip()
        if not course_summary_prompt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="课程简介 prompt 不能为空。",
            )
        next_settings["course_summary_prompt"] = course_summary_prompt

    if request.lecture_notes_prompt is not None:
        lecture_notes_prompt = request.lecture_notes_prompt.strip()
        if not lecture_notes_prompt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="逐页讲稿 prompt 不能为空。",
            )
        next_settings["lecture_notes_prompt"] = lecture_notes_prompt

    if request.page_chat_prompt is not None:
        page_chat_prompt = request.page_chat_prompt.strip()
        if not page_chat_prompt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="当前页问答 prompt 不能为空。",
            )
        next_settings["page_chat_prompt"] = page_chat_prompt

    write_app_settings(next_settings)
    return serialize_llm_config(get_llm_config())


@router.post("/api/llm/test")
def test_llm_config(request: LLMTestRequest) -> dict[str, str]:
    """使用当前配置向 LLM 发起一次纯文本测试。"""

    prompt = request.prompt.strip()
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="测试提示词不能为空。",
        )

    client = LLMClient(get_llm_config())
    answer = client.complete_text(prompt)

    return {"status": "ok", "answer": answer}
