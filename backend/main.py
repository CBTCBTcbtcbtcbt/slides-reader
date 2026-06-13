"""AI slides reader 后端入口文件。

这个文件实现当前阶段需要的最小后端能力：
1. 创建一个 FastAPI 应用。
2. 开放开发环境前端可以访问的 CORS 配置。
3. 提供 `/api/health` 健康检查接口。
4. 提供 PDF 文件上传接口，并把合法 PDF 保存到本地。
5. 使用 SQLite 持久保存上传文档记录。
6. 使用 PyMuPDF 解析 PDF 页数和每页文字。
"""

import sqlite3
from datetime import UTC, datetime
from os import getenv
from pathlib import Path
from uuid import uuid4

import pymupdf
from fastapi import FastAPI, File, HTTPException, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


# BASE_DIR 表示 backend 目录的绝对路径。
# 使用绝对路径可以避免从不同工作目录启动后端时保存位置发生变化。
BASE_DIR = Path(__file__).resolve().parent

# DEFAULT_STORAGE_DIR 表示默认运行数据目录。
# 如果没有额外配置，上传文件和 SQLite 数据库都会保存到项目根目录下的 storage。
DEFAULT_STORAGE_DIR = BASE_DIR.parent / "storage"

# STORAGE_DIR 支持通过环境变量覆盖。
# 这能让测试使用临时目录，不影响开发时正在使用的 storage 数据。
STORAGE_DIR = Path(getenv("SLIDES_READER_STORAGE_DIR", str(DEFAULT_STORAGE_DIR))).resolve()

# DOCUMENT_STORAGE_DIR 是 PDF 上传后的本地保存目录。
# 当前任务会在保存原始 PDF 后同步解析页数和文字。
DOCUMENT_STORAGE_DIR = STORAGE_DIR / "documents"

# DATABASE_PATH 是 SQLite 数据库文件路径。
# SQLite 是本地文件数据库，适合当前阶段的单用户本地应用。
DATABASE_PATH = STORAGE_DIR / "app.db"


# 创建 FastAPI 应用对象。
# FastAPI 应用对象可以理解为整个后端服务的核心入口，所有 API 都挂载在它上面。
app = FastAPI(
    title="Slides Reader API",
    description="AI slides 阅读与授课工具的后端 API。",
    version="0.1.0",
)


class RenameDocumentRequest(BaseModel):
    """重命名文档的请求体。

    属性：
        title：用户希望显示在文档列表里的新标题。
    """

    title: str


