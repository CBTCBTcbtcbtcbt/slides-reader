"""SQLite 数据库初始化和连接管理。"""

import sqlite3

from config import DATABASE_PATH


def init_database() -> None:
    """初始化 SQLite 数据库和当前版本需要的表结构。

    返回值：
        None：这个函数只负责创建目录、表和兼容字段，不返回业务数据。
    """

    # 数据库文件位于 storage 目录下，所以必须先确保父目录存在。
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 使用 with 打开连接，可以在代码块结束时自动提交或回滚并关闭连接。
    with sqlite3.connect(DATABASE_PATH) as connection:
        # documents 表保存上传 slides 的基本信息。
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

        # 旧数据库可能缺少后续版本新增列，因此启动时自动补齐。
        document_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(documents)").fetchall()
        }
        if "error_message" not in document_columns:
            connection.execute("ALTER TABLE documents ADD COLUMN error_message TEXT")
        if "course_summary" not in document_columns:
            connection.execute("ALTER TABLE documents ADD COLUMN course_summary TEXT")
        if "course_summary_status" not in document_columns:
            connection.execute(
                "ALTER TABLE documents ADD COLUMN course_summary_status TEXT NOT NULL DEFAULT 'pending'"
            )
        if "course_summary_error" not in document_columns:
            connection.execute("ALTER TABLE documents ADD COLUMN course_summary_error TEXT")
        if "lecture_notes_paused" not in document_columns:
            connection.execute(
                "ALTER TABLE documents ADD COLUMN lecture_notes_paused INTEGER NOT NULL DEFAULT 0"
            )

        # pages 表保存 PDF 每一页的解析结果、截图和讲稿状态。
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pages (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                text TEXT NOT NULL,
                image_path TEXT,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(document_id, page_number),
                FOREIGN KEY(document_id) REFERENCES documents(id)
            )
            """
        )

        # pages 表同样需要兼容旧数据库字段。
        page_columns = {row[1] for row in connection.execute("PRAGMA table_info(pages)").fetchall()}
        if "image_path" not in page_columns:
            connection.execute("ALTER TABLE pages ADD COLUMN image_path TEXT")
        if "lecture_notes" not in page_columns:
            connection.execute("ALTER TABLE pages ADD COLUMN lecture_notes TEXT")
        if "lecture_notes_status" not in page_columns:
            connection.execute(
                "ALTER TABLE pages ADD COLUMN lecture_notes_status TEXT NOT NULL DEFAULT 'pending'"
            )
        if "lecture_notes_error" not in page_columns:
            connection.execute("ALTER TABLE pages ADD COLUMN lecture_notes_error TEXT")

        # note_blocks 表保存阅读器里的可拖动讲稿文字块。
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS note_blocks (
                id TEXT PRIMARY KEY,
                page_id TEXT NOT NULL,
                content TEXT NOT NULL,
                x REAL NOT NULL,
                y REAL NOT NULL,
                width REAL NOT NULL,
                height REAL NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(page_id),
                FOREIGN KEY(page_id) REFERENCES pages(id)
            )
            """
        )

        # chat_messages 表保存某页 slides 下方的问答历史。
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                page_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(page_id) REFERENCES pages(id)
            )
            """
        )

        # chat_attachments 表保存问答消息关联的图片附件元数据。
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_attachments (
                id TEXT PRIMARY KEY,
                chat_message_id TEXT NOT NULL,
                page_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                display_order INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(chat_message_id) REFERENCES chat_messages(id),
                FOREIGN KEY(page_id) REFERENCES pages(id)
            )
            """
        )

        # lecture_notes_queue 表保存逐页讲稿的待生成队列。
        # 同一个 page_id 只保留一条队列记录，重复点击重生成只会把旧记录更新回 waiting。
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS lecture_notes_queue (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                page_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(page_id),
                FOREIGN KEY(document_id) REFERENCES documents(id),
                FOREIGN KEY(page_id) REFERENCES pages(id)
            )
            """
        )

        # 队列查询总是按文档和状态过滤，再按页码取最早任务，因此补充索引减少扫描。
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_lecture_notes_queue_document_status
            ON lecture_notes_queue(document_id, status, page_number)
            """
        )

        # app_settings 表保存 WebUI 可编辑的 key-value 配置。
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        # exams 表保存为某份文档生成的试卷。
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS exams (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL,
                error_message TEXT,
                total_score INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id)
            )
            """
        )

        # exam_questions 表保存试卷中的具体题目。
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS exam_questions (
                id TEXT PRIMARY KEY,
                exam_id TEXT NOT NULL,
                question_number INTEGER NOT NULL,
                section TEXT NOT NULL,
                question_type TEXT NOT NULL,
                score INTEGER NOT NULL,
                content TEXT NOT NULL,
                options TEXT,
                answer TEXT,
                explanation TEXT,
                source_page INTEGER,
                expected_type TEXT,
                difficulty TEXT,
                knowledge_tag TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(exam_id) REFERENCES exams(id)
            )
            """
        )

        # exam_attempts 表保存用户的答题记录。
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS exam_attempts (
                id TEXT PRIMARY KEY,
                exam_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                score INTEGER,
                answers TEXT NOT NULL,
                FOREIGN KEY(exam_id) REFERENCES exams(id)
            )
            """
        )

        # wrong_questions 表保存用户答错的题目，用于错题本。
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS wrong_questions (
                id TEXT PRIMARY KEY,
                question_id TEXT NOT NULL,
                exam_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                user_answer TEXT,
                created_at TEXT NOT NULL,
                reviewed INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(question_id) REFERENCES exam_questions(id),
                FOREIGN KEY(exam_id) REFERENCES exams(id),
                FOREIGN KEY(attempt_id) REFERENCES exam_attempts(id)
            )
            """
        )

        # phase_exams 表保存综合多份课件的阶段考试。
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS phase_exams (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                document_ids TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                exam_id TEXT,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        # 为常用查询补充索引。
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_exams_document_id
            ON exams(document_id)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_exam_questions_exam_id
            ON exam_questions(exam_id)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_exam_attempts_exam_id
            ON exam_attempts(exam_id)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_wrong_questions_exam_id
            ON wrong_questions(exam_id)
            """
        )


def get_database_connection() -> sqlite3.Connection:
    """创建已经设置 row_factory 的 SQLite 连接。

    返回值：
        sqlite3.Connection：查询结果可通过字段名读取的数据库连接。
    """

    # row_factory 设置为 sqlite3.Row 后，row["title"] 这种写法才可用。
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection
