"""Генерация теста с помощью Gemini API.

Используется только стандартная библиотека Python (urllib), поэтому ничего устанавливать не нужно.
Ключ берётся из переменной окружения GEMINI_API_KEY (файл .env) и никогда не отправляется в браузер.
"""
import json
import random
import socket
import urllib.error
import urllib.request

import config


class GeminiError(Exception):
    """Ошибка генерации: message показывается преподавателю, status — HTTP-код ответа сервера."""

    def __init__(self, message, status=502):
        super().__init__(message)
        self.message = message
        self.status = status


# Схема JSON, по которой модель обязана вернуть вопросы
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question_text": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "correct_answer": {"type": "integer"},
                },
                "required": ["question_text", "options", "correct_answer"],
            },
        },
    },
    "required": ["title", "description", "questions"],
}

DIFFICULTY = {"easy": "лёгкий (базовые понятия)", "medium": "средний", "hard": "сложный (требует понимания, а не заучивания)"}
LANGUAGE = {"ru": "русском", "en": "английском", "tj": "таджикском"}


def build_prompt(topic, count, options, difficulty, language, test_type="choice"):
    base = (
        f"Составь тест для студентов по теме «{topic}».\n"
        f"Количество вопросов: {count}. Уровень сложности: {DIFFICULTY[difficulty]}.\n"
        f"Пиши на {LANGUAGE[language]} языке. В title дай короткое название теста (до 80 символов), "
        f"в description — одно предложение."
    )
    if test_type == "matching":
        return (
            base
            + f" Это тест на соответствие. В каждом вопросе должно быть ровно {options} пар. "
            + "Верни question_type: \"matching\" и поле pairs из объектов left/right."
        )
    return (
        base
        + f" У каждого вопроса ровно {options} вариантов ответа, и только один из них правильный. "
        + "Верни question_type: \"choice\", поле options и номер correct_answer, начиная с нуля."
    )


