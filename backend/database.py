"""
数据库层 - SQLite
数据文件位置：backend/data/saa.db
图片存储位置：backend/data/images/
"""
import sqlite3
import hashlib
import uuid
import os
import base64
from pathlib import Path
from datetime import datetime

# ---------- 路径配置 ----------
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "saa.db"
IMAGES_DIR = DATA_DIR / "images"
IMAGES_DIR.mkdir(exist_ok=True)


# ==================== 数据库连接 ====================

def get_db() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row  # 让查询结果可以用 dict 方式访问
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """初始化数据库表（首次启动自动创建）"""
    conn = get_db()
    conn.executescript("""
        -- 用户表
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT    UNIQUE NOT NULL,
            password_hash TEXT  NOT NULL,
            salt        TEXT    NOT NULL,
            token       TEXT    DEFAULT NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 错题本表（user_id 关联用户，确保数据隔离）
        CREATE TABLE IF NOT EXISTS errorbook (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            question    TEXT    NOT NULL,          -- 题目标题 / 题目内容
            answer      TEXT    DEFAULT '',        -- 正确答案 / 笔记
            image_path  TEXT    DEFAULT NULL,      -- 配图路径（可选）
            subject     TEXT    DEFAULT '',        -- 科目/标签
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        -- 错题分析报告表
        CREATE TABLE IF NOT EXISTS errorbook_analyses (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            errorbook_id    INTEGER NOT NULL UNIQUE,
            user_id         INTEGER NOT NULL,
            analysis_text   TEXT    NOT NULL,       -- AI 分析报告（Markdown）
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (errorbook_id) REFERENCES errorbook(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        -- AI 对话历史表（每条消息）
        CREATE TABLE IF NOT EXISTS chat_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            session_id  INTEGER DEFAULT NULL,       -- 所属会话
            role        TEXT    NOT NULL,
            content     TEXT    NOT NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        -- 对话会话表
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            title       TEXT    DEFAULT '新对话',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        -- 创建索引加速查询
        CREATE INDEX IF NOT EXISTS idx_errorbook_user ON errorbook(user_id);
        CREATE INDEX IF NOT EXISTS idx_users_token ON users(token);
        CREATE INDEX IF NOT EXISTS idx_analyses_errorbook ON errorbook_analyses(errorbook_id);
        CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_history(user_id);
        CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON chat_sessions(user_id);
    """)
    # 兼容旧数据库：如果 chat_history 表缺少 session_id 列，自动补充
    cols = [c[1] for c in conn.execute("PRAGMA table_info(chat_history)").fetchall()]
    if 'session_id' not in cols:
        conn.execute("ALTER TABLE chat_history ADD COLUMN session_id INTEGER DEFAULT NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_history(session_id)")
    conn.commit()
    conn.close()
    print(f"✅ 数据库已就绪: {DB_PATH}")


# ==================== 密码工具 ====================

def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """密码哈希，返回 (hash, salt)"""
    if salt is None:
        salt = uuid.uuid4().hex
    h = hashlib.sha256((password + salt).encode()).hexdigest()
    return h, salt


def verify_password(password: str, salt: str, stored_hash: str) -> bool:
    """验证密码"""
    h, _ = hash_password(password, salt)
    return h == stored_hash


# ==================== 用户操作 ====================

def create_user(username: str, password: str) -> dict | None:
    """
    注册新用户
    返回用户信息 dict，用户名已存在返回 None
    """
    conn = get_db()
    try:
        pwd_hash, salt = hash_password(password)
        token = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO users (username, password_hash, salt, token) VALUES (?, ?, ?, ?)",
            (username, pwd_hash, salt, token)
        )
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        return dict(user) if user else None
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def login_user(username: str, password: str) -> dict | None:
    """
    用户登录
    成功返回用户信息（含新 token），失败返回 None
    """
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not user:
        conn.close()
        return None

    if not verify_password(password, user["salt"], user["password_hash"]):
        conn.close()
        return None

    # 生成新 token
    token = uuid.uuid4().hex
    conn.execute("UPDATE users SET token=? WHERE id=?", (token, user["id"]))
    conn.commit()
    conn.close()

    result = dict(user)
    result["token"] = token
    return result


def get_user_by_token(token: str) -> dict | None:
    """根据 token 获取用户信息"""
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE token=?", (token,)).fetchone()
    conn.close()
    return dict(user) if user else None


# ==================== 错题本 CRUD ====================

def save_errorbook_image(user_id: int, image_base64: str) -> str | None:
    """
    保存错题本图片到文件系统
    返回相对路径，失败返回 None
    """
    if not image_base64:
        return None
    try:
        # 解码 base64
        img_data = base64.b64decode(image_base64)
        # 生成唯一文件名
        filename = f"{user_id}_{uuid.uuid4().hex[:12]}.png"
        filepath = IMAGES_DIR / filename
        with open(filepath, "wb") as f:
            f.write(img_data)
        return f"images/{filename}"  # 相对路径
    except Exception as e:
        print(f"图片保存失败: {e}")
        return None


