"""应用配置表的数据访问函数。"""

from datetime import UTC, datetime

from fastapi import HTTPException, status

from config import LLM_CONFIG_KEYS
from database import get_database_connection, init_database


def read_app_settings() -> dict[str, str]:
    """读取 app_settings 表中的全部配置。

    返回值：
        dict[str, str]：以配置 key 为键、配置 value 为值的字典。
    """

    # 每次读取前初始化数据库，保证测试或脚本直接调用时表已经存在。
    init_database()

    with get_database_connection() as connection:
        rows = connection.execute("SELECT key, value FROM app_settings").fetchall()

    # SQLite 行对象转换成普通字典，方便和默认配置合并。
    return {row["key"]: row["value"] for row in rows}


def write_app_settings(next_settings: dict[str, str]) -> None:
    """把一组配置写入 app_settings 表。

    参数：
        next_settings：要写入的配置字典，key 必须在 LLM_CONFIG_KEYS 中。

    返回值：
        None：这个函数只负责写数据库。
    """

    # updated_at 使用 UTC 时间，便于跨地区或部署环境排查配置变更。
    updated_at = datetime.now(UTC).isoformat()

    init_database()

    with get_database_connection() as connection:
        for key, value in next_settings.items():
            # 后端限制允许保存的 key，避免异常请求写入任意配置项。
            if key not in LLM_CONFIG_KEYS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"不支持的配置项：{key}",
                )

            connection.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, updated_at),
            )
        connection.commit()
