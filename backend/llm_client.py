"""LLM 配置读取、校验和 OpenAI-compatible 调用封装。"""

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

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
    # 四个 prompt 分别服务课程简介、逐页讲稿、当前页问答和试卷生成。
    course_summary_prompt: str
    lecture_notes_prompt: str
    page_chat_prompt: str
    exam_generation_prompt: str


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
        exam_generation_prompt=merged_settings["exam_generation_prompt"].strip(),
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
        "exam_generation_prompt": config.exam_generation_prompt,
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


def encode_image_as_data_url(image_path: Path, mime_type: str = "image/png") -> str:
    """把本地图片转换成 data URL。

    参数：
        image_path：本地图片路径。
        mime_type：图片 MIME 类型，例如 image/png、image/jpeg 或 image/webp。

    返回值：
        str：形如 data:image/png;base64,... 的图片文本。
    """

    # base64 是 OpenAI-compatible 图文输入常用的内联图片表达方式。
    encoded_image = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded_image}"


class LLMClient:
    """统一封装 OpenAI-compatible LLM 调用。"""

    def __init__(self, config: LLMConfig):
        """创建 LLMClient 实例。

        参数：
            config：当前生效的 LLM 配置。
        """

        self.config = config

    def complete_text(
        self,
        prompt: str,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
        timeout_seconds: int | None = None,
    ) -> str:
        """发送纯文本提示词并返回模型文本回答。"""

        # chat completions 使用 messages 数组表达一轮对话。
        messages = [{"role": "user", "content": prompt}]
        return self._send_chat_completion(
            messages,
            max_tokens=max_tokens,
            response_format=response_format,
            timeout_seconds=timeout_seconds,
        )

    def stream_text(self, prompt: str) -> Iterator[str]:
        """发送纯文本提示词，并逐段产出模型回答增量。

        参数：
            prompt：发给模型的完整文本提示词。

        返回值：
            Iterator[str]：每次迭代返回模型新生成的一小段文本。
        """

        # 流式接口和非流式接口使用同一套 messages 结构，只是在 payload 中增加 stream。
        messages = [{"role": "user", "content": prompt}]
        yield from self._send_chat_completion_stream(messages)

    def complete_with_image(self, prompt: str, image_path: Path) -> str:
        """发送文本加页面截图，并返回模型文本回答。"""

        # 页面截图固定是 PNG，复用多图方法可以保证图文请求格式只有一处实现。
        return self.complete_with_images(prompt=prompt, images=[(image_path, "image/png")])

    def complete_with_images(self, prompt: str, images: list[tuple[Path, str]]) -> str:
        """发送文本加多张图片，并返回模型文本回答。

        参数：
            prompt：文本提示词。
            images：图片路径和 MIME 类型列表。

        返回值：
            str：模型返回的文本回答。
        """

        messages = self._build_image_messages(prompt=prompt, images=images)
        try:
            return self._send_chat_completion(messages)
        except HTTPException as error:
            # 部分模型/服务不支持图片输入；遇到这种情况时自动回退到纯文本模式，
            # 保证讲稿生成、当前页问答等核心功能在不支持视觉的模型上仍可工作。
            if self._is_image_input_unsupported(error):
                return self.complete_text(prompt)
            raise

    def stream_with_images(self, prompt: str, images: list[tuple[Path, str]]) -> Iterator[str]:
        """发送文本加多张图片，并逐段产出模型回答增量。

        参数：
            prompt：文本提示词。
            images：图片路径和 MIME 类型列表。

        返回值：
            Iterator[str]：每次迭代返回模型新生成的一小段文本。
        """

        # 图文流式请求的 content 结构与非流式请求完全一致。
        messages = self._build_image_messages(prompt=prompt, images=images)
        try:
            yield from self._send_chat_completion_stream(messages)
        except HTTPException as error:
            if self._is_image_input_unsupported(error):
                yield from self.stream_text(prompt)
                return
            raise

    @staticmethod
    def _is_image_input_unsupported(error: HTTPException) -> bool:
        """判断 LLM 错误是否表示当前模型不支持图片输入。"""

        detail = str(error.detail).lower()
        unsupported_markers = [
            "image input not supported",
            "image_url is not supported",
            "images are not supported",
            "does not support image",
            "vision is not supported",
            "不支持图像",
            "不支持图片",
            "image input is not supported",
        ]
        return any(marker in detail for marker in unsupported_markers)

    def _build_image_messages(self, prompt: str, images: list[tuple[Path, str]]) -> list[dict[str, Any]]:
        """构造 OpenAI-compatible 图文 chat messages。"""

        # 视觉请求把 content 写成文本片段和图片片段的数组。
        content_parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image_path, mime_type in images:
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": encode_image_as_data_url(image_path=image_path, mime_type=mime_type),
                    },
                }
            )

        messages = [
            {
                "role": "user",
                "content": content_parts,
            }
        ]
        return messages

    def _send_chat_completion(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
        timeout_seconds: int | None = None,
    ) -> str:
        """向 OpenAI-compatible chat completions 接口发送请求。"""

        # 发请求前统一检查配置，避免服务返回难理解的认证错误。
        validate_llm_config(self.config)

        # 允许单次请求覆盖全局超时；试卷/阶段考试等长输出场景需要更长时间。
        request_timeout = timeout_seconds if timeout_seconds is not None else self.config.timeout_seconds

        last_error: urllib.error.HTTPError | None = None
        for attempt in range(2):
            payload: dict[str, Any] = {"model": self.config.model, "messages": messages}
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens
            # 部分模型/服务不支持 response_format，首次失败后第二次尝试不带该参数。
            if response_format is not None and attempt == 0:
                payload["response_format"] = response_format

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
                    timeout=request_timeout,
                ) as response:
                    response_body = response.read().decode("utf-8")
            except urllib.error.HTTPError as error:
                # HTTPError 表示服务端返回 4xx/5xx；如果带了 response_format，尝试去掉重试一次。
                last_error = error
                if response_format is not None and attempt == 0:
                    continue
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

        # 防御性兜底：循环逻辑保证不会走到这里。
        if last_error is not None:
            error_body = last_error.read().decode("utf-8", errors="replace")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LLM 服务返回错误：HTTP {last_error.code}，{error_body}",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM 请求失败。",
        )

    def _send_chat_completion_stream(self, messages: list[dict[str, Any]]) -> Iterator[str]:
        """向 OpenAI-compatible chat completions 接口发送流式请求。"""

        # 发请求前统一检查配置，错误会被上层流式包装转换成 error 事件。
        validate_llm_config(self.config)

        # stream=True 要求模型服务按 Server-Sent Events 风格持续返回 data 行。
        payload = {"model": self.config.model, "messages": messages, "stream": True}
        request_body = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            url=build_chat_completions_url(self.config.base_url),
            data=request_body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
                "User-Agent": "SlidesReader/0.1 (+OpenAI-compatible client)",
            },
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.config.timeout_seconds,
            ) as response:
                # OpenAI-compatible 流式响应通常是一行一个 data: JSON，最后用 data: [DONE] 结束。
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data:"):
                        continue

                    data_text = line.removeprefix("data:").strip()
                    if data_text == "[DONE]":
                        break

                    try:
                        data = json.loads(data_text)
                    except json.JSONDecodeError as error:
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"LLM 流式返回格式不符合 OpenAI-compatible chat completions：{data_text}",
                        ) from error

                    choices = data.get("choices")
                    if choices == []:
                        # 部分 OpenAI-compatible 服务会在流末尾返回只包含 usage 的统计 chunk。
                        # 这类 chunk 没有文本增量，应该忽略，而不是当成格式错误。
                        continue

                    if not isinstance(choices, list) or not choices:
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"LLM 流式返回格式不符合 OpenAI-compatible chat completions：{data_text}",
                        )

                    first_choice = choices[0]
                    if not isinstance(first_choice, dict):
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"LLM 流式返回格式不符合 OpenAI-compatible chat completions：{data_text}",
                        )

                    delta = first_choice.get("delta") or {}
                    if not isinstance(delta, dict):
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"LLM 流式返回格式不符合 OpenAI-compatible chat completions：{data_text}",
                        )

                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        yield content
        except urllib.error.HTTPError as error:
            error_body = error.read().decode("utf-8", errors="replace")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LLM 服务返回错误：HTTP {error.code}，{error_body}",
            ) from error
        except urllib.error.URLError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"无法连接 LLM 服务：{error.reason}",
            ) from error
        except TimeoutError as error:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="LLM 请求超时，请检查服务地址或调大超时时间。",
            ) from error
