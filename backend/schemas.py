"""FastAPI 请求体模型。

Pydantic 的 BaseModel 会让 FastAPI 自动校验 JSON 请求体字段，
并在字段缺失或类型错误时返回标准的 422 校验错误。
"""

from pydantic import BaseModel


class RenameDocumentRequest(BaseModel):
    """重命名文档的请求体。"""

    # title 是用户希望显示在文档列表里的新标题。
    title: str


class LLMConfigUpdateRequest(BaseModel):
    """更新 LLM 配置的请求体。"""

    # base_url 是 OpenAI-compatible API 的服务地址。
    base_url: str
    # api_key 为 None 时表示保留旧密钥；为空字符串时表示清空旧密钥。
    api_key: str | None = None
    # model 是用于生成文本或图文回答的模型名称。
    model: str
    # timeout_seconds 是请求模型服务时最多等待的秒数。
    timeout_seconds: int
    # 三个 prompt 为 None 时表示不修改旧 prompt。
    course_summary_prompt: str | None = None
    lecture_notes_prompt: str | None = None
    page_chat_prompt: str | None = None


class LLMTestRequest(BaseModel):
    """测试 LLM 文本调用的请求体。"""

    # prompt 是用于测试模型连接的一小段提示词。
    prompt: str = "请用一句中文回复：LLM 配置测试成功。"


class PageChatRequest(BaseModel):
    """当前页问答接口的请求体。"""

    # question 是用户围绕当前页 slides 输入的问题。
    question: str


class NoteBlockPositionUpdateRequest(BaseModel):
    """更新讲稿文字块位置和尺寸的请求体。"""

    # x/y 是文字块左上角距离阅读区左上角的像素坐标。
    x: float
    y: float
    # width/height 是文字块宽高，单位是像素。
    width: float
    height: float