def init_database() -> None:
    """初始化 SQLite 数据库、Document 表和 Page 表。

    返回值：
        None：这个函数只负责创建目录、表和兼容字段，不返回业务数据。
    """

    # 数据库文件位于 storage 目录下，所以要先确保 storage 目录存在。
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 使用 with 语句打开连接，可以在代码块结束时自动关闭数据库连接。
    with sqlite3.connect(DATABASE_PATH) as connection:
        # 创建 documents 表；IF NOT EXISTS 表示表已存在时不重复创建。
        # documents 表保存上传 PDF 的基本信息，后续任务会继续围绕 document_id 扩展页面数据。
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                file_path TEXT NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        # 兼容任务 03 已经创建过的 documents 表。
        # SQLite 不支持直接用 IF NOT EXISTS 增加列，所以先读取已有列再决定是否 ALTER TABLE。
        document_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(documents)").fetchall()
        }
        if "error_message" not in document_columns:
            connection.execute("ALTER TABLE documents ADD COLUMN error_message TEXT")

        # pages 表保存 PDF 每一页的解析结果。
        # document_id 和 page_number 做唯一约束，避免同一文档同一页被重复插入。
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pages (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                text TEXT NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(document_id, page_number),
                FOREIGN KEY(document_id) REFERENCES documents(id)
            )
            """
        )


def get_database_connection() -> sqlite3.Connection:
    """创建一个 SQLite 数据库连接。

    返回值：
        sqlite3.Connection：已经设置好 row_factory 的数据库连接对象。
    """

    # row_factory 设置为 sqlite3.Row 后，可以像字典一样通过字段名读取查询结果。
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def row_to_document(row: sqlite3.Row) -> dict[str, str | int | None]:
    """把 SQLite 查询结果转换成前端可直接使用的字典。

    参数：
        row：SQLite 查询返回的一行 Document 数据。

    返回值：
        dict[str, str | int | None]：包含文档 ID、标题、文件路径、状态、页数、错误信息和创建时间。
    """

    # 明确列出字段，可以避免把数据库内部字段或未来新增字段意外暴露给前端。
    return {
        "document_id": row["id"],
        "title": row["title"],
        "file_path": row["file_path"],
        "status": row["status"],
        "page_count": row["page_count"],
        "error_message": row["error_message"],
        "created_at": row["created_at"],
    }


def row_to_page(row: sqlite3.Row) -> dict[str, str | int | None]:
    """把 SQLite 查询结果转换成页面字典。

    参数：
        row：SQLite 查询返回的一行 Page 数据。

    返回值：
        dict[str, str | int | None]：包含页面 ID、页码、文字、状态、错误信息和创建时间。
    """

    # 页面文字可能很长，但当前任务需要返回它，方便前端或后续任务验证解析结果。
    return {
        "page_id": row["id"],
        "document_id": row["document_id"],
        "page_number": row["page_number"],
        "text": row["text"],
        "status": row["status"],
        "error_message": row["error_message"],
        "created_at": row["created_at"],
    }


def get_document_with_page_count(document_id: str) -> dict[str, str | int | None] | None:
    """查询单个文档，并附带页面数量。

    参数：
        document_id：要查询的文档 ID。

    返回值：
        dict[str, str | int | None] | None：找到文档时返回文档字典，找不到时返回 None。
    """

    # 这个函数复用文档列表的 JOIN 逻辑，保证 PATCH 返回结构和 GET /api/documents 一致。
    with get_database_connection() as connection:
        row = connection.execute(
            """
            SELECT
                documents.id,
                documents.title,
                documents.file_path,
                documents.status,
                documents.error_message,
                documents.created_at,
                COUNT(pages.id) AS page_count
            FROM documents
            LEFT JOIN pages ON pages.document_id = documents.id
            WHERE documents.id = ?
            GROUP BY documents.id
            """,
            (document_id,),
        ).fetchone()

    if row is None:
        return None

    return row_to_document(row)


def resolve_document_file_path(file_path: str) -> Path:
    """把数据库中的文件路径解析为安全的本地 PDF 路径。

    参数：
        file_path：documents.file_path 中保存的路径字符串。

    返回值：
        Path：解析后的绝对路径。
    """

    # resolve 会把相对路径、.. 等路径片段解析成绝对路径，方便后续做目录边界检查。
    return Path(file_path).resolve()


def ensure_document_file_is_safe(file_path: Path) -> None:
    """确认待删除文件位于 DOCUMENT_STORAGE_DIR 内。

    参数：
        file_path：准备删除的 PDF 文件绝对路径。

    返回值：
        None：路径安全时不返回数据，路径不安全时直接抛出 HTTPException。
    """

    # 删除文件前必须确认路径边界，避免数据库中的异常 file_path 导致误删项目外文件。
    storage_root = DOCUMENT_STORAGE_DIR.resolve()

    try:
        file_path.relative_to(storage_root)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="文档文件路径不在允许删除的 storage/documents 目录内，已拒绝删除文件。",
        ) from error


def update_document_status(
    document_id: str,
    document_status: str,
    error_message: str | None = None,
) -> None:
    """更新文档处理状态。

    参数：
        document_id：需要更新的文档 ID。
        document_status：新的文档状态，例如 processing、ready 或 failed。
        error_message：失败时保存的错误信息，成功时通常为 None。

    返回值：
        None：这个函数只负责写数据库。
    """

    # 状态更新集中在一个函数里，避免上传流程和解析流程重复写 SQL。
    with get_database_connection() as connection:
        connection.execute(
            """
            UPDATE documents
            SET status = ?, error_message = ?
            WHERE id = ?
            """,
            (document_status, error_message, document_id),
        )
        connection.commit()


def create_page_record(
    document_id: str,
    page_number: int,
    text: str,
    page_status: str,
    error_message: str | None = None,
) -> None:
    """创建或替换单页解析记录。

    参数：
        document_id：页面所属文档 ID。
        page_number：从 1 开始的页码。
        text：当前页提取出的文字；空白页使用空字符串。
        page_status：页面解析状态，例如 ready 或 failed。
        error_message：单页解析失败时保存的错误信息。

    返回值：
        None：这个函数只负责写数据库。
    """

    # 每页记录有自己的 ID，方便后续任务把讲稿、截图或问答关联到具体页面。
    page_id = str(uuid4())
    created_at = datetime.now(UTC).isoformat()

    with get_database_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO pages (
                id, document_id, page_number, text, status, error_message, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                page_id,
                document_id,
                page_number,
                text,
                page_status,
                error_message,
                created_at,
            ),
        )
        connection.commit()


def parse_pdf_pages(document_id: str, saved_path: Path) -> None:
    """解析 PDF 页数和每页文字，并写入 pages 表。

    参数：
        document_id：当前 PDF 对应的文档 ID。
        saved_path：已经保存到本地的 PDF 文件路径。

    返回值：
        None：解析结果会直接写入 SQLite。
    """

    # 如果 PDF 文件损坏或不是合法 PDF，pymupdf.open 会抛出异常。
    try:
        with pymupdf.open(saved_path) as pdf_document:
            has_page_error = False
            page_error_messages: list[str] = []

            # enumerate 从 0 开始，所以通过 start=1 让 page_number 符合用户习惯。
            for page_number, page in enumerate(pdf_document, start=1):
                try:
                    # get_text("text", sort=True) 会按阅读顺序尽量提取页面文字。
                    # 空白页会得到空字符串，但仍然需要创建页面记录。
                    page_text = page.get_text("text", sort=True)
                    create_page_record(
                        document_id=document_id,
                        page_number=page_number,
                        text=page_text,
                        page_status="ready",
                    )
                except Exception as error:
                    # 单页失败时仍然写入记录，避免页面数量和 PDF 实际页码不一致。
                    has_page_error = True
                    error_message = f"第 {page_number} 页解析失败：{error}"
                    page_error_messages.append(error_message)
                    create_page_record(
                        document_id=document_id,
                        page_number=page_number,
                        text="",
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

            # 所有页面都创建成功后，把文档状态更新为 ready。
            update_document_status(document_id=document_id, document_status="ready")
    except Exception as error:
        # 整个 PDF 无法打开或无法读取时，记录失败状态，不让后端服务崩溃。
        update_document_status(
            document_id=document_id,
            document_status="failed",
            error_message=f"PDF 无法打开或解析：{error}",
        )


@app.on_event("startup")
def startup() -> None:
    """后端启动时初始化数据库。

    返回值：
        None：这个函数由 FastAPI 在应用启动时自动调用。
    """

    # 启动时建库建表，保证第一次运行项目时不需要手动准备数据库文件。
    init_database()


# 配置开发环境 CORS。
# CORS 是浏览器的跨域访问控制机制；前端开发服务器和后端端口不同，所以需要显式允许。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def read_health() -> dict[str, str]:
    """返回后端健康状态。

    返回值：
        dict[str, str]：包含后端当前状态的 JSON 数据。
    """

    # 这里返回固定状态，供前端确认后端服务已经正常启动。
    return {"status": "ok", "service": "slides-reader-api"}


@app.get("/api/documents")
def list_documents() -> list[dict[str, str | int | None]]:
    """返回已经上传过的文档列表。

    返回值：
        list[dict[str, str | int | None]]：按创建时间倒序排列的文档记录列表。
    """

    # 查询前先确保数据库已初始化，方便在测试或直接导入 app 时也能正常工作。
    init_database()

    # 每次请求单独打开数据库连接，请求结束后自动关闭，适合当前小型本地应用。
    with get_database_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                documents.id,
                documents.title,
                documents.file_path,
                documents.status,
                documents.error_message,
                documents.created_at,
                COUNT(pages.id) AS page_count
            FROM documents
            LEFT JOIN pages ON pages.document_id = documents.id
            GROUP BY documents.id
            ORDER BY documents.created_at DESC
            """
        ).fetchall()

    # 将数据库行转换为普通字典，方便 FastAPI 自动序列化为 JSON。
    return [row_to_document(row) for row in rows]


