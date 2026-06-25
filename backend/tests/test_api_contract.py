"""后端 API 契约测试。

这些测试关注接口路径、状态码、响应字段和关键副作用，确保拆分代码结构后行为不变。
"""

import importlib
import json
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
        if module_name
        in {
            "app",
            "main",
            "config",
            "database",
            "generation_service",
            "pdf_service",
            "llm_client",
            "exam_service",
            "phase_exam_service",
        }
        or module_name.startswith("routes")
        or module_name.startswith("repositories")
    ]
    for module_name in backend_modules:
        sys.modules.pop(module_name, None)

    app_module = importlib.import_module("app")

    # 先保存原始生成函数，后面的测试可以直接验证生成函数本身的行为。
    original_generate_course_summary = app_module.documents.generation_service.generate_course_summary
    monkeypatch.setattr(
        app_module.documents.generation_service,
        "_original_generate_course_summary_for_tests",
        original_generate_course_summary,
        raising=False,
    )

    # 上传成功后不应自动提交课程简介生成；如果这里被调用，就说明手动生成约束被破坏。
    def fail_if_course_summary_auto_generates(document_id: str) -> None:
        # document_id 保留在断言消息里，方便定位是哪一次上传意外触发了后台任务。
        raise AssertionError(f"上传后不应自动生成课程简介：{document_id}")

    monkeypatch.setattr(
        app_module.documents.generation_service,
        "generate_course_summary",
        fail_if_course_summary_auto_generates,
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


def create_ready_exam_for_tests(client: TestClient) -> dict[str, object]:
    """创建一份已经处于 ready 状态的试卷，供考试接口测试复用。"""

    # 先上传一份真实文档，让试卷记录满足 document_id 外键关系。
    upload_data = upload_pdf(client)
    document_id = str(upload_data["document_id"])

    # 直接使用 repository 写入试卷，避免测试依赖真实 LLM 输出。
    exams_module = importlib.import_module("repositories.exams")
    exam = exams_module.create_exam_record(
        document_id=document_id,
        title="Contract Exam",
        description="Exam created by API contract tests.",
        total_score=8,
        exam_status="ready",
    )

    # 第一题是选择题，用来验证答案隐藏和错题记录。
    choice_question = exams_module.create_exam_question(
        exam_id=exam["id"],
        question_number=1,
        section="A",
        question_type="choice",
        score=5,
        content="Which option is correct?",
        options=["Alpha", "Beta", "Gamma", "Delta"],
        answer="D",
        explanation="秘密解析：Delta 是正确答案。",
        source_page=1,
        expected_type="text",
        difficulty="easy",
        knowledge_tag="contract choice",
    )

    # 第二题是数字填空题，用来验证数值答案判分和结果恢复。
    fill_question = exams_module.create_exam_question(
        exam_id=exam["id"],
        question_number=1,
        section="B",
        question_type="fill_in",
        score=3,
        content="What is 1 + 1?",
        options=None,
        answer="2",
        explanation="秘密解析：1 + 1 = 2。",
        source_page=1,
        expected_type="number",
        difficulty="easy",
        knowledge_tag="contract fill",
    )

    return {
        "document_id": document_id,
        "exam": exam,
        "choice_question": choice_question,
        "fill_question": fill_question,
    }


def make_png_bytes() -> bytes:
    """返回一张 1x1 PNG 图片的二进制内容。"""

    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01"
        b"\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00"
        b"\x90wS\xde"
        b"\x00\x00\x00\x0cIDAT"
        b"\x08\xd7c\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00"
        b"\xc9\xfe\x92\xef"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


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
        "exam_generation_prompt": "试卷生成 prompt",
    }
    first_response = client.patch("/api/llm/config", json=first_payload)
    assert first_response.status_code == 200
    first_data = first_response.json()
    assert first_data["base_url"] == "https://example.test/v1"
    assert first_data["api_key_configured"] is True
    assert first_data["api_key_preview"] == "sk-t********cret"
    assert first_data["exam_generation_prompt"] == "试卷生成 prompt"
    assert "sk-test-secret" not in first_response.text

    keep_key_payload = {
        "base_url": "https://example.test/v1",
        "model": "model-b",
        "timeout_seconds": 40,
        "course_summary_prompt": "课程简介 prompt 2",
        "lecture_notes_prompt": "逐页讲稿 prompt 2",
        "page_chat_prompt": "当前页问答 prompt 2",
        "exam_generation_prompt": "试卷生成 prompt 2",
    }
    keep_response = client.patch("/api/llm/config", json=keep_key_payload)
    assert keep_response.status_code == 200
    keep_data = keep_response.json()
    assert keep_data["model"] == "model-b"
    assert keep_data["api_key_configured"] is True
    assert keep_data["api_key_preview"] == "sk-t********cret"
    assert keep_data["exam_generation_prompt"] == "试卷生成 prompt 2"

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
    assert upload_data["course_summary_status"] == "pending"

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
    assert status_data["course_summary_status"] == "pending"
    assert status_data["course_summary_ready"] is False
    assert status_data["total_pages"] == 1
    assert status_data["lecture_notes_pending_count"] == 0
    assert status_data["lecture_notes_processing_count"] == 0
    assert status_data["should_poll"] is False
    assert status_data["pages"][0]["page_number"] == 1

    image_response = client.get(f"/api/documents/{document_id}/pages/1/image")
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"

    delete_response = client.delete(f"/api/documents/{document_id}")
    assert delete_response.status_code == 204
    assert not pdf_path.exists()
    assert not image_path.exists()
    assert client.get("/api/documents").json() == []


