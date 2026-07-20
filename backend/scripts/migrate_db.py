"""一次性 DB 迁移：给 users 表加 email 列 + 创建 chat_sessions/chat_messages 表。

适用：已有旧 DB（idea28 email + idea29 chat 表之前创建的）。
新 clone 不需要跑（create_all 会自动建全表）。

用法：cd backend && PYTHONPATH=. uv run python scripts/migrate_db.py
"""

import sqlite3
import sys
from pathlib import Path


def main():
    db_path = Path(__file__).resolve().parent.parent / "data" / "stock.db"
    if not db_path.exists():
        print(f"DB not found at {db_path}")
        return 1
    c = sqlite3.connect(str(db_path))

    # 1. users 加 email
    cols = [r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()]
    if "email" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN email VARCHAR(100)")
        print("added email column to users")
    else:
        print("email column already exists")

    # 2. chat_sessions
    c.execute(
        """CREATE TABLE IF NOT EXISTS chat_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id),
        title VARCHAR(100) NOT NULL DEFAULT '新对话', agent_ids JSON DEFAULT '[]',
        summary TEXT, summary_upto_msg_id INTEGER, pinned BOOLEAN DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_message_at DATETIME)"""
    )
    print("chat_sessions OK")

    # 3. chat_messages
    c.execute(
        """CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
        role VARCHAR(20) NOT NULL, content TEXT NOT NULL DEFAULT '',
        agents_used JSON DEFAULT '[]', stocks_detected JSON DEFAULT '[]',
        token_count INTEGER DEFAULT 0, is_compressed BOOLEAN DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"""
    )
    print("chat_messages OK")

    c.commit()
    c.close()
    print("migration done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
