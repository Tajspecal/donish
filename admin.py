"""Панель преподавателя: тесты, вопросы, импорт файла, генерация через Gemini, управление пользователями."""
import json
import time
from contextlib import closing

from flask import Blueprint, jsonify, request, session

import config
import gemini
from auth import role_required
from database import get_db

admin_bp = Blueprint('admin', __name__)

STAFF = ('teacher', 'admin')
_last_generate = {}  # { user_id: время последней генерации } — пауза между запросами


def _save_questions(conn, test_id, questions):
    conn.executemany(
        'INSERT INTO questions (test_id, question_text, options, correct_answer) VALUES (?, ?, ?, ?);',
        [(test_id, q['question_text'], json.dumps(q['options'], ensure_ascii=False), q['correct_answer'])
         for q in questions]
    )


def _create_test(data, source):
    test, error = gemini.validate_test(data)
    if error:
        return jsonify({"error": error}), 400
    with closing(get_db()) as conn:
        cur = conn.execute(
            'INSERT INTO tests (title, description, created_by, source, created_at) '
            'VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP);',
            (test['title'], test['description'], session['user_id'], source)
        )
        _save_questions(conn, cur.lastrowid, test['questions'])
        conn.commit()
    return jsonify({"id": cur.lastrowid, "questions": len(test['questions'])}), 201


# ---------- Тесты ----------