def test_legacy_absolute_file_paths_can_be_read_and_deleted(client: TestClient) -> None:
    """项目迁移后，旧绝对路径不应让文档变成无法读取或删除的僵尸记录。"""

    upload_data = upload_pdf(client)
    document_id = str(upload_data["document_id"])
    pdf_path = Path(str(upload_data["file_path"]))
    page = client.get(f"/api/documents/{document_id}/pages").json()[0]
    image_path = Path(page["image_path"])
    assert pdf_path.exists()
    assert image_path.exists()

    legacy_root = Path("/old/slides-reader/New/storage")
    legacy_pdf_path = legacy_root / "documents" / pdf_path.name
    legacy_image_path = legacy_root / "pages" / image_path.name

    database = importlib.import_module("database")
    with database.get_database_connection() as connection:
        connection.execute(
            "UPDATE documents SET file_path = ? WHERE id = ?",
            (str(legacy_pdf_path), document_id),
        )
        connection.execute(
            "UPDATE pages SET image_path = ? WHERE document_id = ?",
            (str(legacy_image_path), document_id),
        )
        connection.commit()

    file_response = client.get(f"/api/documents/{document_id}/file")
    assert file_response.status_code == 200
    assert file_response.headers["content-type"] == "application/pdf"

    image_response = client.get(f"/api/documents/{document_id}/pages/1/image")
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"

    delete_response = client.delete(f"/api/documents/{document_id}")
    assert delete_response.status_code == 204
    assert not pdf_path.exists()
    assert not image_path.exists()
    assert client.get("/api/documents").json() == []


def test_manual_course_summary_generation_starts_only_when_requested(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """手动调用课程简介接口时才进入生成流程。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]
    generation_service = importlib.import_module("generation_service")
    called_document_ids: list[str] = []

    def fake_generate_course_summary(document_id_for_task: str) -> None:
        # 记录后台任务收到的文档 ID，避免真实请求 LLM。
        called_document_ids.append(document_id_for_task)

    monkeypatch.setattr(generation_service, "generate_course_summary", fake_generate_course_summary)

    response = client.post(f"/api/documents/{document_id}/course-summary/regenerate")
    assert response.status_code == 200
    assert response.json() == {"status": "processing", "document_id": document_id}
    assert called_document_ids == [document_id]

    status_response = client.get(f"/api/documents/{document_id}/status")
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["course_summary_status"] == "processing"
    assert status_data["should_poll"] is True


def test_course_summary_generation_does_not_auto_generate_lecture_notes(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """课程简介生成成功后不会自动重置或生成逐页讲稿。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]
    pages_module = importlib.import_module("repositories.pages")
    generation_service = importlib.import_module("generation_service")

    # 先写入一份已有讲稿，用来确认生成简介不会清空或重置讲稿状态。
    pages_module.update_page_lecture_notes_status(
        document_id=document_id,
        page_number=1,
        lecture_notes_status="ready",
        lecture_notes="已有讲稿",
        error_message=None,
    )

    class FakeLLMClient:
        """替代真实 LLMClient 的课程简介测试对象。"""

        def __init__(self, config):
            # config 参数保持和真实 LLMClient 构造函数一致。
            self.config = config

        def complete_text(self, prompt: str) -> str:
            # 确认 prompt 仍然包含上传 PDF 中提取出的文字。
            assert "Slides Reader contract test" in prompt
            return "手动生成的课程简介"

    def fail_if_lecture_notes_auto_generates(document_id_for_task: str) -> None:
        # 如果未来又在课程简介生成后串起整份讲稿生成，这个断言会直接暴露回归。
        raise AssertionError(f"课程简介生成后不应自动生成逐页讲稿：{document_id_for_task}")

    monkeypatch.setattr(generation_service, "LLMClient", FakeLLMClient)
    monkeypatch.setattr(
        generation_service,
        "generate_document_lecture_notes",
        fail_if_lecture_notes_auto_generates,
    )

    original_generate_course_summary = generation_service._original_generate_course_summary_for_tests
    original_generate_course_summary(document_id)

    documents = client.get("/api/documents").json()
    document = next(item for item in documents if item["document_id"] == document_id)
    assert document["course_summary_status"] == "ready"
    assert document["course_summary"] == "手动生成的课程简介"

    page = client.get(f"/api/documents/{document_id}/pages").json()[0]
    assert page["lecture_notes_status"] == "ready"
    assert page["lecture_notes"] == "已有讲稿"