@app.get("/api/documents/{document_id}/pages")
def list_document_pages(document_id: str) -> list[dict[str, str | int | None]]:
    """返回某个文档的所有页面解析记录。

    参数：
        document_id：需要查询页面的文档 ID。

    返回值：
        list[dict[str, str | int | None]]：按页码升序排列的页面记录列表。
    """

    # 查询前先确保数据库已初始化，方便第一次请求也能正常返回空列表或结果。
    init_database()

    with get_database_connection() as connection:
        document = connection.execute(
            "SELECT id FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()

        # 如果文档不存在，返回 404，避免前端误以为只是没有页面。
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="没有找到对应的文档。",
            )

        rows = connection.execute(
            """
            SELECT id, document_id, page_number, text, status, error_message, created_at
            FROM pages
            WHERE document_id = ?
            ORDER BY page_number ASC
            """,
            (document_id,),
        ).fetchall()

    return [row_to_page(row) for row in rows]


@app.patch("/api/documents/{document_id}")
def rename_document(
    document_id: str,
    request: RenameDocumentRequest,
) -> dict[str, str | int | None]:
    """重命名文档显示标题。

    参数：
        document_id：需要重命名的文档 ID。
        request：包含新标题的请求体。

    返回值：
        dict[str, str | int | None]：更新后的文档记录。
    """

    # 去掉首尾空白，避免保存看起来为空的标题。
    next_title = request.title.strip()

    if not next_title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文档标题不能为空。",
        )

    init_database()

    with get_database_connection() as connection:
        result = connection.execute(
            """
            UPDATE documents
            SET title = ?
            WHERE id = ?
            """,
            (next_title, document_id),
        )
        connection.commit()

    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的文档。",
        )

    document = get_document_with_page_count(document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到对应的文档。",
        )

    return document


