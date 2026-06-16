"""健康检查路由。"""

from fastapi import APIRouter


router = APIRouter()


@router.get("/api/health")
def read_health() -> dict[str, str]:
    """返回后端健康状态。"""

    return {"status": "ok", "service": "slides-reader-api"}