def test_lecture_notes_queue_keeps_existing_notes_until_new_result(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """讲稿入队不会清空旧讲稿，清空等待队列后旧讲稿状态恢复为 ready。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]
    documents_module = importlib.import_module("repositories.documents")
    pages_module = importlib.import_module("repositories.pages")
    generation_service = importlib.import_module("generation_service")

    documents_module.update_course_summary_status(
        document_id=document_id,
        summary_status="ready",
        course_summary="已有课程简介",
        error_message=None,
    )
    pages_module.update_page_lecture_notes_status(
        document_id=document_id,
        page_number=1,
        lecture_notes_status="ready",
        lecture_notes="旧讲稿",
        error_message=None,
    )

    def keep_queue_waiting(document_id_for_task: str) -> None:
        # 路由应只负责入队；这里阻止测试里的后台任务真正消费队列，便于检查 waiting 状态。
        assert document_id_for_task == document_id

    monkeypatch.setattr(generation_service, "generate_document_lecture_notes", keep_queue_waiting)

    enqueue_response = client.post(f"/api/documents/{document_id}/lecture-notes/regenerate")
    assert enqueue_response.status_code == 200
    assert enqueue_response.json() == {"status": "queued", "document_id": document_id}

    status_after_enqueue = client.get(f"/api/documents/{document_id}/status").json()
    assert status_after_enqueue["lecture_notes_ready_count"] == 1
    assert status_after_enqueue["lecture_notes_pending_count"] == 1
    assert status_after_enqueue["pages"][0]["lecture_notes_status"] == "pending"

    page_after_enqueue = client.get(f"/api/documents/{document_id}/pages").json()[0]
    assert page_after_enqueue["lecture_notes"] == "旧讲稿"
    assert page_after_enqueue["lecture_notes_status"] == "pending"

    clear_response = client.delete(f"/api/documents/{document_id}/lecture-notes/queue")
    assert clear_response.status_code == 200
    assert clear_response.json() == {
        "status": "cleared",
        "document_id": document_id,
        "cleared_count": 1,
    }

    status_after_clear = client.get(f"/api/documents/{document_id}/status").json()
    assert status_after_clear["lecture_notes_pending_count"] == 0
    assert status_after_clear["pages"][0]["lecture_notes_status"] == "ready"

    page_after_clear = client.get(f"/api/documents/{document_id}/pages").json()[0]
    assert page_after_clear["lecture_notes"] == "旧讲稿"
    assert page_after_clear["lecture_notes_status"] == "ready"


def test_generate_remaining_lecture_notes_enqueues_and_starts_generation(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """生成剩余讲稿会补齐缺讲稿页面、解除暂停，并启动后台消费者。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]
    documents_module = importlib.import_module("repositories.documents")
    generation_service = importlib.import_module("generation_service")
    started_document_ids: list[str] = []

    documents_module.update_course_summary_status(
        document_id=document_id,
        summary_status="ready",
        course_summary="已有课程简介",
        error_message=None,
    )
    documents_module.set_lecture_notes_paused(document_id=document_id, paused=True)

    def record_generation_start(document_id_for_task: str) -> None:
        started_document_ids.append(document_id_for_task)

    monkeypatch.setattr(generation_service, "generate_document_lecture_notes", record_generation_start)

    response = client.post(f"/api/documents/{document_id}/lecture-notes/remaining")
    assert response.status_code == 200
    assert response.json() == {
        "status": "queued",
        "document_id": document_id,
        "queued_count": 1,
        "started": True,
    }
    assert started_document_ids == [document_id]

    status_after_enqueue = client.get(f"/api/documents/{document_id}/status").json()
    assert status_after_enqueue["lecture_notes_paused"] is False
    assert status_after_enqueue["lecture_notes_pending_count"] == 1

    second_response = client.post(f"/api/documents/{document_id}/lecture-notes/remaining")
    assert second_response.status_code == 200
    assert second_response.json() == {
        "status": "queued",
        "document_id": document_id,
        "queued_count": 0,
        "started": True,
    }
    assert started_document_ids == [document_id, document_id]


def test_resume_lecture_notes_does_not_enqueue_missing_pages(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """继续生成只解除暂停并启动已有队列，不自动把缺讲稿页面补进队列。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]
    documents_module = importlib.import_module("repositories.documents")
    generation_service = importlib.import_module("generation_service")

    documents_module.update_course_summary_status(
        document_id=document_id,
        summary_status="ready",
        course_summary="已有课程简介",
        error_message=None,
    )
    documents_module.set_lecture_notes_paused(document_id=document_id, paused=True)

    def keep_queue_untouched(document_id_for_task: str) -> None:
        # 这里允许 resume 启动后台任务，但队列为空时任务不会生成任何页面。
        assert document_id_for_task == document_id

    monkeypatch.setattr(generation_service, "generate_document_lecture_notes", keep_queue_untouched)

    response = client.post(f"/api/documents/{document_id}/lecture-notes/resume")
    assert response.status_code == 200
    assert response.json() == {
        "status": "resumed",
        "document_id": document_id,
        "lecture_notes_paused": False,
    }

    status_after_resume = client.get(f"/api/documents/{document_id}/status").json()
    assert status_after_resume["lecture_notes_paused"] is False
    assert status_after_resume["lecture_notes_pending_count"] == 0


def test_lecture_notes_generation_strips_outer_markdown_fence(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """逐页讲稿保存前会清掉 LLM 包住整段回答的 markdown 代码围栏。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]
    documents_module = importlib.import_module("repositories.documents")
    generation_service = importlib.import_module("generation_service")

    documents_module.update_course_summary_status(
        document_id=document_id,
        summary_status="ready",
        course_summary="课程简介",
        error_message=None,
    )
    document = {
        "id": document_id,
        "title": upload_data["title"],
        "page_count": upload_data["page_count"],
        "course_summary": "课程简介",
    }
    page = importlib.import_module("repositories.pages").get_page_for_lecture_notes_by_id(
        client.get(f"/api/documents/{document_id}/pages").json()[0]["page_id"]
    )

    class FakeLLMClient:
        def __init__(self, config):
            self.config = config

        def complete_with_image(self, prompt: str, image_path: Path) -> str:
            assert "课程简介" in prompt
            assert image_path.exists()
            return "```markdown\n## 本页核心观点\n正文内容。\n```"

    monkeypatch.setattr(generation_service, "LLMClient", FakeLLMClient)
    monkeypatch.setattr(generation_service, "LLM_TRANSIENT_RETRY_DELAYS_SECONDS", [0.0, 0.0, 0.0])

    generation_service.generate_single_page_lecture_notes(document=document, page=page)

    pages_after_generation = client.get(f"/api/documents/{document_id}/pages").json()
    generated_page = pages_after_generation[0]
    assert generated_page["lecture_notes_status"] == "ready"
    assert generated_page["lecture_notes"] == "## 本页核心观点\n正文内容。"
    assert generated_page["note_block"]["content"] == "## 本页核心观点\n正文内容。"


def test_lecture_notes_generation_retries_transient_overload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Kimi 429/overloaded 这类临时错误会自动重试，而不是马上记为失败。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]
    documents_module = importlib.import_module("repositories.documents")
    generation_service = importlib.import_module("generation_service")

    documents_module.update_course_summary_status(
        document_id=document_id,
        summary_status="ready",
        course_summary="课程简介",
        error_message=None,
    )
    document = {
        "id": document_id,
        "title": upload_data["title"],
        "page_count": upload_data["page_count"],
        "course_summary": "课程简介",
    }
    page = importlib.import_module("repositories.pages").get_page_for_lecture_notes_by_id(
        client.get(f"/api/documents/{document_id}/pages").json()[0]["page_id"]
    )
    attempts = {"count": 0}

    class FakeLLMClient:
        def __init__(self, config):
            self.config = config

        def complete_with_image(self, prompt: str, image_path: Path) -> str:
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise generation_service.HTTPException(
                    status_code=502,
                    detail='LLM 服务返回错误：HTTP 429，{"error":{"type":"engine_overloaded_error"}}',
                )
            return "重试后的讲稿"

    monkeypatch.setattr(generation_service, "LLMClient", FakeLLMClient)
    monkeypatch.setattr(generation_service, "LLM_TRANSIENT_RETRY_DELAYS_SECONDS", [0.0, 0.0, 0.0])

    generation_service.generate_single_page_lecture_notes(document=document, page=page)
    assert attempts["count"] == 2

    generated_page = client.get(f"/api/documents/{document_id}/pages").json()[0]
    assert generated_page["lecture_notes_status"] == "ready"
    assert generated_page["lecture_notes"] == "重试后的讲稿"


