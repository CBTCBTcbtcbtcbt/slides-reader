"""文档、页面文件和讲稿生成控制路由。"""

from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse

import generation_service
from config import CONVERSION_TEMP_DIR, DOCUMENT_STORAGE_DIR
from database import init_database
from pdf_service import (
    convert_slides_to_pdf,
    ensure_document_file_is_safe,
    ensure_page_image_file_is_safe,
    get_upload_file_extension,
    is_supported_slides_upload,
    parse_pdf_pages,
    resolve_document_file_path,
    resolve_page_image_path,
)
from repositories.documents import (
    count_document_pages,
    create_document_record,
    delete_document_records,
    document_exists,
    get_document_file_row,
    get_document_for_status,
    get_document_ready_for_lecture_notes,
    get_document_with_page_count,
    list_documents_with_page_count,
    rename_document_record,
    reset_document_lecture_notes_status,
    set_lecture_notes_paused,
    update_course_summary_status,
)
from repositories.pages import (
    get_document_status_page_rows,
    get_page_for_lecture_notes,
    get_page_for_lecture_notes_by_id,
    get_page_image_row,
    list_document_pages_with_blocks_and_chat,
    list_page_image_paths_for_document,
    update_page_lecture_notes_status,
)
from schemas import RenameDocumentRequest


router = APIRouter()


@router.get("/api/documents")
def list_documents() -> list[dict[str, str | int | bool | None]]:
    """返回已经上传过的文档列表。"""

    init_database()
    return list_documents_with_page_count()


@router.get("/api/documents/{document_id}/file")
def read_document_file(document_id: str) -> FileResponse:
    """返回某个文档对应的系统实际使用 PDF 文件。"""

    init_database()
    document = get_document_file_row(document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的文档。",
        )

    document_file_path = resolve_document_file_path(document["file_path"])
    ensure_document_file_is_safe(document_file_path)

    if not document_file_path.exists() or not document_file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF 文件不存在，可能已经被手动删除。",
        )

    response = FileResponse(
        path=document_file_path,
        media_type="application/pdf",
        filename=document_file_path.name,
    )
    response.headers["content-disposition"] = f'inline; filename="{document_file_path.name}"'
    return response


@router.get("/api/documents/{document_id}/status")
def read_document_status(document_id: str) -> dict[str, Any]:
    """返回指定文档的处理进度和页级错误状态。"""

    init_database()
    document = get_document_for_status(document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的文档。",
        )

    page_rows = get_document_status_page_rows(document_id)
    pages = [
        {
            "page_id": row["id"],
            "page_number": row["page_number"],
            "status": row["status"],
            "error_message": row["error_message"],
            "lecture_notes_status": row["lecture_notes_status"],
            "lecture_notes_error": row["lecture_notes_error"],
        }
        for row in page_rows
    ]
    total_pages = len(pages)
    lecture_notes_ready_count = sum(
        1 for page in pages if page["lecture_notes_status"] == "ready"
    )
    lecture_notes_failed_count = sum(
        1 for page in pages if page["lecture_notes_status"] == "failed"
    )
    lecture_notes_processing_count = sum(
        1 for page in pages if page["lecture_notes_status"] == "processing"
    )
    lecture_notes_pending_count = sum(
        1 for page in pages if page["lecture_notes_status"] == "pending"
    )

    lecture_notes_paused = bool(document["lecture_notes_paused"])
    should_poll = (
        document["status"] == "processing"
        or document["course_summary_status"] == "processing"
        or (not lecture_notes_paused and lecture_notes_processing_count > 0)
        or (
            not lecture_notes_paused
            and document["course_summary_status"] == "ready"
            and lecture_notes_pending_count > 0
        )
    )

    return {
        "document_id": document["id"],
        "title": document["title"],
        "status": document["status"],
        "error_message": document["error_message"],
        "course_summary_status": document["course_summary_status"],
        "course_summary_error": document["course_summary_error"],
        "course_summary_ready": document["course_summary_status"] == "ready"
        and bool(document["course_summary"]),
        "total_pages": total_pages,
        "lecture_notes_ready_count": lecture_notes_ready_count,
        "lecture_notes_failed_count": lecture_notes_failed_count,
        "lecture_notes_processing_count": lecture_notes_processing_count,
        "lecture_notes_pending_count": lecture_notes_pending_count,
        "lecture_notes_paused": lecture_notes_paused,
        "should_poll": should_poll,
        "pages": pages,
    }


