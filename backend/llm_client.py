"""LLM 配置读取、校验和 OpenAI-compatible 调用封装。"""

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from config import LLM_DEFAULT_CONFIG
from repositories.settings import read_app_settings


@dataclass(frozen=True)
class LLMConfig:
    """后端内部使用的 LLM 配置对象。"""

    # base_url 是 OpenAI-compatible API 的服务地址。
    base_url: str
    # api_key 是模型服务密钥。
    api_key: str
    # model 是模型名称。
    model: str
    # timeout_seconds 是 HTTP 请求超时时间，单位是秒。
    timeout_seconds: int
    # 三个 prompt 分别服务课程简介、逐页讲稿和当前页问答。
    course_summary_prompt: str
    lecture_notes_prompt: str
    page_chat_prompt: str


def mask_secret(secret: str) -> str:
    """把密钥转换成前端可展示的掩码字符串。

    参数：
        secret：真实密钥字符串。

    返回值：
        str：不泄露完整密钥的掩码字符串。
    """

    # 未配置密钥时返回空字符串，前端可以据此展示“未配置”。
    if not secret:
        return ""

    # 很短的密钥不展示首尾字符，避免掩码本身泄露过多信息。
    if len(secret) <= 8:
        return "********"

    # 较长密钥只展示开头和结尾，中间统一用星号遮蔽。
    return f"{secret[:4]}{'*' * 8}{secret[-4:]}"


def normalize_base_url(base_url: str) -> str:
    """规范化 LLM 服务地址。

    参数：
        base_url：用户输入的 OpenAI-compatible API 服务地址。

    返回值：
        str：去掉首尾空白和末尾斜杠后的地址。
    """

    # 不自动补协议，避免把错误输入悄悄变成另一个地址。
    return base_url.strip().rstrip("/")


def normalize_timeout_seconds(timeout_seconds: int | str) -> int:
    """校验并转换 LLM 请求超时时间。

    参数：
        timeout_seconds：用户或环境变量提供的超时时间。

    返回值：
        int：合法的超时时间，单位是秒。
    """

    try:
        normalized_timeout = int(timeout_seconds)
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LLM 超时时间必须是整数秒。",
        ) from error

    if normalized_timeout < 5 or normalized_timeout > 300:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LLM 超时时间必须在 5 到 300 秒之间。",
        )

    return normalized_timeout


def get_llm_config() -> LLMConfig:
    """读取最终生效的 LLM 配置。

    返回值：
        LLMConfig：合并环境变量默认值和 WebUI 保存值后的配置对象。
    """

    # 数据库配置来自 WebUI，优先级高于环境变量默认值。
    stored_settings = read_app_settings()
    merged_settings = {**LLM_DEFAULT_CONFIG, **stored_settings}

    return LLMConfig(
        base_url=normalize_base_url(merged_settings["base_url"]),
        api_key=merged_settings["api_key"],
        model=merged_settings["model"].strip(),
        timeout_seconds=normalize_timeout_seconds(merged_settings["timeout_seconds"]),
        course_summary_prompt=merged_settings["course_summary_prompt"].strip(),
        lecture_notes_prompt=merged_settings["lecture_notes_prompt"].strip(),
        page_chat_prompt=merged_settings["page_chat_prompt"].strip(),
    )


def serialize_llm_config(config: LLMConfig) -> dict[str, str | int | bool]:
    """把 LLM 配置转换成可以返回给前端的字典。

    参数：
        config：后端内部使用的 LLM 配置对象。

    返回值：
        dict[str, str | int | bool]：隐藏真实 API Key 后的配置数据。
    """

    return {
        "base_url": config.base_url,
        "model": config.model,
        "timeout_seconds": config.timeout_seconds,
        "course_summary_prompt": config.course_summary_prompt,
        "lecture_notes_prompt": config.lecture_notes_prompt,
        "page_chat_prompt": config.page_chat_prompt,
        "api_key_configured": bool(config.api_key),
        "api_key_preview": mask_secret(config.api_key),
    }


def validate_llm_config(config: LLMConfig) -> None:
    """校验 LLM 配置是否足够发起请求。

    参数：
        config：需要校验的 LLM 配置。

    返回值：
        None：配置合法时不返回数据；配置缺失时抛出 HTTPException。
    """

    if not config.base_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先配置 LLM_BASE_URL。",
        )

    if not config.api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先配置 LLM_API_KEY。",
        )

    if not config.model:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先配置 LLM_MODEL。",
        )


def build_chat_completions_url(base_url: str) -> str:
    """根据 base_url 生成 OpenAI-compatible chat completions 请求地址。"""

    # 如果用户已经填到完整路径，就直接使用，兼容只暴露完整路径的服务。
    if base_url.endswith("/chat/completions"):
        return base_url

    # 常见服务会把 base_url 配成 https://host/v1。
    return f"{base_url}/chat/completions"


def encode_image_as_data_url(image_path: Path) -> str:
    """把本地 PNG 图片转换成 data URL。

    参数：
        image_path：本地图片路径。

    返回值：
        str：形如 data:image/png;base64,... 的图片文本。
    """

    # 当前页面截图固定保存为 PNG，所以 MIME 类型固定为 image/png。
    encoded_image = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded_image}"


class LLMClient:
    """统一封装 OpenAI-compatible LLM 调用。"""

    def __init__(self, config: LLMConfig):
        """创建 LLMClient 实例。

        参数：
            config：当前生效的 LLM 配置。
        """

        self.config = config

    def complete_text(self, prompt: str) -> str:
        """发送纯文本提示词并返回模型文本回答。"""

        # chat completions 使用 messages 数组表达一轮对话。
        messages = [{"role": "user", "content": prompt}]
        return self._send_chat_completion(messages)

    def complete_with_image(self, prompt: str, image_path: Path) -> str:
        """发送文本加页面截图，并返回模型文本回答。"""

        # 视觉请求把 content 写成文本片段和图片片段的数组。
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": encode_image_as_data_url(image_path)},
                    },
                ],
            }
        ]
        return self._send_chat_completion(messages)

    def _send_chat_completion(self, messages: list[dict[str, Any]]) -> str:
        """向 OpenAI-compatible chat completions 接口发送请求。"""

        # 发请求前统一检查配置，避免服务返回难理解的认证错误。
        validate_llm_config(self.config)

        payload = {"model": self.config.model, "messages": messages}
        request_body = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            url=build_chat_completions_url(self.config.base_url),
            data=request_body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "SlidesReader/0.1 (+OpenAI-compatible client)",
            },
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.config.timeout_seconds,
            ) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            # HTTPError 表示服务端返回 4xx/5xx，尽量把响应体带给前端排查。
            error_body = error.read().decode("utf-8", errors="replace")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LLM 服务返回错误：HTTP {error.code}，{error_body}",
            ) from error
        except urllib.error.URLError as error:
            # URLError 通常代表网络不可达、域名错误或连接失败。
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"无法连接 LLM 服务：{error.reason}",
            ) from error
        except TimeoutError as error:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="LLM 请求超时，请检查服务地址或调大超时时间。",
            ) from error

        try:
            data = json.loads(response_body)
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LLM 服务返回格式不符合 OpenAI-compatible chat completions：{response_body}",
            ) from error

        if not isinstance(content, str) or not content.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="LLM 服务返回了空回答。",
            )

        return content