def test_lecture_notes_generation_falls_back_to_text_after_transient_image_failures(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """图文讲稿连续临时失败后，会降级为纯文本讲稿，避免页面永久失败。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]
    documents_module = importlib.import_module("repositories.documents")
    generation_service = importlib.import_module("generation_service")

    documents_module.update_course_summary_status(
        document_id=document_id,
        summary_status="ready",
        course_summary="课程简介",
        error_message=None,
    )
    document = {
        "id": document_id,
        "title": upload_data["title"],
        "page_count": upload_data["page_count"],
        "course_summary": "课程简介",
    }
    page = importlib.import_module("repositories.pages").get_page_for_lecture_notes_by_id(
        client.get(f"/api/documents/{document_id}/pages").json()[0]["page_id"]
    )
    calls = {"image": 0, "text": 0}

    class FakeLLMClient:
        def __init__(self, config):
            self.config = config

        def complete_with_image(self, prompt: str, image_path: Path) -> str:
            calls["image"] += 1
            raise generation_service.HTTPException(
                status_code=502,
                detail='LLM 服务返回错误：HTTP 429，{"error":{"type":"engine_overloaded_error"}}',
            )

        def complete_text(self, prompt: str) -> str:
            calls["text"] += 1
            assert "不要使用 ```markdown" in prompt
            return "纯文本兜底讲稿"

    monkeypatch.setattr(generation_service, "LLMClient", FakeLLMClient)
    monkeypatch.setattr(generation_service, "LLM_TRANSIENT_RETRY_DELAYS_SECONDS", [0.0, 0.0, 0.0])

    generation_service.generate_single_page_lecture_notes(document=document, page=page)

    assert calls == {"image": 4, "text": 1}
    generated_page = client.get(f"/api/documents/{document_id}/pages").json()[0]
    assert generated_page["lecture_notes_status"] == "ready"
    assert generated_page["lecture_notes"] == "纯文本兜底讲稿"


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
    assert data["user_message"]["attachments"] == []


def test_page_chat_stream_saves_messages_and_returns_deltas(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """流式当前页问答会返回增量事件，并在结束后保存完整 assistant 消息。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]
    page = client.get(f"/api/documents/{document_id}/pages").json()[0]
    generation_service = importlib.import_module("generation_service")

    class FakeLLMClient:
        """替代真实 LLMClient 的流式纯文本测试对象。"""

        def __init__(self, config):
            # config 参数保持和真实 LLMClient 构造函数一致。
            self.config = config

        def stream_text(self, prompt: str):
            # 流式接口应沿用当前页 prompt，并按顺序吐出文本片段。
            assert "请流式解释这一页" in prompt
            yield "第一段"
            yield "，第二段。"

    monkeypatch.setattr(generation_service, "LLMClient", FakeLLMClient)

    response = client.post(
        f"/api/pages/{page['page_id']}/chat/stream",
        json={"question": "请流式解释这一页"},
    )
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.strip().splitlines()]
    assert [event["type"] for event in events] == ["user_message", "delta", "delta", "done"]
    assert events[1]["content"] == "第一段"
    assert events[2]["content"] == "，第二段。"
    assert events[3]["assistant_message"]["content"] == "第一段，第二段。"
    assert [message["role"] for message in events[3]["messages"]] == ["user", "assistant"]


