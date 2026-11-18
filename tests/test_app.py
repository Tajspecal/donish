"""Автотесты платформы «Дониш». Запуск из папки проекта: python -m unittest discover -s tests -v

Gemini заменён локальным поддельным сервером, поэтому интернет и ключ не нужны.
"""
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_tmp = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmp, "test.db")
os.environ["ADMIN_PASSWORD"] = "adminpass"
os.environ["GEMINI_API_KEY"] = "test-key"

import config  # noqa: E402

GOOD = {
    "title": "Сети",
    "description": "Основы сетей",
    "questions": [
        {"question_text": f"Вопрос {i}", "options": ["а", "б", "в", "г"], "correct_answer": i % 4} for i in range(5)
    ],
}


class FakeGemini(BaseHTTPRequestHandler):
    mode = "ok"      # ok | 429 | disconnect | bad_json | bad_format | wrong_options
    calls = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeGemini.calls.append({"path": self.path, "key": self.headers.get("x-goog-api-key"), "body": body})
        mode = FakeGemini.mode
        if mode == "429":
            return self._send(429, {"error": {"message": "quota"}})
        if mode == "disconnect":
            self.connection.close()
            return
        if mode == "bad_json":
            text = "это не json"
        elif mode == "bad_format":
            text = json.dumps({"title": "x", "description": "", "questions": [{"question_text": "q", "options": ["a"], "correct_answer": 0}]})
        elif mode == "wrong_options":
            text = json.dumps({**GOOD, "questions": [{"question_text": "q", "options": ["a", "b"], "correct_answer": 0}]})
        else:
            text = json.dumps(GOOD)
        self._send(200, {"candidates": [{"content": {"parts": [{"text": text}]}}]})

    def _send(self, code, data):
        raw = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


server = HTTPServer(("127.0.0.1", 0), FakeGemini)
threading.Thread(target=server.serve_forever, daemon=True).start()
config.GEMINI_API_URL = f"http://127.0.0.1:{server.server_port}/v1beta"
config.GENERATE_PAUSE = 0

import admin  # noqa: E402
from app import app  # noqa: E402


def client():
    return app.test_client()