@admin_bp.route('/api/admin/tests', methods=['GET'])
@role_required(*STAFF)
def list_tests():
    with closing(get_db()) as conn:
        rows = conn.execute(
            '''SELECT t.id, t.title, t.description, t.source, t.created_at,
                      (SELECT COUNT(*) FROM questions q WHERE q.test_id = t.id) AS questions,
                      u.username AS author
               FROM tests t LEFT JOIN users u ON u.id = t.created_by
               ORDER BY t.id DESC;'''
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@admin_bp.route('/api/admin/tests', methods=['POST'])
@role_required(*STAFF)
def create_test():
    return _create_test(request.json, 'manual')


@admin_bp.route('/api/admin/tests/<int:test_id>', methods=['GET'])
@role_required(*STAFF)
def get_test(test_id):
    with closing(get_db()) as conn:
        test = conn.execute('SELECT id, title, description, source FROM tests WHERE id = ?;', (test_id,)).fetchone()
        if not test:
            return jsonify({"error": "Тест не найден"}), 404
        rows = conn.execute(
            'SELECT question_text, options, correct_answer FROM questions WHERE test_id = ? ORDER BY id;', (test_id,)
        ).fetchall()
    result = dict(test)
    result['questions'] = [
        {"question_text": r['question_text'], "options": json.loads(r['options']), "correct_answer": r['correct_answer']}
        for r in rows
    ]
    return jsonify(result)


@admin_bp.route('/api/admin/tests/<int:test_id>', methods=['PUT'])
@role_required(*STAFF)
def update_test(test_id):
    test, error = gemini.validate_test(request.json)
    if error:
        return jsonify({"error": error}), 400
    with closing(get_db()) as conn:
        if not conn.execute('SELECT 1 FROM tests WHERE id = ?;', (test_id,)).fetchone():
            return jsonify({"error": "Тест не найден"}), 404
        conn.execute('UPDATE tests SET title = ?, description = ? WHERE id = ?;',
                     (test['title'], test['description'], test_id))
        conn.execute('DELETE FROM questions WHERE test_id = ?;', (test_id,))
        _save_questions(conn, test_id, test['questions'])
        conn.commit()
    return jsonify({"status": "ok", "questions": len(test['questions'])})


@admin_bp.route('/api/admin/tests/<int:test_id>', methods=['DELETE'])
@role_required(*STAFF)
def delete_test(test_id):
    with closing(get_db()) as conn:
        cur = conn.execute('DELETE FROM tests WHERE id = ?;', (test_id,))  # вопросы и результаты удалятся каскадом
        conn.commit()
    if cur.rowcount == 0:
        return jsonify({"error": "Тест не найден"}), 404
    return jsonify({"status": "ok"})


# ---------- Импорт и генерация ----------

@admin_bp.route('/api/admin/import', methods=['POST'])
@role_required(*STAFF)
def import_test():
    data = request.json or {}
    source = data.get('source') if data.get('source') in ('import', 'gemini') else 'import'
    return _create_test(data, source)


@admin_bp.route('/api/admin/generate', methods=['POST'])
@role_required(*STAFF)
def generate():
    data = request.json or {}
    topic = (data.get('topic') or '').strip() if isinstance(data.get('topic'), str) else ''
    difficulty = data.get('difficulty', 'medium')
    language = data.get('language', 'ru')
    try:
        count = int(data.get('count', 5))
        options = int(data.get('options', 4))
    except (TypeError, ValueError):
        return jsonify({"error": "Число вопросов и вариантов должно быть числом"}), 400

    if not (3 <= len(topic) <= 200):
        return jsonify({"error": "Тема должна содержать от 3 до 200 символов"}), 400
    if not (1 <= count <= config.MAX_QUESTIONS):
        return jsonify({"error": f"Число вопросов — от 1 до {config.MAX_QUESTIONS}"}), 400
    if not (config.MIN_OPTIONS <= options <= config.MAX_OPTIONS):
        return jsonify({"error": f"Число вариантов — от {config.MIN_OPTIONS} до {config.MAX_OPTIONS}"}), 400
    if difficulty not in gemini.DIFFICULTY or language not in gemini.LANGUAGE:
        return jsonify({"error": "Неверная сложность или язык"}), 400

    # Пауза между запросами одного пользователя, чтобы не исчерпать лимит бесплатного уровня
    now = time.time()
    wait = config.GENERATE_PAUSE - (now - _last_generate.get(session['user_id'], 0))
    if wait > 0:
        return jsonify({"error": f"Подождите ещё {int(wait) + 1} с перед следующей генерацией"}), 429
    _last_generate[session['user_id']] = now

    try:
        test = gemini.generate_test(topic, count, options, difficulty, language)
    except gemini.GeminiError as e:
        if e.status != 429:  # неудачный запрос не должен блокировать повторную попытку на 10 секунд
            _last_generate.pop(session['user_id'], None)
        return jsonify({"error": e.message}), e.status
    return jsonify(test)


# ---------- Пользователи (только администратор) ----------

@admin_bp.route('/api/admin/users', methods=['GET'])
@role_required('admin')
def list_users():
    with closing(get_db()) as conn:
        rows = conn.execute('SELECT id, username, email, role, created_at FROM users ORDER BY id;').fetchall()
    return jsonify([dict(r) for r in rows])


def _admins_count(conn):
    return conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin';").fetchone()[0]


@admin_bp.route('/api/admin/users/<int:user_id>/role', methods=['PUT'])
@role_required('admin')
def set_role(user_id):
    role = (request.json or {}).get('role')
    if role not in ('student', 'teacher', 'admin'):
        return jsonify({"error": "Неверная роль"}), 400
    with closing(get_db()) as conn:
        user = conn.execute('SELECT role FROM users WHERE id = ?;', (user_id,)).fetchone()
        if not user:
            return jsonify({"error": "Пользователь не найден"}), 404
        if user['role'] == 'admin' and role != 'admin' and _admins_count(conn) <= 1:
            return jsonify({"error": "Нельзя убрать роль у последнего администратора"}), 400
        conn.execute('UPDATE users SET role = ? WHERE id = ?;', (role, user_id))
        conn.commit()
    return jsonify({"status": "ok"})


@admin_bp.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@role_required('admin')
def delete_user(user_id):
    if user_id == session['user_id']:
        return jsonify({"error": "Нельзя удалить самого себя"}), 400
    with closing(get_db()) as conn:
        user = conn.execute('SELECT role FROM users WHERE id = ?;', (user_id,)).fetchone()
        if not user:
            return jsonify({"error": "Пользователь не найден"}), 404
        if user['role'] == 'admin' and _admins_count(conn) <= 1:
            return jsonify({"error": "Нельзя удалить последнего администратора"}), 400
        conn.execute('DELETE FROM users WHERE id = ?;', (user_id,))
        conn.commit()
    return jsonify({"status": "ok"})
