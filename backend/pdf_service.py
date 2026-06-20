"""PDF/PPT 文件处理、截图渲染和路径安全检查。"""

import subprocess
from os import getenv
from pathlib import Path

import pymupdf
from fastapi import HTTPException, UploadFile, status

from config import (
    BASE_DIR,
    DOCUMENT_STORAGE_DIR,
    LIBREOFFICE_PROFILE_DIR,
    PAGE_IMAGE_STORAGE_DIR,
)
from repositories.documents import update_document_status
from repositories.pages import create_page_record


def configure_mupdf_console_output() -> None:
    """关闭 MuPDF 直接写入控制台的 warning/error 噪声。"""

    # LibreOffice 转换出来的 PPT/PPTX PDF 有时带有不完整的结构树。
    # MuPDF 会把这类可恢复问题直接打印到 stderr，例如 No common ancestor in structure tree。
    # 这些信息不一定代表解析失败，真实失败仍然会通过 Python 异常进入下面的错误处理。
    mupdf_tools = getattr(pymupdf, "TOOLS", None)
    if mupdf_tools is None:
        return

    # 不同 PyMuPDF 版本可能缺少其中某个开关，所以逐个判断后再调用。
    for toggle_name in ("mupdf_display_errors", "mupdf_display_warnings"):
        toggle = getattr(mupdf_tools, toggle_name, None)
        if toggle is not None:
            toggle(False)


configure_mupdf_console_output()


def get_upload_file_extension(file: UploadFile) -> str:
    """读取上传文件的小写后缀名。"""

    # filename 可能为空，所以用空字符串兜底。
    filename = file.filename or ""
    return Path(filename).suffix.lower()


def is_supported_slides_upload(file: UploadFile) -> bool:
    """判断上传文件是否是当前支持的 slides 格式。"""

    # 浏览器对 PPT/PPTX 的 content-type 声明不稳定，所以以后缀作为主校验。
    return get_upload_file_extension(file) in {".pdf", ".ppt", ".pptx"}


def resolve_document_file_path(file_path: str) -> Path:
    """把数据库中的文件路径解析为本地 PDF 绝对路径。"""

    return Path(file_path).resolve()


def ensure_document_file_is_safe(file_path: Path) -> None:
    """确认待读取或待删除的 PDF 文件位于 DOCUMENT_STORAGE_DIR 内。"""

    storage_root = DOCUMENT_STORAGE_DIR.resolve()
    try:
        file_path.relative_to(storage_root)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="文档文件路径不在允许访问的 storage/documents 目录内，已拒绝访问文件。",
        ) from error


def resolve_page_image_path(image_path: str) -> Path:
    """把数据库中的截图路径解析为本地 PNG 绝对路径。"""

    return Path(image_path).resolve()


def ensure_page_image_file_is_safe(image_path: Path) -> None:
    """确认页面截图文件位于 PAGE_IMAGE_STORAGE_DIR 内。"""

    storage_root = PAGE_IMAGE_STORAGE_DIR.resolve()
    try:
        image_path.relative_to(storage_root)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="页面截图路径不在允许访问的 storage/pages 目录内，已拒绝操作。",
        ) from error


def build_page_image_path(document_id: str, page_number: int) -> Path:
    """生成某一页截图应保存到的本地路径。"""

    return PAGE_IMAGE_STORAGE_DIR / f"{document_id}-page-{page_number}.png"


def render_page_image(page: pymupdf.Page, document_id: str, page_number: int) -> Path:
    """把 PDF 单页渲染成 PNG 图片并保存到本地。"""

    # 截图目录可能还不存在，渲染前先创建。
    PAGE_IMAGE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    # Matrix(2, 2) 在清晰度和体积之间取中等值。
    render_matrix = pymupdf.Matrix(2, 2)
    pixmap = page.get_pixmap(matrix=render_matrix)

    image_path = build_page_image_path(document_id=document_id, page_number=page_number)
    pixmap.save(image_path)
    return image_path