def login(c, username, password):
    r = c.post("/api/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def register(c, username):
    r = c.post("/api/register", json={"username": username, "email": f"{username}@x.kz", "password": "pass1234"})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


class Base(unittest.TestCase):
    def setUp(self):
        FakeGemini.mode = "ok"
        FakeGemini.calls.clear()
        admin._last_generate.clear()
        config.GENERATE_PAUSE = 0


class AuthTests(Base):
    def test_register_gives_student_role(self):
        c = client()
        self.assertEqual(register(c, "stud1")["role"], "student")
        self.assertEqual(c.get("/api/me").get_json()["role"], "student")

    def test_duplicate_and_bad_data(self):
        c = client()
        register(c, "dup")
        r = client().post("/api/register", json={"username": "dup", "email": "n@x.kz", "password": "1234"})
        self.assertEqual(r.status_code, 409)
        r = client().post("/api/register", json={"username": "ab", "email": "n@x.kz", "password": "1234"})
        self.assertEqual(r.status_code, 400)

    def test_login_wrong_password(self):
        r = client().post("/api/login", json={"username": "admin", "password": "nope"})
        self.assertEqual(r.status_code, 401)

    def test_admin_created_on_first_start(self):
        c = client()
        self.assertEqual(login(c, "admin", "adminpass")["role"], "admin")

    def test_tests_require_login(self):
        self.assertEqual(client().get("/api/tests").status_code, 401)


class RolesTests(Base):
    def test_student_cannot_use_admin_routes(self):
        c = client()
        register(c, "stud2")
        for method, url in [("get", "/api/admin/tests"), ("post", "/api/admin/tests"), ("post", "/api/admin/import"),
                            ("post", "/api/admin/generate"), ("get", "/api/admin/users"),
                            ("delete", "/api/admin/tests/1"), ("put", "/api/admin/users/1/role")]:
            r = getattr(c, method)(url, json={})
            self.assertEqual(r.status_code, 403, url)
        self.assertEqual(FakeGemini.calls, [])

    def test_anonymous_gets_401(self):
        self.assertEqual(client().get("/api/admin/tests").status_code, 401)

    def test_teacher_has_no_user_management(self):
        a = client()
        login(a, "admin", "adminpass")
        c = client()
        uid = register(c, "teach1")["id"]
        self.assertEqual(a.put(f"/api/admin/users/{uid}/role", json={"role": "teacher"}).status_code, 200)
        self.assertEqual(c.get("/api/admin/tests").status_code, 200)   # роль берётся из базы сразу
        self.assertEqual(c.get("/api/admin/users").status_code, 403)

    def test_last_admin_is_protected(self):
        a = client()
        me = login(a, "admin", "adminpass")
        self.assertEqual(a.put(f"/api/admin/users/{me['id']}/role", json={"role": "student"}).status_code, 400)
        self.assertEqual(a.delete(f"/api/admin/users/{me['id']}").status_code, 400)

    def test_bad_role_rejected(self):
        a = client()
        me = login(a, "admin", "adminpass")
        self.assertEqual(a.put(f"/api/admin/users/{me['id']}/role", json={"role": "boss"}).status_code, 400)

    def test_deleted_user_session_stops_working(self):
        a = client()
        login(a, "admin", "adminpass")
        c = client()
        uid = register(c, "gone")["id"]
        self.assertEqual(a.delete(f"/api/admin/users/{uid}").status_code, 200)
        self.assertEqual(c.get("/api/tests").status_code, 200)  # студенту без роли проверки достаточно сессии
        self.assertEqual(c.get("/api/admin/tests").status_code, 401)


class CrudTests(Base):
    def setUp(self):
        super().setUp()
        self.a = client()
        login(self.a, "admin", "adminpass")

    def test_create_edit_delete(self):
        r = self.a.post("/api/admin/tests", json=GOOD)
        self.assertEqual(r.status_code, 201)
        tid = r.get_json()["id"]
        one = self.a.get(f"/api/admin/tests/{tid}").get_json()
        self.assertEqual(one["source"], "manual")
        self.assertEqual(len(one["questions"]), 5)

        edited = {**GOOD, "title": "Новое название", "questions": GOOD["questions"][:2]}
        self.assertEqual(self.a.put(f"/api/admin/tests/{tid}", json=edited).status_code, 200)
        one = self.a.get(f"/api/admin/tests/{tid}").get_json()
        self.assertEqual((one["title"], len(one["questions"])), ("Новое название", 2))

        row = [t for t in self.a.get("/api/admin/tests").get_json() if t["id"] == tid][0]
        self.assertEqual((row["questions"], row["author"]), (2, "admin"))

        self.assertEqual(self.a.delete(f"/api/admin/tests/{tid}").status_code, 200)
        self.assertEqual(self.a.get(f"/api/admin/tests/{tid}").status_code, 404)
        self.assertEqual(self.a.delete(f"/api/admin/tests/{tid}").status_code, 404)

    def test_validation(self):
        bad = [
            {**GOOD, "title": "  "},
            {**GOOD, "questions": []},
            {**GOOD, "questions": [{"question_text": "q", "options": ["a"], "correct_answer": 0}]},
            {**GOOD, "questions": [{"question_text": "q", "options": ["a", "b"], "correct_answer": 2}]},
            {**GOOD, "questions": [{"question_text": "q", "options": ["a", "b"], "correct_answer": True}]},
            {**GOOD, "questions": [{"question_text": "q", "options": ["a", "a"], "correct_answer": 0}]},
            {**GOOD, "questions": [{"question_text": "", "options": ["a", "b"], "correct_answer": 0}]},
            {**GOOD, "questions": [{"question_text": "q", "options": ["a", ""], "correct_answer": 0}]},
            {**GOOD, "questions": [GOOD["questions"][0]] * 21},
            {"title": "x" * 201, "questions": GOOD["questions"]},
            [],
        ]
        for data in bad:
            self.assertEqual(self.a.post("/api/admin/tests", json=data).status_code, 400, str(data)[:80])

    def test_import_keeps_source(self):
        r = self.a.post("/api/admin/import", json={**GOOD, "source": "gemini"})
        tid = r.get_json()["id"]
        self.assertEqual(self.a.get(f"/api/admin/tests/{tid}").get_json()["source"], "gemini")
        r = self.a.post("/api/admin/import", json={**GOOD, "source": "hacker"})
        self.assertEqual(self.a.get(f"/api/admin/tests/{r.get_json()['id']}").get_json()["source"], "import")

    def test_student_flow_and_scoring(self):
        tid = self.a.post("/api/admin/tests", json=GOOD).get_json()["id"]
        s = client()
        register(s, "stud_flow")
        qs = s.get(f"/api/tests/{tid}/questions").get_json()
        self.assertEqual(len(qs), 5)
        self.assertNotIn("correct_answer", qs[0])
        answers = {str(q["id"]): i % 4 for i, q in enumerate(qs)}   # все верные
        r = s.post("/api/submit", json={"test_id": tid, "answers": answers}).get_json()
        self.assertEqual((r["score"], r["correct"], r["total"]), (100, 5, 5))
        answers[str(qs[0]["id"])] = 3                              # одна ошибка
        self.assertEqual(s.post("/api/submit", json={"test_id": tid, "answers": answers}).get_json()["score"], 80)
        self.assertEqual(len(s.get("/api/results").get_json()), 2)

    def test_delete_test_removes_results(self):
        tid = self.a.post("/api/admin/tests", json=GOOD).get_json()["id"]
        s = client()
        register(s, "stud_del")
        s.post("/api/submit", json={"test_id": tid, "answers": {}})
        self.a.delete(f"/api/admin/tests/{tid}")
        self.assertEqual(s.get("/api/results").get_json(), [])


class GenerateTests(Base):
    PARAMS = {"topic": "Компьютерные сети", "count": 5, "options": 4, "difficulty": "medium", "language": "ru"}

    def setUp(self):
        super().setUp()
        self.a = client()
        login(self.a, "admin", "adminpass")

    def n_tests(self):
        return len(self.a.get("/api/admin/tests").get_json())

    def test_success_returns_draft_and_does_not_save(self):
        before = self.n_tests()
        r = self.a.post("/api/admin/generate", json=self.PARAMS)
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(len(data["questions"]), 5)
        for q in data["questions"]:  # после перемешивания правильный ответ должен остаться правильным
            self.assertTrue(0 <= q["correct_answer"] < 4)
        self.assertEqual(self.n_tests(), before)
        call = FakeGemini.calls[0]
        self.assertEqual(call["key"], "test-key")
        self.assertIn("Компьютерные сети", call["body"]["contents"][0]["parts"][0]["text"])
        self.assertIn("generateContent", call["path"])

    def test_shuffle_keeps_correct_text(self):
        d = self.a.post("/api/admin/generate", json=self.PARAMS).get_json()
        # в GOOD правильный вариант вопроса i — элемент ["а","б","в","г"][i % 4]
        for i, q in enumerate(d["questions"]):
            self.assertEqual(q["options"][q["correct_answer"]], ["а", "б", "в", "г"][i % 4])

    def test_rate_limit_429(self):
        FakeGemini.mode = "429"
        r = self.a.post("/api/admin/generate", json=self.PARAMS)
        self.assertEqual(r.status_code, 429)
        self.assertIn("Лимит", r.get_json()["error"])

    def test_disconnected_service_returns_gateway_error(self):
        FakeGemini.mode = "disconnect"
        r = self.a.post("/api/admin/generate", json=self.PARAMS)
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.get_json()["error"], "Нет связи с сервисом Gemini. Проверьте интернет.")

    def test_bad_json_retried_then_error(self):
        FakeGemini.mode = "bad_json"
        r = self.a.post("/api/admin/generate", json=self.PARAMS)
        self.assertEqual(r.status_code, 502)
        self.assertEqual(len(FakeGemini.calls), 2)  # одна повторная попытка

    def test_schema_violation_rejected(self):
        FakeGemini.mode = "bad_format"
        self.assertEqual(self.a.post("/api/admin/generate", json=self.PARAMS).status_code, 502)

    def test_wrong_option_count_rejected(self):
        FakeGemini.mode = "wrong_options"
        self.assertEqual(self.a.post("/api/admin/generate", json=self.PARAMS).status_code, 502)

    def test_uses_generate_content_json_response_config(self):
        r = self.a.post("/api/admin/generate", json=self.PARAMS)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(FakeGemini.calls), 1)
        generation_config = FakeGemini.calls[0]["body"]["generationConfig"]
        self.assertEqual(generation_config["responseMimeType"], "application/json")
        self.assertIn("responseSchema", generation_config)
        self.assertNotIn("responseFormat", generation_config)

    def test_fewer_questions_gives_warning(self):
        r = self.a.post("/api/admin/generate", json={**self.PARAMS, "count": 8})
        self.assertIn("5 вопросов вместо 8", r.get_json()["warning"])

    def test_parameter_validation(self):
        for patch in [{"topic": "ab"}, {"topic": "x" * 201}, {"count": 0}, {"count": 21}, {"options": 1},
                      {"options": 7}, {"difficulty": "insane"}, {"language": "xx"}, {"count": "abc"}, {"topic": 5}]:
            r = self.a.post("/api/admin/generate", json={**self.PARAMS, **patch})
            self.assertEqual(r.status_code, 400, patch)
        self.assertEqual(FakeGemini.calls, [])

    def test_pause_between_requests(self):
        config.GENERATE_PAUSE = 60
        self.assertEqual(self.a.post("/api/admin/generate", json=self.PARAMS).status_code, 200)
        self.assertEqual(self.a.post("/api/admin/generate", json=self.PARAMS).status_code, 429)
        self.assertEqual(len(FakeGemini.calls), 1)

    def test_no_key_configured(self):
        old = config.GEMINI_API_KEY
        config.GEMINI_API_KEY = ""
        try:
            r = self.a.post("/api/admin/generate", json=self.PARAMS)
        finally:
            config.GEMINI_API_KEY = old
        self.assertEqual(r.status_code, 503)
        self.assertEqual(FakeGemini.calls, [])

    def test_key_never_sent_to_browser(self):
        r = self.a.post("/api/admin/generate", json=self.PARAMS)
        self.assertNotIn("test-key", r.get_data(as_text=True))
        self.assertNotIn("test-key", self.a.get("/").get_data(as_text=True))


class MigrationTests(unittest.TestCase):
    def test_old_database_gets_new_columns(self):
        import sqlite3
        import database
        path = os.path.join(_tmp, "old.db")
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'student', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE tests (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT);
            INSERT INTO tests (title) VALUES ('старый');
        """)
        conn.commit(); conn.close()
        old = config.DB_PATH
        config.DB_PATH = path
        try:
            database.init_db()
            conn = database.get_db()
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(tests)")}
            self.assertTrue({"created_by", "source", "created_at"} <= cols)
            self.assertEqual(conn.execute("SELECT source FROM tests").fetchone()[0], "manual")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0], 1)
            conn.close()
        finally:
            config.DB_PATH = old


if __name__ == "__main__":
    unittest.main()