def get_errorbook_items(user_id: int) -> list[dict]:
    """获取某用户的所有错题"""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM errorbook WHERE user_id=? ORDER BY updated_at DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_errorbook_item(user_id: int, question: str, answer: str = "",
                       image_base64: str = None, subject: str = "") -> dict | None:
    """添加一条错题"""
    # 先保存图片
    image_path = save_errorbook_image(user_id, image_base64) if image_base64 else None

    conn = get_db()
    now = datetime.now().isoformat()
    cursor = conn.execute(
        """INSERT INTO errorbook (user_id, question, answer, image_path, subject, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, question, answer, image_path, subject, now, now)
    )
    conn.commit()
    item = conn.execute("SELECT * FROM errorbook WHERE id=?", (cursor.lastrowid,)).fetchone()
    conn.close()
    return dict(item) if item else None


def update_errorbook_item(item_id: int, user_id: int, question: str = None,
                          answer: str = None, image_base64: str = None,
                          subject: str = None, keep_image: bool = True) -> dict | None:
    """修改一条错题（只更新传入的字段）"""
    conn = get_db()
    # 检查是否是本人的
    item = conn.execute(
        "SELECT * FROM errorbook WHERE id=? AND user_id=?",
        (item_id, user_id)
    ).fetchone()
    if not item:
        conn.close()
        return None

    # 构建更新字段
    updates = {}
    if question is not None:
        updates["question"] = question
    if answer is not None:
        updates["answer"] = answer
    if subject is not None:
        updates["subject"] = subject

    # 处理图片
    if image_base64 is not None and image_base64 != "":
        # 新图片 → 保存并更新路径
        image_path = save_errorbook_image(user_id, image_base64)
        updates["image_path"] = image_path
    elif not keep_image:
        # 要求删除图片
        # 删除旧文件
        if item["image_path"]:
            old_path = DATA_DIR / item["image_path"]
            if old_path.exists():
                old_path.unlink()
        updates["image_path"] = None

    if updates:
        updates["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [item_id, user_id]
        conn.execute(
            f"UPDATE errorbook SET {set_clause} WHERE id=? AND user_id=?",
            values
        )
        conn.commit()

    item = conn.execute("SELECT * FROM errorbook WHERE id=?", (item_id,)).fetchone()
    conn.close()
    return dict(item) if item else None


def delete_errorbook_item(item_id: int, user_id: int) -> bool:
    """删除一条错题（同时删除关联图片文件）"""
    conn = get_db()
    item = conn.execute(
        "SELECT * FROM errorbook WHERE id=? AND user_id=?",
        (item_id, user_id)
    ).fetchone()
    if not item:
        conn.close()
        return False

    # 删除图片文件
    if item["image_path"]:
        old_path = DATA_DIR / item["image_path"]
        if old_path.exists():
            old_path.unlink()

    conn.execute("DELETE FROM errorbook WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return True


# ==================== 错题分析报告 CRUD ====================

def save_analysis(errorbook_id: int, user_id: int, analysis_text: str) -> dict | None:
    """
    保存/更新一条 AI 分析报告（每个错题只保留最新一份）
    如果已存在则更新，不存在则插入
    """
    conn = get_db()
    # 检查错题是否属于该用户
    item = conn.execute(
        "SELECT id FROM errorbook WHERE id=? AND user_id=?",
        (errorbook_id, user_id)
    ).fetchone()
    if not item:
        conn.close()
        return None

    now = datetime.now().isoformat()
    existing = conn.execute(
        "SELECT id FROM errorbook_analyses WHERE errorbook_id=?",
        (errorbook_id,)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE errorbook_analyses SET analysis_text=?, created_at=? WHERE errorbook_id=?",
            (analysis_text, now, errorbook_id)
        )
    else:
        conn.execute(
            "INSERT INTO errorbook_analyses (errorbook_id, user_id, analysis_text, created_at) VALUES (?, ?, ?, ?)",
            (errorbook_id, user_id, analysis_text, now)
        )
    conn.commit()
    result = conn.execute(
        "SELECT * FROM errorbook_analyses WHERE errorbook_id=?",
        (errorbook_id,)
    ).fetchone()
    conn.close()
    return dict(result) if result else None


def get_analysis(errorbook_id: int, user_id: int) -> dict | None:
    """获取某条错题的 AI 分析报告"""
    conn = get_db()
    analysis = conn.execute(
        "SELECT a.* FROM errorbook_analyses a "
        "JOIN errorbook e ON a.errorbook_id = e.id "
        "WHERE a.errorbook_id=? AND e.user_id=?",
        (errorbook_id, user_id)
    ).fetchone()
    conn.close()
    return dict(analysis) if analysis else None


def delete_analysis(errorbook_id: int, user_id: int) -> bool:
    """删除某条错题的 AI 分析报告"""
    conn = get_db()
    item = conn.execute(
        "SELECT id FROM errorbook WHERE id=? AND user_id=?",
        (errorbook_id, user_id)
    ).fetchone()
    if not item:
        conn.close()
        return False
    conn.execute("DELETE FROM errorbook_analyses WHERE errorbook_id=?", (errorbook_id,))
    conn.commit()
    conn.close()
    return True


def get_all_analyses(user_id: int) -> list[dict]:
    """获取某用户的所有 AI 分析报告（含关联的错题信息）"""
    conn = get_db()
    rows = conn.execute("""
        SELECT a.id, a.errorbook_id, a.analysis_text, a.created_at,
               e.question, e.subject, e.image_path
        FROM errorbook_analyses a
        JOIN errorbook e ON a.errorbook_id = e.id
        WHERE a.user_id = ?
        ORDER BY a.created_at DESC
    """, (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ==================== 对话会话 CRUD ====================

def create_chat_session(user_id: int, title: str = "新对话") -> dict | None:
    """创建新的对话会话，返回 session 信息"""
    conn = get_db()
    now = datetime.now().isoformat()
    cursor = conn.execute(
        "INSERT INTO chat_sessions (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (user_id, title, now, now)
    )
    conn.commit()
    session = conn.execute("SELECT * FROM chat_sessions WHERE id=?", (cursor.lastrowid,)).fetchone()
    conn.close()
    return dict(session) if session else None


def get_chat_sessions(user_id: int) -> list[dict]:
    """获取某用户所有对话会话列表（按更新时间倒序）"""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM chat_sessions WHERE user_id=? ORDER BY updated_at DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_chat_session(session_id: int, user_id: int) -> dict | None:
    """获取单个会话信息"""
    conn = get_db()
    session = conn.execute(
        "SELECT * FROM chat_sessions WHERE id=? AND user_id=?",
        (session_id, user_id)
    ).fetchone()
    conn.close()
    return dict(session) if session else None


def update_session_title(session_id: int, user_id: int, title: str):
    """更新会话标题"""
    conn = get_db()
    conn.execute(
        "UPDATE chat_sessions SET title=?, updated_at=? WHERE id=? AND user_id=?",
        (title, datetime.now().isoformat(), session_id, user_id)
    )
    conn.commit()
    conn.close()


def touch_session(session_id: int):
    """更新会话的 updated_at 时间"""
    conn = get_db()
    conn.execute(
        "UPDATE chat_sessions SET updated_at=? WHERE id=?",
        (datetime.now().isoformat(), session_id)
    )
    conn.commit()
    conn.close()


def get_session_messages(session_id: int, user_id: int) -> list[dict]:
    """获取某个会话的所有消息（按时间正序）"""
    conn = get_db()
    # 先确认会话属于该用户
    session = conn.execute(
        "SELECT id FROM chat_sessions WHERE id=? AND user_id=?", (session_id, user_id)
    ).fetchone()
    if not session:
        conn.close()
        return []
    rows = conn.execute(
        "SELECT * FROM chat_history WHERE session_id=? ORDER BY created_at ASC",
        (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_session_messages(user_id: int, session_id: int, messages: list[dict], title: str = None) -> int:
    """
    保存消息到指定会话。如果 session_id=0 则自动创建新会话。
    返回 session_id，失败返回 0
    """
    if not messages:
        return 0

    conn = get_db()

    # 如果没有 session，新建一个
    if session_id == 0:
        now = datetime.now().isoformat()
        t = (title or messages[0].get("content", "新对话"))[:30]
        cursor = conn.execute(
            "INSERT INTO chat_sessions (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (user_id, t, now, now)
        )
        session_id = cursor.lastrowid
    else:
        # 验证会话属于该用户
        s = conn.execute(
            "SELECT id FROM chat_sessions WHERE id=? AND user_id=?",
            (session_id, user_id)
        ).fetchone()
        if not s:
            conn.close()
            return 0
        # 更新标题（如果有且不是默认值）
        if title and len(title) > len("新对话"):
            conn.execute(
                "UPDATE chat_sessions SET title=?, updated_at=? WHERE id=?",
                (title[:30], datetime.now().isoformat(), session_id)
            )

    # 插入消息
    now = datetime.now().isoformat()
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if not content:
            continue
        conn.execute(
            "INSERT INTO chat_history (user_id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, session_id, role, content, now)
        )

    # 更新时间戳
    conn.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (now, session_id))
    conn.commit()
    conn.close()
    return session_id


def delete_chat_session(session_id: int, user_id: int) -> bool:
    """删除一个会话及其所有消息"""
    conn = get_db()
    session = conn.execute(
        "SELECT id FROM chat_sessions WHERE id=? AND user_id=?", (session_id, user_id)
    ).fetchone()
    if not session:
        conn.close()
        return False
    conn.execute("DELETE FROM chat_history WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))
    conn.commit()
    conn.close()
    return True


# ==================== 启动时自动初始化 ====================
init_db()
