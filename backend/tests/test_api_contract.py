"""后端 API 契约测试。

这些测试关注接口路径、状态码、响应字段和关键副作用，确保拆分代码结构后行为不变。
"""

import importlib
import os
import sys
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """创建使用临时 storage 的 TestClient。

    参数：
        tmp_path：pytest 提供的临时目录。
        monkeypatch：pytest 提供的环境变量和对象替换工具。

    返回值：
        Iterator[TestClient]：已经触发 startup 的 FastAPI 测试客户端。
    """

    # 让后端所有运行数据写入临时目录，避免污染项目真实 storage。
    monkeypatch.setenv("SLIDES_READER_STORAGE_DIR", str(tmp_path / "storage"))

    # 清理已导入的后端模块，保证 config.py 重新读取上面的环境变量。
    backend_modules = [
        module_name
        for module_name in list(sys.modules)
        if module_name in {"app", "main", "config", "database", "generation_service", "pdf_service", "llm_client"}
        or module_name.startswith("routes")
        or module_name.startswith("repositories")
    ]
    for module_name in backend_modules:
        sys.modules.pop(module_name, None)

    app_module = importlib.import_module("app")

    # 上传成功后原逻辑会提交后台课程简介生成；契约测试只验证上传和解析，避免真实请求 LLM。
    monkeypatch.setattr(
        app_module.documents.generation_service,
        "generate_course_summary",
        lambda document_id: None,
    )

    with TestClient(app_module.app) as test_client:
        yield test_client


def make_one_page_pdf() -> bytes:
    """生成一页最小测试 PDF。

    返回值：
        bytes：PDF 文件二进制内容。
    """

    # PyMuPDF 是项目已有依赖，用它生成测试 PDF 可以避免提交额外二进制 fixture。
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Slides Reader contract test")
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def upload_pdf(client: TestClient) -> dict[str, object]:
    """上传一页测试 PDF 并返回响应 JSON。"""

    response = client.post(
        "/api/documents",
        files={"file": ("contract.pdf", make_one_page_pdf(), "application/pdf")},
    )
    assert response.status_code == 201
    return response.json()


def test_health_and_empty_documents(client: TestClient) -> None:
    """健康检查成功，空库文档列表返回空数组。"""

    health_response = client.get("/api/health")
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok", "service": "slides-reader-api"}

    documents_response = client.get("/api/documents")
    assert documents_response.status_code == 200
    assert documents_response.json() == []


def test_llm_config_save_read_mask_keep_and_clear_key(client: TestClient) -> None:
    """LLM 配置读写保持 API Key 掩码、保留旧密钥和清空密钥规则。"""

    first_payload = {
        "base_url": "https://example.test/v1/",
        "api_key": "sk-test-secret",
        "model": "model-a",
        "timeout_seconds": 30,
        "course_summary_prompt": "课程简介 prompt",
        "lecture_notes_prompt": "逐页讲稿 prompt",
        "page_chat_prompt": "当前页问答 prompt",
    }
    first_response = client.patch("/api/llm/config", json=first_payload)
    assert first_response.status_code == 200
    first_data = first_response.json()
    assert first_data["base_url"] == "https://example.test/v1"
    assert first_data["api_key_configured"] is True
    assert first_data["api_key_preview"] == "sk-t********cret"
    assert "sk-test-secret" not in first_response.text

    keep_key_payload = {
        "base_url": "https://example.test/v1",
        "model": "model-b",
        "timeout_seconds": 40,
        "course_summary_prompt": "课程简介 prompt 2",
        "lecture_notes_prompt": "逐页讲稿 prompt 2",
        "page_chat_prompt": "当前页问答 prompt 2",
    }
    keep_response = client.patch("/api/llm/config", json=keep_key_payload)
    assert keep_response.status_code == 200
    keep_data = keep_response.json()
    assert keep_data["model"] == "model-b"
    assert keep_data["api_key_configured"] is True
    assert keep_data["api_key_preview"] == "sk-t********cret"

    clear_key_payload = {**keep_key_payload, "api_key": ""}
    clear_response = client.patch("/api/llm/config", json=clear_key_payload)
    assert clear_response.status_code == 200
    clear_data = clear_response.json()
    assert clear_data["api_key_configured"] is False
    assert clear_data["api_key_preview"] == ""