@router.get("/api/documents/{document_id}/pages")
def list_document_pages(document_id: str) -> list[dict[str, Any]]:
    """返回某个文档的所有页面解析记录。"""

    init_database()
    return list_document_pages_with_blocks_and_chat(document_id)


@router.get("/api/documents/{document_id}/pages/{page_number}/image")
def read_page_image(document_id: str, page_number: int) -> FileResponse:
    """返回指定页面的 PNG 截图文件。"""

    init_database()
    if page_number < 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的页面截图。",
        )

    if not document_exists(document_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的文档。",
        )

    page = get_page_image_row(document_id=document_id, page_number=page_number)
    if page is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的页面。",
        )

    if not page["image_path"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="当前页面没有截图。",
        )

    image_path = resolve_page_image_path(page["image_path"])
    ensure_page_image_file_is_safe(image_path)

    if not image_path.exists() or not image_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="页面截图文件不存在，可能已经被手动删除。",
        )

    return FileResponse(path=image_path, media_type="image/png", filename=image_path.name)


@router.post("/api/documents/{document_id}/course-summary/regenerate")
def regenerate_course_summary(
    document_id: str,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """重新生成指定文档的课程简介。"""

    init_database()
    if not document_exists(document_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的文档。",
        )

    if count_document_pages(document_id) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前文档还没有页面记录，无法生成课程简介。",
        )

    update_course_summary_status(
        document_id=document_id,
        summary_status="processing",
        course_summary=None,
        error_message=None,
    )
    background_tasks.add_task(generation_service.generate_course_summary, document_id)

    return {"status": "processing", "document_id": document_id}


@router.post("/api/documents/{document_id}/lecture-notes/regenerate")
def regenerate_document_lecture_notes(
    document_id: str,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """重新生成指定文档的所有页面讲稿。"""

    init_database()
    document = get_document_ready_for_lecture_notes(document_id)
    reset_document_lecture_notes_status(document_id)
    background_tasks.add_task(generation_service.generate_document_lecture_notes, document["id"])

    return {"status": "processing", "document_id": document_id}


@router.post("/api/documents/{document_id}/lecture-notes/pause")
def pause_document_lecture_notes(document_id: str) -> dict[str, str | bool]:
    """暂停指定文档后续页面的讲稿生成。"""

    init_database()
    if not document_exists(document_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的文档。",
        )

    set_lecture_notes_paused(document_id=document_id, paused=True)
    return {
        "status": "paused",
        "document_id": document_id,
        "lecture_notes_paused": True,
    }


@router.post("/api/documents/{document_id}/lecture-notes/resume")
def resume_document_lecture_notes(
    document_id: str,
    background_tasks: BackgroundTasks,
) -> dict[str, str | bool]:
    """继续指定文档未完成页面的讲稿生成。"""

    init_database()
    document = get_document_ready_for_lecture_notes(document_id)
    set_lecture_notes_paused(document_id=document_id, paused=False)
    background_tasks.add_task(generation_service.generate_document_lecture_notes, document["id"])

    return {
        "status": "processing",
        "document_id": document_id,
        "lecture_notes_paused": False,
    }


@router.post("/api/documents/{document_id}/pages/{page_number}/lecture-notes/regenerate")
def regenerate_page_lecture_notes(
    document_id: str,
    page_number: int,
    background_tasks: BackgroundTasks,
) -> dict[str, str | int]:
    """重新生成指定页面的讲稿。"""

    init_database()
    document = get_document_ready_for_lecture_notes(document_id)
    page = get_page_for_lecture_notes(document_id=document_id, page_number=page_number)

    update_page_lecture_notes_status(
        document_id=document_id,
        page_number=page_number,
        lecture_notes_status="processing",
        lecture_notes=None,
        error_message=None,
    )
    background_tasks.add_task(generation_service.generate_single_page_lecture_notes, document, page)

    return {
        "status": "processing",
        "document_id": document_id,
        "page_number": page_number,
    }


@router.post("/api/pages/{page_id}/regenerate")
def regenerate_page_lecture_notes_by_id(
    page_id: str,
    background_tasks: BackgroundTasks,
) -> dict[str, str | int]:
    """通过 page_id 重新生成指定页面的讲稿。"""

    init_database()
    page = get_page_for_lecture_notes_by_id(page_id)
    document = get_document_ready_for_lecture_notes(page["document_id"])

    update_page_lecture_notes_status(
        document_id=page["document_id"],
        page_number=page["page_number"],
        lecture_notes_status="processing",
        lecture_notes=None,
        error_message=None,
    )
    background_tasks.add_task(generation_service.generate_single_page_lecture_notes, document, page)

    return {
        "status": "processing",
        "document_id": page["document_id"],
        "page_id": page["id"],
        "page_number": page["page_number"],
    }


@router.patch("/api/documents/{document_id}")
def rename_document(
    document_id: str,
    request: RenameDocumentRequest,
) -> dict[str, str | int | bool | None]:
    """重命名文档显示标题。"""

    next_title = request.title.strip()
    if not next_title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文档标题不能为空。",
        )

    init_database()
    return rename_document_record(document_id=document_id, next_title=next_title)