def test_page_chat_multipart_image_attachment_persists_and_file_can_be_read(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """multipart 当前页问答会保存图片附件，并能通过文件接口读取。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]
    page = client.get(f"/api/documents/{document_id}/pages").json()[0]
    generation_service = importlib.import_module("generation_service")
    seen_image_counts: list[int] = []

    class FakeLLMClient:
        """替代真实 LLMClient 的图文问答测试对象。"""

        def __init__(self, config):
            # config 参数保持和真实 LLMClient 构造函数一致。
            self.config = config

        def complete_with_images(self, prompt: str, images: list[tuple[Path, str]]) -> str:
            # 本轮上传的一张 PNG 应该被加入图文请求。
            assert "请看这张图" in prompt
            seen_image_counts.append(len(images))
            assert images[0][1] == "image/png"
            return "这是图文 mock 回答。"

        def complete_text(self, prompt: str) -> str:
            # 有图片时不应该降级成纯文本请求。
            raise AssertionError("有图片附件时不应调用 complete_text。")

    monkeypatch.setattr(generation_service, "LLMClient", FakeLLMClient)

    response = client.post(
        f"/api/pages/{page['page_id']}/chat",
        data={"question": "请看这张图"},
        files={"attachments": ("example.png", make_png_bytes(), "image/png")},
    )
    assert response.status_code == 200
    data = response.json()
    assert seen_image_counts == [1]

    user_attachments = data["user_message"]["attachments"]
    assert len(user_attachments) == 1
    attachment = user_attachments[0]
    assert attachment["kind"] == "image"
    assert attachment["filename"] == "example.png"
    assert attachment["mime_type"] == "image/png"
    assert attachment["file_url"] == f"/api/chat-attachments/{attachment['attachment_id']}/file"

    file_response = client.get(attachment["file_url"])
    assert file_response.status_code == 200
    assert file_response.headers["content-type"] == "image/png"
    assert file_response.content == make_png_bytes()

    pages_after_chat = client.get(f"/api/documents/{document_id}/pages").json()
    persisted_attachment = pages_after_chat[0]["chat_messages"][0]["attachments"][0]
    assert persisted_attachment["attachment_id"] == attachment["attachment_id"]


def test_page_chat_with_image_falls_back_to_text_after_transient_overload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当前页图文问答遇到 Kimi 临时过载后，会降级为纯文本回答。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]
    page = client.get(f"/api/documents/{document_id}/pages").json()[0]
    generation_service = importlib.import_module("generation_service")
    calls = {"image": 0, "text": 0}

    class FakeLLMClient:
        def __init__(self, config):
            self.config = config

        def complete_with_images(self, prompt: str, images: list[tuple[Path, str]]) -> str:
            calls["image"] += 1
            raise generation_service.HTTPException(
                status_code=502,
                detail='LLM 服务返回错误：HTTP 429，{"error":{"type":"engine_overloaded_error"}}',
            )

        def complete_text(self, prompt: str) -> str:
            calls["text"] += 1
            assert "图文过载后回答" in prompt
            return "纯文本兜底回答"

    monkeypatch.setattr(generation_service, "LLMClient", FakeLLMClient)
    monkeypatch.setattr(generation_service, "LLM_TRANSIENT_RETRY_DELAYS_SECONDS", [0.0, 0.0, 0.0])

    response = client.post(
        f"/api/pages/{page['page_id']}/chat",
        data={"question": "图文过载后回答"},
        files={"attachments": ("fallback.png", make_png_bytes(), "image/png")},
    )
    assert response.status_code == 200
    data = response.json()
    assert calls == {"image": 4, "text": 1}
    assert data["assistant_message"]["content"] == "纯文本兜底回答"


def test_page_chat_stream_with_image_falls_back_to_text_stream_after_transient_overload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当前页图文流式问答遇到 Kimi 临时过载后，会降级为纯文本流。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]
    page = client.get(f"/api/documents/{document_id}/pages").json()[0]
    generation_service = importlib.import_module("generation_service")
    calls = {"image_stream": 0, "text_stream": 0}

    class FakeLLMClient:
        def __init__(self, config):
            self.config = config

        def stream_with_images(self, prompt: str, images: list[tuple[Path, str]]):
            calls["image_stream"] += 1
            raise generation_service.HTTPException(
                status_code=502,
                detail='LLM 服务返回错误：HTTP 429，{"error":{"type":"engine_overloaded_error"}}',
            )
            yield ""

        def stream_text(self, prompt: str):
            calls["text_stream"] += 1
            assert "流式图文过载后回答" in prompt
            yield "纯文本"
            yield "流回答"

    monkeypatch.setattr(generation_service, "LLMClient", FakeLLMClient)

    response = client.post(
        f"/api/pages/{page['page_id']}/chat/stream",
        data={"question": "流式图文过载后回答"},
        files={"attachments": ("stream-fallback.png", make_png_bytes(), "image/png")},
    )
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.strip().splitlines()]
    assert calls == {"image_stream": 1, "text_stream": 1}
    assert [event["type"] for event in events] == ["user_message", "delta", "delta", "done"]
    assert events[-1]["assistant_message"]["content"] == "纯文本流回答"


def test_page_chat_stream_with_image_uses_stream_with_images(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """流式图文当前页问答会保存附件，并调用图文流式 LLM 接口。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]
    page = client.get(f"/api/documents/{document_id}/pages").json()[0]
    generation_service = importlib.import_module("generation_service")
    seen_image_counts: list[int] = []

    class FakeLLMClient:
        """替代真实 LLMClient 的流式图文测试对象。"""

        def __init__(self, config):
            self.config = config

        def stream_with_images(self, prompt: str, images: list[tuple[Path, str]]):
            assert "请流式看图" in prompt
            seen_image_counts.append(len(images))
            assert images[0][1] == "image/png"
            yield "图文"
            yield "回答"

        def stream_text(self, prompt: str):
            raise AssertionError("有图片附件时不应调用 stream_text。")

    monkeypatch.setattr(generation_service, "LLMClient", FakeLLMClient)

    response = client.post(
        f"/api/pages/{page['page_id']}/chat/stream",
        data={"question": "请流式看图"},
        files={"attachments": ("stream.png", make_png_bytes(), "image/png")},
    )
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.strip().splitlines()]
    assert seen_image_counts == [1]
    assert events[0]["type"] == "user_message"
    assert len(events[0]["message"]["attachments"]) == 1
    assert events[-1]["assistant_message"]["content"] == "图文回答"


def test_llm_stream_ignores_usage_only_chunks(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLMClient 流式解析应忽略 choices 为空的 usage-only chunk。"""

    llm_client_module = importlib.import_module("llm_client")
    config = llm_client_module.LLMConfig(
        base_url="https://example.test/v1",
        api_key="sk-test",
        model="gpt-5.5",
        timeout_seconds=30,
        course_summary_prompt="课程简介 prompt",
        lecture_notes_prompt="逐页讲稿 prompt",
        page_chat_prompt="当前页问答 prompt",
        exam_generation_prompt="试卷生成 prompt",
    )

    class FakeStreamResponse:
        """模拟 urllib 返回的 SSE 行迭代响应。"""

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def __iter__(self):
            yield 'data: {"choices":[{"delta":{"content":"第一段"}}]}\n'.encode("utf-8")
            yield (
                b'data: {"id":"resp_1","object":"chat.completion.chunk",'
                b'"choices":[],"usage":{"prompt_tokens":1,"completion_tokens":1}}\n'
            )
            yield 'data: {"choices":[{"delta":{"content":"第二段"}}]}\n'.encode("utf-8")
            yield b"data: [DONE]\n"

    def fake_urlopen(request, timeout):
        # request 和 timeout 参数保持 urllib.request.urlopen 的调用形态。
        return FakeStreamResponse()

    monkeypatch.setattr(llm_client_module.urllib.request, "urlopen", fake_urlopen)

    client_instance = llm_client_module.LLMClient(config)
    assert list(client_instance.stream_text("测试")) == ["第一段", "第二段"]


def test_page_chat_rejects_invalid_and_too_many_attachments(client: TestClient) -> None:
    """当前页问答会拒绝非图片和超过数量限制的附件。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]
    page = client.get(f"/api/documents/{document_id}/pages").json()[0]

    invalid_response = client.post(
        f"/api/pages/{page['page_id']}/chat",
        data={"question": "这不是图片"},
        files={"attachments": ("note.txt", b"not image", "text/plain")},
    )
    assert invalid_response.status_code == 400
    assert "只支持上传 PNG、JPEG 或 WebP 图片" in invalid_response.text

    too_many_files = [
        ("attachments", (f"image-{index}.png", make_png_bytes(), "image/png"))
        for index in range(5)
    ]
    too_many_response = client.post(
        f"/api/pages/{page['page_id']}/chat",
        data={"question": "图片太多"},
        files=too_many_files,
    )
    assert too_many_response.status_code == 400
    assert "每次最多只能上传 4 张图片" in too_many_response.text


