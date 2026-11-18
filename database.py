import os
import sqlite3
from contextlib import closing

from werkzeug.security import generate_password_hash

import config


# Подключение к базе SQLite
def get_db():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _columns(conn, table):
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table});")}


# Если файла базы нет — создаём таблицы и тестовые данные из schema.sql.
# Если база уже есть, но создана старой версией — добавляем новые столбцы таблицы tests.
# После этого проверяем, что в системе есть хотя бы один администратор.
def init_db():
    if not os.path.exists(config.DB_PATH):
        with open(config.SCHEMA_PATH, encoding="utf-8") as f:
            sql = f.read()
        with closing(get_db()) as conn:
            conn.executescript(sql)
            conn.commit()

    with closing(get_db()) as conn:
        cols = _columns(conn, "tests")
        if "created_by" not in cols:
            conn.execute("ALTER TABLE tests ADD COLUMN created_by INTEGER REFERENCES users(id) ON DELETE SET NULL;")
        if "source" not in cols:
            conn.execute("ALTER TABLE tests ADD COLUMN source TEXT NOT NULL DEFAULT 'manual';")
        if "created_at" not in cols:
            conn.execute("ALTER TABLE tests ADD COLUMN created_at TEXT;")
        conn.commit()
        _ensure_admin(conn)


def _ensure_admin(conn):
    if conn.execute("SELECT 1 FROM users WHERE role = 'admin' LIMIT 1;").fetchone():
        return
    username, email = config.ADMIN_USERNAME, config.ADMIN_EMAIL
    existing = conn.execute(
        "SELECT id FROM users WHERE username = ? OR LOWER(email) = LOWER(?);", (username, email)
    ).fetchone()
    if existing:  # такой логин уже занят обычным пользователем — повышаем его
        conn.execute("UPDATE users SET role = 'admin' WHERE id = ?;", (existing["id"],))
    else:
        conn.execute(
            "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, 'admin');",
            (username, email, generate_password_hash(config.ADMIN_PASSWORD)),
        )
    conn.commit()
    print(f"[Дониш] Создан администратор: логин «{username}». Смените пароль в .env (ADMIN_PASSWORD) до первого запуска!")
