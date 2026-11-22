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

-- ===== Тестовые данные =====
INSERT INTO tests (id, title, description) VALUES
    (1, 'Основы Python',  'Базовые понятия языка Python: типы данных, функции, списки.'),
    (2, 'HTML и CSS',     'Верстка сайтов: теги, стили, отступы.'),
    (3, 'Основы SQL',     'Запросы к базе данных: SELECT, INSERT, DELETE, ключи.');

INSERT INTO questions (test_id, question_text, options, correct_answer) VALUES
    (1, 'Какой функцией выводят текст на экран?',        '["print()", "echo()", "write()", "console.log()"]', 0),
    (1, 'Какой тип данных у значения 3.14?',             '["int", "float", "str", "bool"]', 1),
    (1, 'Как создать список в Python?',                  '["{1, 2, 3}", "(1, 2, 3)", "[1, 2, 3]", "<1, 2, 3>"]', 2),
    (1, 'Что вернёт len("test")?',                       '["3", "4", "5", "Ошибку"]', 1),
    (1, 'Какое ключевое слово объявляет функцию?',       '["function", "def", "func", "lambda"]', 1),

    (2, 'Какой тег создаёт ссылку?',                     '["<link>", "<a>", "<href>", "<url>"]', 1),
    (2, 'Какое CSS-свойство меняет цвет текста?',        '["font-color", "text-color", "color", "fill"]', 2),
    (2, 'Какой тег задаёт самый крупный заголовок?',     '["<h6>", "<head>", "<h1>", "<title>"]', 2),
    (2, 'Каким тегом подключают внешний файл стилей?',   '["<style>", "<link>", "<css>", "<script>"]', 1),
    (2, 'Какое свойство задаёт внутренние отступы?',     '["margin", "padding", "spacing", "border"]', 1),

    (3, 'Какая команда выбирает данные из таблицы?',     '["GET", "SELECT", "FETCH", "OPEN"]', 1),
    (3, 'Какая команда добавляет новую строку?',         '["INSERT", "ADD ROW", "APPEND", "PUT"]', 0),
    (3, 'Какое ключевое слово задаёт условие отбора?',   '["FILTER", "WHEN", "WHERE", "CHECK"]', 2),
    (3, 'Для чего нужен PRIMARY KEY?',                   '["Шифрует данные", "Однозначно идентифицирует строку", "Удаляет дубликаты в запросе", "Сортирует таблицу"]', 1),
    (3, 'Какая команда удаляет строки из таблицы?',      '["REMOVE", "DROP ROW", "DELETE", "CUT"]', 2);