def test_page_chat_followup_uses_recent_history_images(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """第二轮不带图片追问时，会自动带入同页最近历史图片。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]
    page = client.get(f"/api/documents/{document_id}/pages").json()[0]
    generation_service = importlib.import_module("generation_service")
    seen_image_counts: list[int] = []

    class FakeLLMClient:
        """记录每轮图文请求携带图片数量的测试对象。"""

        def __init__(self, config):
            self.config = config

        def complete_with_images(self, prompt: str, images: list[tuple[Path, str]]) -> str:
            seen_image_counts.append(len(images))
            return f"图文回答 {len(seen_image_counts)}"

        def complete_text(self, prompt: str) -> str:
            raise AssertionError("有历史图片时也应调用 complete_with_images。")

    monkeypatch.setattr(generation_service, "LLMClient", FakeLLMClient)

    first_response = client.post(
        f"/api/pages/{page['page_id']}/chat",
        data={"question": "第一轮带图"},
        files={"attachments": ("first.png", make_png_bytes(), "image/png")},
    )
    assert first_response.status_code == 200

    second_response = client.post(
        f"/api/pages/{page['page_id']}/chat",
        json={"question": "第二轮追问"},
    )
    assert second_response.status_code == 200
    assert seen_image_counts == [1, 1]


def test_delete_document_removes_chat_attachment_files(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """删除文档会同步删除聊天附件记录和本地图片文件。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]
    page = client.get(f"/api/documents/{document_id}/pages").json()[0]
    generation_service = importlib.import_module("generation_service")

    class FakeLLMClient:
        """替代真实 LLMClient 的图文问答测试对象。"""

        def __init__(self, config):
            self.config = config

        def complete_with_images(self, prompt: str, images: list[tuple[Path, str]]) -> str:
            return "图文回答"

    monkeypatch.setattr(generation_service, "LLMClient", FakeLLMClient)

    response = client.post(
        f"/api/pages/{page['page_id']}/chat",
        data={"question": "带图后删除文档"},
        files={"attachments": ("delete-me.png", make_png_bytes(), "image/png")},
    )
    assert response.status_code == 200
    attachment = response.json()["user_message"]["attachments"][0]
    attachments_module = importlib.import_module("repositories.chat_attachments")
    attachment_row = attachments_module.get_chat_attachment_file_row(attachment["attachment_id"])
    attachment_path = Path(attachment_row["file_path"])
    assert attachment_path.exists()

    delete_response = client.delete(f"/api/documents/{document_id}")
    assert delete_response.status_code == 204
    assert not attachment_path.exists()
    assert attachments_module.get_chat_attachment_file_row(attachment["attachment_id"]) is None


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


def test_exam_validation_converts_non_numeric_fill_in_answers(client: TestClient) -> None:
    """试卷生成校验会把非数字填空题转成单选题，避免整份试卷失败。"""

    exam_service = importlib.import_module("exam_service")
    exam_data = {
        "title": "Converted Exam",
        "sections": [
            {
                "name": "B",
                "questions": [
                    {
                        "number": 1,
                        "type": "fill_in",
                        "score": 5,
                        "content": "In Python, the ______ operator returns the remainder.",
                        "answer": "%",
                        "explanation": "取模运算符。",
                        "source_page": 1,
                        "expected_type": "number",
                    },
                    {
                        "number": 2,
                        "type": "fill_in",
                        "score": 5,
                        "content": "What is 10 % 3?",
                        "answer": "1",
                        "explanation": "10 除以 3 的余数是 1。",
                        "source_page": 1,
                        "expected_type": "number",
                    },
                ],
            }
        ],
    }

    exam_service.validate_exam_data(exam_data)
    converted_question = exam_data["sections"][0]["questions"][0]
    numeric_question = exam_data["sections"][0]["questions"][1]

    assert converted_question["type"] == "choice"
    assert converted_question["answer"] == "A"
    assert converted_question["options"][0] == "%"
    assert converted_question["expected_type"] == "text"
    assert numeric_question["type"] == "fill_in"
    assert numeric_question["answer"] == "1"
    assert numeric_question["expected_type"] == "number"


def test_exam_reading_can_hide_answers_for_take_view(client: TestClient) -> None:
    """答题页读取试卷时可以只拿元数据和无答案题目，避免前端提前拿到正确答案。"""

    created = create_ready_exam_for_tests(client)
    exam_id = created["exam"]["id"]

    # 试卷元数据读取必须支持不带 questions，前端刷新答题页时可以先拿标题和状态。
    metadata_response = client.get(f"/api/exams/{exam_id}?include_questions=false")
    assert metadata_response.status_code == 200
    metadata = metadata_response.json()
    assert metadata["id"] == exam_id
    assert metadata["status"] == "ready"
    assert "questions" not in metadata

    # 答题页题目列表不应包含 answer 和 explanation，否则用户能在浏览器里看到答案。
    questions_response = client.get(f"/api/exams/{exam_id}/questions?include_answer=false")
    assert questions_response.status_code == 200
    questions = questions_response.json()
    assert len(questions) == 2
    assert {question["question_type"] for question in questions} == {"choice", "fill_in"}
    assert all("answer" not in question for question in questions)
    assert all("explanation" not in question for question in questions)


