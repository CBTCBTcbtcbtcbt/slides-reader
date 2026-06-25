"""FastAPI 应用创建和路由挂载入口。"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from database import init_database
from routes import documents, exams, health, llm, pages, phase_exams, wrong_questions


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
FRONTEND_DIST_DIR = PROJECT_DIR / "frontend" / "dist"
FRONTEND_INDEX_PATH = FRONTEND_DIST_DIR / "index.html"
FRONTEND_ASSETS_DIR = FRONTEND_DIST_DIR / "assets"


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用对象。

    返回值：
        FastAPI：已经挂载路由和 CORS 中间件的应用实例。
    """

    # FastAPI 应用对象是整个后端服务的核心入口，所有 API 都挂载在它上面。
    application = FastAPI(
        title="Slides Reader API",
        description="AI slides 阅读与授课工具的后端 API。",
        version="0.1.0",
    )

    # CORS 是浏览器的跨域访问控制机制；这里允许本地 Vite 前端访问后端。
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 路由按业务边界拆分，但对外路径保持完全不变。
    application.include_router(health.router)
    application.include_router(documents.router)
    application.include_router(pages.router)
    application.include_router(llm.router)
    application.include_router(exams.router)
    application.include_router(wrong_questions.router)
    application.include_router(phase_exams.router)

    if FRONTEND_ASSETS_DIR.exists():
        application.mount(
            "/assets",
            StaticFiles(directory=FRONTEND_ASSETS_DIR),
            name="frontend-assets",
        )

    @application.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str) -> FileResponse:
        """返回前端单页应用入口。

        API 路由已经在上面注册；未命中的非 API 路径交给 React Router。
        这样生产/展示时只需要启动 FastAPI 一个端口。
        """

        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")

        if not FRONTEND_INDEX_PATH.exists():
            raise RuntimeError(
                "frontend/dist/index.html 不存在。请先在 frontend 目录运行 npm run build。"
            )

        return FileResponse(FRONTEND_INDEX_PATH)

    @application.on_event("startup")
    def startup() -> None:
        """应用启动时初始化数据库。"""

        init_database()

    return application


# app 是 uvicorn main:app 或 uvicorn app:app 都可以直接加载的应用对象。
app = create_app()
