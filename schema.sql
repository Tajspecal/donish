-- Схема базы данных «Дониш» (SQLite).
-- Выполняется автоматически при первом запуске, когда файла donish.db ещё нет.
-- Первый администратор создаётся программой (database.py), потому что пароль нужно хранить в виде хеша.

PRAGMA foreign_keys = ON;

-- Пользователи
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'student'
                  CHECK (role IN ('student', 'teacher', 'admin')),
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Тесты (source — как создан: manual, import или gemini; created_by — кто создал)
CREATE TABLE tests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT,
    test_type   TEXT NOT NULL DEFAULT 'choice'
                CHECK (test_type IN ('choice', 'matching')),
    duration_minutes INTEGER
                CHECK (duration_minutes IS NULL OR duration_minutes BETWEEN 1 AND 600),
    created_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    source      TEXT NOT NULL DEFAULT 'manual'
                CHECK (source IN ('manual', 'import', 'gemini')),
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Вопросы (options — JSON-список вариантов, correct_answer — номер правильного, начиная с 0)
CREATE TABLE questions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id        INTEGER NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    question_type  TEXT NOT NULL DEFAULT 'choice'
                   CHECK (question_type IN ('choice', 'matching')),
    question_text  TEXT NOT NULL,
    options        TEXT NOT NULL,
    matching_pairs TEXT,
    correct_answer INTEGER NOT NULL
);

-- Результаты прохождения
CREATE TABLE results (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    test_id    INTEGER NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    score      INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