def test_exam_attempt_result_can_be_reloaded_without_frontend_memory(client: TestClient) -> None:
    """提交答题后，结果页应能用 attempt_id 重新读取结果和解析，支持页面刷新。"""

    created = create_ready_exam_for_tests(client)
    exam_id = created["exam"]["id"]
    choice_question = created["choice_question"]
    fill_question = created["fill_question"]

    submit_response = client.post(
        f"/api/exams/{exam_id}/attempts",
        json={
            "answers": {
                choice_question["id"]: "A",
                fill_question["id"]: "2",
            }
        },
    )
    assert submit_response.status_code == 200
    submitted_result = submit_response.json()
    attempt_id = submitted_result["attempt"]["id"]
    assert submitted_result["total_score"] == 3
    assert submitted_result["max_score"] == 8
    assert submitted_result["question_results"][0]["max_score"] == 5
    assert submitted_result["question_results"][1]["max_score"] == 3

    reload_response = client.get(f"/api/exams/{exam_id}/attempts/{attempt_id}/result")
    assert reload_response.status_code == 200
    reloaded_result = reload_response.json()
    assert reloaded_result["attempt"]["id"] == attempt_id
    assert reloaded_result["total_score"] == submitted_result["total_score"]
    assert reloaded_result["max_score"] == submitted_result["max_score"]
    assert len(reloaded_result["questions"]) == 2
    assert reloaded_result["questions"][0]["answer"] == "D"
    assert reloaded_result["questions"][0]["explanation"] == "秘密解析：Delta 是正确答案。"
    assert reloaded_result["question_results"][0]["score"] == 0
    assert reloaded_result["question_results"][0]["max_score"] == 5


def test_exam_background_wrapper_marks_exam_failed_when_service_raises(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """试卷后台任务包装层遇到未处理异常时，应兜底把试卷状态更新为 failed。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]

    exams_module = importlib.import_module("repositories.exams")
    exam_routes = importlib.import_module("routes.exams")

    exam = exams_module.create_exam_record(
        document_id=document_id,
        title="Pending exam",
        description=None,
        total_score=100,
        exam_status="pending",
    )

    def fail_without_status_update(document_id: str, exam_id: str, difficulty: str) -> None:
        # 模拟 service 在来得及更新状态前就抛出异常，验证路由 wrapper 的最后防线。
        raise RuntimeError(f"simulated exam task failure: {exam_id}")

    monkeypatch.setattr(exam_routes, "generate_exam", fail_without_status_update)

    exam_routes._generate_exam_safely(
        exam_id=exam["id"],
        document_id=document_id,
        difficulty="medium",
    )

    updated_exam = exams_module.get_exam_by_id(exam["id"])
    assert updated_exam is not None
    assert updated_exam["status"] == "failed"
    assert "simulated exam task failure" in updated_exam["error_message"]


def test_phase_exam_background_wrapper_marks_phase_exam_failed_when_service_raises(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """阶段考试后台任务包装层遇到未处理异常时，应兜底把阶段考试状态更新为 failed。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]

    phase_exams_module = importlib.import_module("repositories.phase_exams")
    phase_exam_routes = importlib.import_module("routes.phase_exams")

    phase_exam = phase_exams_module.create_phase_exam_record(
        name="Pending phase",
        document_ids=[document_id],
        difficulty="medium",
        phase_exam_status="processing",
    )

    def fail_without_status_update(
        document_ids: list[str],
        name: str,
        difficulty: str,
        phase_exam_id: str,
    ) -> None:
        # 模拟 service 在来得及更新状态前就抛出异常，验证路由 wrapper 的最后防线。
        raise RuntimeError(f"simulated phase task failure: {phase_exam_id}")

    monkeypatch.setattr(phase_exam_routes, "generate_phase_exam", fail_without_status_update)

    phase_exam_routes._generate_phase_exam_safely(
        phase_exam_id=phase_exam["id"],
        document_ids=[document_id],
        name="Pending phase",
        difficulty="medium",
    )

    updated_phase_exam = phase_exams_module.get_phase_exam_by_id(phase_exam["id"])
    assert updated_phase_exam is not None
    assert updated_phase_exam["status"] == "failed"
    assert "simulated phase task failure" in updated_phase_exam["error_message"]


