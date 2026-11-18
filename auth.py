"""Регистрация, вход, выход и проверка авторизации."""
import sqlite3
from contextlib import closing
from functools import wraps

from flask import Blueprint, jsonify, request, session
from werkzeug.security import generate_password_hash, check_password_hash

from database import get_db

auth_bp = Blueprint('auth', __name__)


# Декоратор: пускает только авторизованных
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "Необходима авторизация"}), 401
        return f(*args, **kwargs)
    return wrapper


# Декоратор: пускает только пользователей с нужной ролью (роль берётся из базы при каждом запросе)
def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({"error": "Необходима авторизация"}), 401
            with closing(get_db()) as conn:
                row = conn.execute('SELECT role FROM users WHERE id = ?;', (session['user_id'],)).fetchone()
            if not row:  # пользователя удалили, пока сессия была активна
                session.clear()
                return jsonify({"error": "Необходима авторизация"}), 401
            if row['role'] not in roles:
                return jsonify({"error": "Недостаточно прав"}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator


@auth_bp.route('/api/register', methods=['POST'])
def register():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if len(username) < 3:
        return jsonify({"error": "Логин должен содержать минимум 3 символа"}), 400
    if len(username) > 50:
        return jsonify({"error": "Логин слишком длинный"}), 400
    if '@' not in email or '.' not in email.split('@')[-1] or len(email) > 100:
        return jsonify({"error": "Введите корректный email"}), 400
    if len(password) < 4:
        return jsonify({"error": "Пароль должен содержать минимум 4 символа"}), 400

    with closing(get_db()) as conn:
        if conn.execute('SELECT 1 FROM users WHERE username = ?;', (username,)).fetchone():
            return jsonify({"error": "Такой логин уже занят"}), 409
        if conn.execute('SELECT 1 FROM users WHERE LOWER(email) = ?;', (email,)).fetchone():
            return jsonify({"error": "Этот email уже зарегистрирован"}), 409

        try:
            cur = conn.execute(
                "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, 'student');",
                (username, email, generate_password_hash(password))
            )
            conn.commit()
        except sqlite3.IntegrityError:
            return jsonify({"error": "Такой логин или email уже занят"}), 409
        user_id = cur.lastrowid

    session['user_id'] = user_id
    session['username'] = username
    return jsonify({"id": user_id, "username": username, "role": "student"}), 201


@auth_bp.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    with closing(get_db()) as conn:
        user = conn.execute(
            'SELECT id, username, password_hash, role FROM users WHERE username = ?;', (username,)
        ).fetchone()

    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({"error": "Неверный логин или пароль"}), 401

    session['user_id'] = user['id']
    session['username'] = user['username']
    return jsonify({"id": user['id'], "username": user['username'], "role": user['role']})


@auth_bp.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"status": "ok"})


@auth_bp.route('/api/me', methods=['GET'])
def me():
    if 'user_id' not in session:
        return jsonify({"authenticated": False})
    with closing(get_db()) as conn:
        user = conn.execute('SELECT id, username, role FROM users WHERE id = ?;', (session['user_id'],)).fetchone()
    if not user:
        session.clear()
        return jsonify({"authenticated": False})
    return jsonify({"authenticated": True, "id": user['id'], "username": user['username'], "role": user['role']})