def test_upload_pdf_pages_status_image_and_delete(client: TestClient) -> None:
    """上传 PDF 后生成记录、页面、截图，删除时清理数据库和本地文件。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]
    assert upload_data["title"] == "contract.pdf"
    assert upload_data["status"] == "ready"
    assert upload_data["page_count"] == 1
    assert upload_data["saved_filename"] == f"{document_id}.pdf"
    assert upload_data["course_summary_status"] == "processing"

    pdf_path = Path(str(upload_data["file_path"]))
    assert pdf_path.exists()

    pages_response = client.get(f"/api/documents/{document_id}/pages")
    assert pages_response.status_code == 200
    pages = pages_response.json()
    assert len(pages) == 1
    page = pages[0]
    assert page["document_id"] == document_id
    assert page["page_number"] == 1
    assert page["status"] == "ready"
    assert page["image_url"] == f"/api/documents/{document_id}/pages/1/image"
    assert page["lecture_notes_status"] == "pending"
    assert page["note_block"] is None

    image_path = Path(page["image_path"])
    assert image_path.exists()

    status_response = client.get(f"/api/documents/{document_id}/status")
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["document_id"] == document_id
    assert status_data["total_pages"] == 1
    assert status_data["lecture_notes_pending_count"] == 1
    assert status_data["pages"][0]["page_number"] == 1

    image_response = client.get(f"/api/documents/{document_id}/pages/1/image")
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"

    delete_response = client.delete(f"/api/documents/{document_id}")
    assert delete_response.status_code == 204
    assert not pdf_path.exists()
    assert not image_path.exists()
    assert client.get("/api/documents").json() == []


def test_page_chat_saves_user_and_assistant_messages(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当前页问答使用 mock LLM 后保存 user 和 assistant 消息。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]
    page = client.get(f"/api/documents/{document_id}/pages").json()[0]

    generation_service = importlib.import_module("generation_service")

    class FakeLLMClient:
        """替代真实 LLMClient 的测试对象。"""

        def __init__(self, config):
            # config 参数保持和真实 LLMClient 构造函数一致。
            self.config = config

        def complete_text(self, prompt: str) -> str:
            # 返回固定回答，让测试不依赖网络和 API Key。
            assert "请解释这一页" in prompt
            return "这是 mock 回答。"

    monkeypatch.setattr(generation_service, "LLMClient", FakeLLMClient)

    response = client.post(
        f"/api/pages/{page['page_id']}/chat",
        json={"question": "请解释这一页"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["user_message"]["role"] == "user"
    assert data["assistant_message"]["role"] == "assistant"
    assert data["assistant_message"]["content"] == "这是 mock 回答。"
    assert [message["role"] for message in data["messages"]] == ["user", "assistant"]


def test_note_block_position_validation_and_update(client: TestClient) -> None:
    """讲稿文字块位置接口校验最小尺寸，并能成功更新。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]

    # 直接写入讲稿和文字块所需状态，模拟讲稿已经生成成功的页面。
    pages_module = importlib.import_module("repositories.pages")
    pages_module.update_page_lecture_notes_status(
        document_id=document_id,
        page_number=1,
        lecture_notes_status="ready",
        lecture_notes="本页讲稿",
        error_message=None,
    )

    page = client.get(f"/api/documents/{document_id}/pages").json()[0]
    note_block = page["note_block"]
    assert note_block is not None

    invalid_response = client.patch(
        f"/api/note-blocks/{note_block['note_block_id']}",
        json={"x": 1, "y": 2, "width": 10, "height": 10},
    )
    assert invalid_response.status_code == 400

    valid_response = client.patch(
        f"/api/note-blocks/{note_block['note_block_id']}",
        json={"x": 42, "y": 43, "width": 180, "height": 120},
    )
    assert valid_response.status_code == 200
    updated = valid_response.json()
    assert updated["x"] == 42
    assert updated["y"] == 43
    assert updated["width"] == 180
    assert updated["height"] == 120
