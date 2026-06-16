"""后端兼容入口。

当前启动脚本仍然使用 `uvicorn main:app`，因此这里保留同名 app 导出。
真实 FastAPI 应用创建、CORS 配置和路由挂载都在 app.py 中完成。
"""

from app import app


__all__ = ["app"]
