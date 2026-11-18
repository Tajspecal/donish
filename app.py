"""Точка входа: создаёт приложение, подключает модули и запускает сервер.

Структура проекта:
    app.py        — запуск приложения
    config.py     — настройки (имя, база данных, секретный ключ)
    database.py   — подключение к SQLite и создание таблиц
    auth.py       — регистрация, вход, выход, проверка роли
    quiz.py       — тесты, вопросы, результаты (для студентов)
    admin.py      — панель преподавателя и администратора
    gemini.py     — генерация тестов через Gemini API
    schema.sql    — структура таблиц и тестовые данные
    templates/    — HTML и статические файлы (css, js)
"""
from flask import Flask, render_template

import config
from admin import admin_bp
from auth import auth_bp
from database import init_db
from quiz import quiz_bp


def create_app():
    app = Flask(__name__, static_folder='templates/static')
    app.secret_key = config.SECRET_KEY

    app.register_blueprint(auth_bp)
    app.register_blueprint(quiz_bp)
    app.register_blueprint(admin_bp)

    init_db()  # создаёт базу при первом запуске, добавляет недостающие столбцы и администратора

    @app.route('/')
    def index():
        return render_template('index.html')

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