@router.delete("/api/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str) -> Response:
    """删除文档记录、页面记录、本地 PDF 文件和页面截图文件。"""

    init_database()
    document = get_document_file_row(document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的文档。",
        )

    document_file_path = resolve_document_file_path(document["file_path"])
    ensure_document_file_is_safe(document_file_path)

    page_image_paths = [
        resolve_page_image_path(image_path)
        for image_path in list_page_image_paths_for_document(document_id)
    ]
    for page_image_path in page_image_paths:
        ensure_page_image_file_is_safe(page_image_path)

    delete_document_records(document_id)

    if document_file_path.exists():
        try:
            document_file_path.unlink()
        except OSError as error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"数据库记录已删除，但本地 PDF 文件删除失败：{error}",
            ) from error

    for page_image_path in page_image_paths:
        if page_image_path.exists():
            try:
                page_image_path.unlink()
            except OSError as error:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"数据库记录已删除，但页面截图删除失败：{error}",
                ) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> dict[str, str | int | bool | None]:
    """接收用户上传的 PDF/PPT/PPTX slides，并保存为系统实际使用的 PDF。"""

    if not is_supported_slides_upload(file):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只支持上传 PDF、PPT 或 PPTX 文件，请选择 .pdf、.ppt 或 .pptx 格式的 slides。",
        )

    document_id = str(uuid4())
    upload_extension = get_upload_file_extension(file)

    DOCUMENT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    saved_filename = f"{document_id}.pdf"
    saved_path = DOCUMENT_STORAGE_DIR / saved_filename

    file_bytes = await file.read()

    if upload_extension == ".pdf":
        saved_path.write_bytes(file_bytes)
    else:
        CONVERSION_TEMP_DIR.mkdir(parents=True, exist_ok=True)
        temporary_source_path = CONVERSION_TEMP_DIR / f"{document_id}{upload_extension}"

        try:
            temporary_source_path.write_bytes(file_bytes)
            convert_slides_to_pdf(
                source_path=temporary_source_path,
                output_pdf_path=saved_path,
            )
        finally:
            if temporary_source_path.exists():
                temporary_source_path.unlink()
            temporary_pdf_path = temporary_source_path.with_suffix(".pdf")
            if temporary_pdf_path.exists():
                temporary_pdf_path.unlink()

    init_database()
    create_document_record(
        document_id=document_id,
        title=file.filename or "unknown.pdf",
        file_path=str(saved_path),
        document_status="processing",
    )

    parse_pdf_pages(document_id=document_id, saved_path=saved_path)

    document_after_parse = get_document_with_page_count(document_id)
    if document_after_parse is not None and document_after_parse["status"] == "ready":
        update_course_summary_status(
            document_id=document_id,
            summary_status="processing",
            course_summary=None,
            error_message=None,
        )
        background_tasks.add_task(generation_service.generate_course_summary, document_id)
    elif document_after_parse is not None and document_after_parse["status"] == "failed":
        update_course_summary_status(
            document_id=document_id,
            summary_status="failed",
            course_summary=None,
            error_message="PDF 解析失败，无法生成课程简介。",
        )

    document = get_document_with_page_count(document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PDF 已保存，但无法读取文档记录。",
        )

    return {
        **document,
        "filename": file.filename or "unknown.pdf",
        "saved_filename": saved_filename,
    }
