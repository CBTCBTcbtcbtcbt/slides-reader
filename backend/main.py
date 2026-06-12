"""AI slides reader 后端入口文件。

这个文件实现当前阶段需要的最小后端能力：
1. 创建一个 FastAPI 应用。
2. 开放开发环境前端可以访问的 CORS 配置。
3. 提供 `/api/health` 健康检查接口。
4. 提供 PDF 文件上传接口，并把合法 PDF 保存到本地。
"""

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware


# BASE_DIR 表示 backend 目录的绝对路径。
# 使用绝对路径可以避免从不同工作目录启动后端时保存位置发生变化。
BASE_DIR = Path(__file__).resolve().parent

# PROJECT_DIR 表示项目根目录，也就是 backend 的上一级目录。
# storage 目录放在项目根目录下，方便后续数据库、PDF 和页面截图统一管理。
PROJECT_DIR = BASE_DIR.parent

# DOCUMENT_STORAGE_DIR 是 PDF 上传后的本地保存目录。
# 当前任务只负责保存原始 PDF，不负责写入数据库或解析 PDF。
DOCUMENT_STORAGE_DIR = PROJECT_DIR / "storage" / "documents"


# 创建 FastAPI 应用对象。
# FastAPI 应用对象可以理解为整个后端服务的核心入口，所有 API 都挂载在它上面。
app = FastAPI(
    title="Slides Reader API",
    description="AI slides 阅读与授课工具的后端 API。",
    version="0.1.0",
)


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
async def upload_document(file: UploadFile = File(...)) -> dict[str, str]:
    """接收用户上传的 PDF slides，并保存到本地 storage 目录。

    参数：
        file：前端通过 multipart/form-data 上传的 PDF 文件。

    返回值：
        dict[str, str]：包含 document_id、原始文件名和保存后的文件名。
    """

    # 先校验文件类型，不合格时直接返回 400，避免把错误文件写入 storage。
    if not is_pdf_upload(file):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只支持上传 PDF 文件，请选择 .pdf 格式的 slides。",
        )

    # 为当前上传生成唯一 document_id，后续任务会用它关联数据库记录。
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

    return {
        "document_id": document_id,
        "filename": file.filename or "unknown.pdf",
        "saved_filename": saved_filename,
    }