@app.delete("/api/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str) -> Response:
    """删除文档记录、页面记录和本地 PDF 文件。

    参数：
        document_id：需要删除的文档 ID。

    返回值：
        Response：删除成功时返回 204 空响应。
    """

    init_database()

    with get_database_connection() as connection:
        document = connection.execute(
            "SELECT id, file_path FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()

        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="没有找到对应的文档。",
            )

        # 删除数据库记录前先计算文件路径并完成安全检查。
        # 这样一旦路径异常，不会出现数据库已删但文件未处理的状态。
        document_file_path = resolve_document_file_path(document["file_path"])
        ensure_document_file_is_safe(document_file_path)

        # 先删子表 pages，再删主表 documents，避免留下孤立页面记录。
        connection.execute("DELETE FROM pages WHERE document_id = ?", (document_id,))
        connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        connection.commit()

    # 如果文件已经不存在，说明本地文件可能被手动删除过；此时数据库删除仍然算成功。
    if document_file_path.exists():
        try:
            document_file_path.unlink()
        except OSError as error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"数据库记录已删除，但本地 PDF 文件删除失败：{error}",
            ) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)


def is_pdf_upload(file: UploadFile) -> bool:
    """判断上传文件是否可以作为 PDF 接收。

    参数：
        file：FastAPI 接收到的上传文件对象，里面包含文件名、文件类型和文件内容读取方法。

    返回值：
        bool：文件名后缀和 content-type 都符合 PDF 时返回 True，否则返回 False。
    """

    # filename 可能为空，所以先使用空字符串兜底，避免调用 lower 方法时报错。
    filename = file.filename or ""

    # 后缀校验用于拦截明显不是 PDF 的文件名。
    has_pdf_extension = filename.lower().endswith(".pdf")

    # content-type 校验用于确认浏览器声明的文件类型是 PDF。
    # 不同浏览器通常会为 PDF 设置 application/pdf。
    has_pdf_content_type = file.content_type == "application/pdf"

    return has_pdf_extension and has_pdf_content_type


@app.post("/api/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(file: UploadFile = File(...)) -> dict[str, str | int | None]:
    """接收用户上传的 PDF slides，并保存到本地 storage 目录。

    参数：
        file：前端通过 multipart/form-data 上传的 PDF 文件。

    返回值：
        dict[str, str | int | None]：包含文档记录、页数、错误信息和保存后的文件名。
    """

    # 先校验文件类型，不合格时直接返回 400，避免把错误文件写入 storage。
    if not is_pdf_upload(file):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只支持上传 PDF 文件，请选择 .pdf 格式的 slides。",
        )

    # 为当前上传生成唯一 document_id，后续任务会用它关联页面、讲稿和问答记录。
    document_id = str(uuid4())

    # 创建保存目录；parents=True 表示父目录不存在时一起创建。
    DOCUMENT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    # 使用后端生成的 ID 作为文件名，避免用户原始文件名重复或包含不安全字符。
    saved_filename = f"{document_id}.pdf"
    saved_path = DOCUMENT_STORAGE_DIR / saved_filename

    # 读取上传内容并写入本地文件。
    # 当前任务只验证保存能力，所以不在这里解析 PDF。
    file_bytes = await file.read()
    saved_path.write_bytes(file_bytes)

    # created_at 使用 UTC 时间，方便后续不同地区或部署环境统一排序。
    created_at = datetime.now(UTC).isoformat()

    # 当前任务中，上传成功后会立即解析 PDF，所以初始状态设为 processing。
    document_status = "processing"

    # 确保数据库和 documents 表已经存在。
    init_database()

    # 上传文件保存成功后，把文档记录写入 SQLite。
    with get_database_connection() as connection:
        connection.execute(
            """
            INSERT INTO documents (id, title, file_path, status, error_message, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                file.filename or "unknown.pdf",
                str(saved_path),
                document_status,
                None,
                created_at,
            ),
        )
        connection.commit()

    # 同步解析 PDF 页数和文字。
    # 任务 04 暂不使用后台任务，后续 LLM 生成阶段再引入后台处理。
    parse_pdf_pages(document_id=document_id, saved_path=saved_path)

    # 解析后重新读取文档记录和页数，保证接口返回的是最终状态。
    with get_database_connection() as connection:
        document = connection.execute(
            """
            SELECT
                documents.id,
                documents.title,
                documents.file_path,
                documents.status,
                documents.error_message,
                documents.created_at,
                COUNT(pages.id) AS page_count
            FROM documents
            LEFT JOIN pages ON pages.document_id = documents.id
            WHERE documents.id = ?
            GROUP BY documents.id
            """,
            (document_id,),
        ).fetchone()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PDF 已保存，但无法读取文档记录。",
        )

    return {
        **row_to_document(document),
        "filename": file.filename or "unknown.pdf",
        "saved_filename": saved_filename,
    }