def _request_body(prompt, test_type="choice"):
    """Формат JSON-ответа для метода Gemini generateContent."""
    schema = dict(RESPONSE_SCHEMA)
    if test_type == "matching":
        schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "questions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question_type": {"type": "string"},
                            "question_text": {"type": "string"},
                            "pairs": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "left": {"type": "string"},
                                        "right": {"type": "string"},
                                    },
                                    "required": ["left", "right"],
                                },
                            },
                        },
                        "required": ["question_type", "question_text", "pairs"],
                    },
                },
            },
            "required": ["title", "description", "questions"],
        }
    config_part = {"responseMimeType": "application/json", "responseSchema": schema}
    config_part["temperature"] = 0.7
    return {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": config_part}


def _post(body):
    url = f"{config.GEMINI_API_URL}/models/{config.GEMINI_MODEL}:generateContent"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": config.GEMINI_API_KEY},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=config.GEMINI_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_error_detail(e):
    try:
        return json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
    except Exception:
        return ""


def _call_api(prompt, test_type="choice"):
    if not config.GEMINI_API_KEY:
        raise GeminiError("Генерация не настроена: добавьте ключ GEMINI_API_KEY в файл .env и перезапустите сервер.", 503)

    try:
        return _post(_request_body(prompt, test_type))
    except urllib.error.HTTPError as e:
        detail = getattr(e, "detail", None)
        if detail is None:
            detail = _http_error_detail(e)
        print(f"[Gemini] HTTP {e.code}: {detail}")  # подробности — только в консоль сервера
        if e.code == 429:
            raise GeminiError("Лимит запросов бесплатного уровня исчерпан. Подождите и повторите позже.", 429)
        if e.code in (400, 401, 403, 404):
            raise GeminiError("Gemini отклонил запрос: проверьте ключ GEMINI_API_KEY и название модели (см. консоль сервера).", 502)
        raise GeminiError("Сервис Gemini временно недоступен. Повторите попытку позже.", 502)
    except (socket.timeout, TimeoutError):
        raise GeminiError("Gemini не ответил вовремя. Повторите попытку.", 504)
    except ConnectionError as e:
        print(f"[Gemini] соединение прервано: {e}")
        raise GeminiError("Нет связи с сервисом Gemini. Проверьте интернет.", 502)
    except urllib.error.URLError as e:
        print(f"[Gemini] нет связи: {e.reason}")
        raise GeminiError("Нет связи с сервисом Gemini. Проверьте интернет.", 502)


def _extract_json(response):
    try:
        text = response["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except (KeyError, IndexError, TypeError, ValueError):
        raise ValueError("Ответ модели не является корректным JSON")


def validate_test(data, max_questions=None):
    """Проверяет структуру теста (используется и для импорта файла, и для ответа Gemini).
    Возвращает (очищенный_тест, None) или (None, текст_ошибки)."""
    if not isinstance(data, dict):
        return None, "Файл должен содержать объект JSON"
    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        return None, "Название теста не может быть пустым"
    if len(title.strip()) > 200:
        return None, "Название теста длиннее 200 символов"
    description = data.get("description") or ""
    if not isinstance(description, str):
        return None, "Описание должно быть текстом"
    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        return None, "В тесте должен быть хотя бы один вопрос"
    limit = max_questions or config.MAX_QUESTIONS
    if len(questions) > limit:
        return None, f"В тесте не может быть больше {limit} вопросов"

    inferred_types = {q.get("question_type", "choice") if isinstance(q, dict) else None for q in questions}
    if len(inferred_types) != 1:
        return None, "В одном тесте могут быть только вопросы одного типа"
    test_type = data.get("test_type") or next(iter(inferred_types))
    if test_type not in ("choice", "matching"):
        return None, "Неверный тип теста"

    clean = []
    for n, q in enumerate(questions, 1):
        if not isinstance(q, dict):
            return None, f"Вопрос {n}: неверный формат"
        text = q.get("question_text")
        if not isinstance(text, str) or not text.strip():
            return None, f"Вопрос {n}: текст вопроса пуст"
        question_type = q.get("question_type", "choice")
        if question_type not in ("choice", "matching"):
            return None, f"Вопрос {n}: неверный тип"
        if test_type is not None and question_type != test_type:
            return None, f"Вопрос {n}: тип не соответствует типу теста"
        if question_type == "matching":
            pairs = q.get("pairs")
            if not isinstance(pairs, list) or not (config.MIN_OPTIONS <= len(pairs) <= config.MAX_OPTIONS):
                return None, f"Вопрос {n}: для соответствия нужно от {config.MIN_OPTIONS} до {config.MAX_OPTIONS} пар"
            clean_pairs = []
            left_values = []
            right_values = []
            for pair_n, pair in enumerate(pairs, 1):
                if not isinstance(pair, dict):
                    return None, f"Вопрос {n}: неверный формат пары {pair_n}"
                left = pair.get("left")
                right = pair.get("right")
                if not isinstance(left, str) or not left.strip() or not isinstance(right, str) or not right.strip():
                    return None, f"Вопрос {n}: элементы пары {pair_n} не заполнены"
                left = left.strip()
                right = right.strip()
                if left in left_values:
                    return None, f"Вопрос {n}: левые элементы повторяются"
                if right in right_values:
                    return None, f"Вопрос {n}: правые элементы повторяются"
                left_values.append(left)
                right_values.append(right)
                clean_pairs.append({"left": left, "right": right})
            clean.append({
                "question_type": "matching",
                "question_text": text.strip(),
                "pairs": clean_pairs,
            })
            continue
        opts = q.get("options")
        if not isinstance(opts, list) or not (config.MIN_OPTIONS <= len(opts) <= config.MAX_OPTIONS):
            return None, f"Вопрос {n}: должно быть от {config.MIN_OPTIONS} до {config.MAX_OPTIONS} вариантов ответа"
        if any(not isinstance(o, str) or not o.strip() for o in opts):
            return None, f"Вопрос {n}: есть пустой вариант ответа"
        opts = [o.strip() for o in opts]
        if len(set(o.lower() for o in opts)) != len(opts):
            return None, f"Вопрос {n}: варианты ответа повторяются"
        correct = q.get("correct_answer")
        if isinstance(correct, bool) or not isinstance(correct, int) or not (0 <= correct < len(opts)):
            return None, f"Вопрос {n}: номер правильного ответа указан неверно"
        clean.append({
            "question_type": "choice",
            "question_text": text.strip(),
            "options": opts,
            "correct_answer": correct,
        })

    return {"test_type": test_type, "title": title.strip(), "description": description.strip(), "questions": clean}, None


def _shuffle_options(test):
    """Модели часто ставят правильный ответ на одно и то же место — перемешиваем варианты."""
    for q in test["questions"]:
        if q["question_type"] == "matching":
            continue
        right = q["options"][q["correct_answer"]]
        random.shuffle(q["options"])
        q["correct_answer"] = q["options"].index(right)


def generate_test(topic, count, options, difficulty, language, test_type="choice"):
    """Возвращает проверенный черновик теста (в базу данных не записывается)."""
    prompt = build_prompt(topic, count, options, difficulty, language, test_type)
    last_error = "Ответ модели не соответствует формату"
    for _ in range(2):  # одна повторная попытка, если ответ не прошёл проверку
        response = _call_api(prompt, test_type)
        try:
            data = _extract_json(response)
        except ValueError as e:
            last_error = str(e)
            continue
        test, error = validate_test(data, max_questions=count)
        if error:
            last_error = error
            continue
        if test_type == "matching":
            if any(len(q["pairs"]) != options for q in test["questions"]):
                last_error = "Число пар соответствия не совпадает с запрошенным"
                continue
        elif any(len(q["options"]) != options for q in test["questions"]):
            last_error = "Число вариантов ответа не совпадает с запрошенным"
            continue
        _shuffle_options(test)
        test["warning"] = (
            f"Модель вернула {len(test['questions'])} вопросов вместо {count}." if len(test["questions"]) < count else ""
        )
        return test
    print(f"[Gemini] ответ не прошёл проверку: {last_error}")
    raise GeminiError("Модель вернула ответ в неверном формате. Повторите генерацию.", 502)
