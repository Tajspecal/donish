"""Тесты, вопросы, проверка ответов и история результатов."""
import json
from contextlib import closing

from flask import Blueprint, jsonify, request, session

from auth import login_required
from database import get_db

quiz_bp = Blueprint('quiz', __name__)


# 1. Список всех тестов
@quiz_bp.route('/api/tests', methods=['GET'])
@login_required
def get_tests():
    with closing(get_db()) as conn:
        rows = conn.execute('SELECT id, title, description FROM tests ORDER BY id;').fetchall()
    return jsonify([dict(r) for r in rows])


# 2. Вопросы теста (без правильных ответов)
@quiz_bp.route('/api/tests/<int:test_id>/questions', methods=['GET'])
@login_required
def get_test_questions(test_id):
    with closing(get_db()) as conn:
        rows = conn.execute(
            'SELECT id, question_text, options FROM questions WHERE test_id = ? ORDER BY id;',
            (test_id,)
        ).fetchall()
    questions = [
        {"id": r['id'], "question_text": r['question_text'], "options": json.loads(r['options'])}
        for r in rows
    ]
    return jsonify(questions)


# 3. Проверка ответов и сохранение результата (баллы считает сервер, пользователь — из сессии)
@quiz_bp.route('/api/submit', methods=['POST'])
@login_required
def submit_test():
    data = request.json or {}
    user_id = session['user_id']
    test_id = data.get('test_id')
    answers = data.get('answers', {})  # { "id_вопроса": индекс_варианта }

    with closing(get_db()) as conn:
        questions = conn.execute(
            'SELECT id, correct_answer FROM questions WHERE test_id = ?;', (test_id,)
        ).fetchall()
        if not questions:
            return jsonify({"error": "Тест не найден"}), 404

        total = len(questions)
        right = sum(1 for q in questions if answers.get(str(q['id'])) == q['correct_answer'])
        score = round(right / total * 100)

        conn.execute(
            'INSERT INTO results (user_id, test_id, score) VALUES (?, ?, ?);',
            (user_id, test_id, score)
        )
        conn.commit()
    return jsonify({"status": "success", "score": score, "correct": right, "total": total})


# 4. История результатов текущего пользователя
@quiz_bp.route('/api/results', methods=['GET'])
@login_required
def get_results():
    with closing(get_db()) as conn:
        rows = conn.execute(
            '''SELECT r.id, r.score, t.title,
                      strftime('%Y-%m-%dT%H:%M:%SZ', r.created_at) AS created_at
               FROM results r
               JOIN tests t ON t.id = r.test_id
               WHERE r.user_id = ?
               ORDER BY r.id DESC;''',
            (session['user_id'],)
        ).fetchall()
    return jsonify([dict(r) for r in rows])
