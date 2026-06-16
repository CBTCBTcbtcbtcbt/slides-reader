"""FastAPI 应用创建和路由挂载入口。"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_database
from routes import documents, health, llm, pages


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

    @application.on_event("startup")
    def startup() -> None:
        """应用启动时初始化数据库。"""

        init_database()

    return application


# app 是 uvicorn main:app 或 uvicorn app:app 都可以直接加载的应用对象。
app = create_app()