def test_phase_exam_generation_failure_keeps_link_to_failed_exam(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """阶段考试生成失败时，phase_exam 仍应关联已创建的 failed exam，避免留下孤儿记录。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]

    exams_module = importlib.import_module("repositories.exams")
    phase_exams_module = importlib.import_module("repositories.phase_exams")
    phase_exam_service = importlib.import_module("phase_exam_service")

    phase_exam = phase_exams_module.create_phase_exam_record(
        name="Broken Phase",
        document_ids=[document_id],
        difficulty="medium",
        phase_exam_status="processing",
    )

    def fail_before_llm(document_ids: list[str]) -> tuple[list[dict[str, object]], str, bool]:
        # 模拟读取多文档输入阶段失败；此时普通 exam 已经被创建，但还没生成题目。
        raise RuntimeError(f"simulated phase failure for {document_ids[0]}")

    monkeypatch.setattr(phase_exam_service, "build_phase_exam_input", fail_before_llm)

    with pytest.raises(RuntimeError, match="simulated phase failure"):
        phase_exam_service.generate_phase_exam(
            document_ids=[document_id],
            name="Broken Phase",
            difficulty="medium",
            phase_exam_id=phase_exam["id"],
        )

    updated_phase_exam = phase_exams_module.get_phase_exam_by_id(phase_exam["id"])
    assert updated_phase_exam is not None
    assert updated_phase_exam["status"] == "failed"
    assert updated_phase_exam["exam_id"] is not None

    linked_exam = exams_module.get_exam_by_id(updated_phase_exam["exam_id"])
    assert linked_exam is not None
    assert linked_exam["status"] == "failed"
    assert "simulated phase failure" in linked_exam["error_message"]


def test_delete_document_cascades_exams_wrong_questions_and_phase_exams(client: TestClient) -> None:
    """删除文档会清理关联试卷、错题和阶段考试记录。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]
    exams_module = importlib.import_module("repositories.exams")
    phase_exams_module = importlib.import_module("repositories.phase_exams")
    wrong_questions_module = importlib.import_module("repositories.wrong_questions")

    exam = exams_module.create_exam_record(
        document_id=document_id,
        title="Document exam",
        description=None,
        total_score=5,
        exam_status="ready",
    )
    question = exams_module.create_exam_question(
        exam_id=exam["id"],
        question_number=1,
        section="A",
        question_type="choice",
        score=5,
        content="Pick A",
        options=["A", "B", "C", "D"],
        answer="A",
        explanation="A is correct",
        source_page=1,
        expected_type="text",
    )
    attempt = exams_module.create_exam_attempt(
        exam_id=exam["id"],
        answers={question["id"]: "B"},
        score=0,
    )
    wrong = wrong_questions_module.create_wrong_question(
        question_id=question["id"],
        exam_id=exam["id"],
        attempt_id=attempt["id"],
        user_answer="B",
    )
    phase_exam = phase_exams_module.create_phase_exam_record(
        name="Phase",
        document_ids=[document_id],
        difficulty="medium",
        phase_exam_status="ready",
    )
    phase_exams_module.update_phase_exam_exam_id(phase_exam["id"], exam["id"])

    delete_response = client.delete(f"/api/documents/{document_id}")
    assert delete_response.status_code == 204
    assert exams_module.get_exam_by_id(exam["id"]) is None
    assert exams_module.get_exam_questions(exam["id"]) == []
    assert exams_module.list_exam_attempts(exam["id"]) == []
    assert wrong_questions_module.get_wrong_question_by_id(wrong["id"]) is None
    assert phase_exams_module.get_phase_exam_by_id(phase_exam["id"]) is None


def test_delete_phase_exam_removes_linked_exam_and_related_records(client: TestClient) -> None:
    """删除阶段考试会同步清理关联试卷、题目、答题记录和错题记录。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]

    exams_module = importlib.import_module("repositories.exams")
    phase_exams_module = importlib.import_module("repositories.phase_exams")
    wrong_questions_module = importlib.import_module("repositories.wrong_questions")

    # 阶段考试生成成功后会关联一份普通 exam，这里直接构造该状态，避免测试依赖真实 LLM。
    exam = exams_module.create_exam_record(
        document_id=document_id,
        title="Linked phase exam",
        description=None,
        total_score=5,
        exam_status="ready",
    )
    question = exams_module.create_exam_question(
        exam_id=exam["id"],
        question_number=1,
        section="A",
        question_type="choice",
        score=5,
        content="Pick A",
        options=["A", "B", "C", "D"],
        answer="A",
        explanation="A is correct",
        source_page=1,
        expected_type="text",
    )
    attempt = exams_module.create_exam_attempt(
        exam_id=exam["id"],
        answers={question["id"]: "B"},
        score=0,
    )
    wrong = wrong_questions_module.create_wrong_question(
        question_id=question["id"],
        exam_id=exam["id"],
        attempt_id=attempt["id"],
        user_answer="B",
    )
    phase_exam = phase_exams_module.create_phase_exam_record(
        name="Phase",
        document_ids=[document_id],
        difficulty="medium",
        phase_exam_status="ready",
    )
    phase_exams_module.update_phase_exam_exam_id(phase_exam["id"], exam["id"])

    delete_response = client.delete(f"/api/phase-exams/{phase_exam['id']}")
    assert delete_response.status_code == 204
    assert phase_exams_module.get_phase_exam_by_id(phase_exam["id"]) is None
    assert exams_module.get_exam_by_id(exam["id"]) is None
    assert exams_module.get_exam_questions(exam["id"]) == []
    assert exams_module.list_exam_attempts(exam["id"]) == []
    assert wrong_questions_module.get_wrong_question_by_id(wrong["id"]) is None


def test_delete_exam_removes_attempts_questions_and_wrong_entries(client: TestClient) -> None:
    """删除试卷会清理题目、答题记录和错题记录。"""

    upload_data = upload_pdf(client)
    document_id = upload_data["document_id"]

    exams_module = importlib.import_module("repositories.exams")
    wrong_questions_module = importlib.import_module("repositories.wrong_questions")

    exam = exams_module.create_exam_record(
        document_id=document_id,
        title="Delete me",
        description=None,
        total_score=5,
        exam_status="ready",
    )
    question = exams_module.create_exam_question(
        exam_id=exam["id"],
        question_number=1,
        section="A",
        question_type="choice",
        score=5,
        content="Pick A",
        options=["A", "B", "C", "D"],
        answer="A",
        explanation="A is correct",
        source_page=1,
        expected_type="text",
    )
    attempt = exams_module.create_exam_attempt(
        exam_id=exam["id"],
        answers={question["id"]: "B"},
        score=0,
    )
    wrong = wrong_questions_module.create_wrong_question(
        question_id=question["id"],
        exam_id=exam["id"],
        attempt_id=attempt["id"],
        user_answer="B",
    )

    delete_response = client.delete(f"/api/exams/{exam['id']}")
    assert delete_response.status_code == 204
    assert exams_module.get_exam_by_id(exam["id"]) is None
    assert exams_module.get_exam_questions(exam["id"]) == []
    assert exams_module.list_exam_attempts(exam["id"]) == []
    assert wrong_questions_module.get_wrong_question_by_id(wrong["id"]) is None