def resolve_soffice_path() -> Path | None:
    """查找 LibreOffice 的 soffice.exe 路径。"""

    candidate_paths = [
        getenv("SLIDES_READER_SOFFICE_PATH", ""),
        str(
            BASE_DIR.parent
            / "tools"
            / "libreoffice"
            / "LibreOfficePortable"
            / "App"
            / "libreoffice"
            / "program"
            / "soffice.exe"
        ),
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]

    for candidate_path in candidate_paths:
        if not candidate_path:
            continue

        resolved_path = Path(candidate_path).resolve()
        if resolved_path.exists() and resolved_path.is_file():
            return resolved_path

    try:
        command_result = subprocess.run(
            ["where", "soffice.exe"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    for output_line in command_result.stdout.splitlines():
        resolved_path = Path(output_line.strip()).resolve()
        if resolved_path.exists() and resolved_path.is_file():
            return resolved_path

    return None


def convert_slides_to_pdf(source_path: Path, output_pdf_path: Path) -> None:
    """使用 LibreOffice 把 PPT/PPTX 转换成 PDF。"""

    soffice_path = resolve_soffice_path()
    if soffice_path is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="没有找到 LibreOffice 的 soffice.exe，无法转换 PPT/PPTX。请先运行项目根目录下的 setup-env.ps1，或设置 SLIDES_READER_SOFFICE_PATH。",
        )

    output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    LIBREOFFICE_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    profile_uri = LIBREOFFICE_PROFILE_DIR.resolve().as_uri()
    conversion_output_path = source_path.with_suffix(".pdf")
    if conversion_output_path.exists():
        conversion_output_path.unlink()

    command = [
        str(soffice_path),
        f"-env:UserInstallation={profile_uri}",
        "--headless",
        "--nologo",
        "--nodefault",
        "--nofirststartwizard",
        "--nolockcheck",
        "--convert-to",
        "pdf",
        "--outdir",
        str(source_path.parent),
        str(source_path),
    ]

    try:
        process = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LibreOffice 转换 PPT/PPTX 超时，请确认文件没有损坏或过大。",
        ) from error
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"无法启动 LibreOffice 转换进程：{error}",
        ) from error

    # Windows 上 soffice 退出码不总是可靠，所以优先检查 PDF 产物是否存在。
    if not conversion_output_path.exists() or not conversion_output_path.is_file():
        error_output = (process.stderr or process.stdout or "").strip()
        if process.returncode not in (0, None):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"LibreOffice 转换失败，退出码 {process.returncode}：{error_output or '没有返回错误详情'}",
            )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LibreOffice 转换命令已执行，但没有生成 PDF：{error_output or '没有返回错误详情'}",
        )

    if output_pdf_path.exists():
        output_pdf_path.unlink()

    conversion_output_path.replace(output_pdf_path)


def parse_pdf_pages(document_id: str, saved_path: Path) -> None:
    """解析 PDF 页数、每页文字和每页截图，并写入 pages 表。"""

    try:
        with pymupdf.open(saved_path) as pdf_document:
            has_page_error = False
            page_error_messages: list[str] = []

            for page_number, page in enumerate(pdf_document, start=1):
                try:
                    page_text = page.get_text("text", sort=True)
                    image_path = render_page_image(
                        page=page,
                        document_id=document_id,
                        page_number=page_number,
                    )

                    create_page_record(
                        document_id=document_id,
                        page_number=page_number,
                        text=page_text,
                        image_path=image_path,
                        page_status="ready",
                    )
                except Exception as error:
                    # 单页失败时仍然创建页面记录，避免页码和 PDF 实际页数不一致。
                    has_page_error = True
                    error_message = f"第 {page_number} 页解析或截图生成失败：{error}"
                    page_error_messages.append(error_message)
                    create_page_record(
                        document_id=document_id,
                        page_number=page_number,
                        text="",
                        image_path=None,
                        page_status="failed",
                        error_message=error_message,
                    )

            if has_page_error:
                update_document_status(
                    document_id=document_id,
                    document_status="failed",
                    error_message="；".join(page_error_messages),
                )
                return

            update_document_status(document_id=document_id, document_status="ready")
    except Exception as error:
        # 整份 PDF 无法打开或读取时，只标记文档失败，不让服务崩溃。
        update_document_status(
            document_id=document_id,
            document_status="failed",
            error_message=f"PDF 无法打开或解析：{error}",
        )
