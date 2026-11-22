import os

# Папка проекта
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# Читаем файл .env (строки вида КЛЮЧ=значение), чтобы не хранить ключи в коде.
# Уже заданные переменные окружения имеют приоритет.
def _load_env(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env(os.path.join(BASE_DIR, ".env"))

# Название платформы
APP_NAME = "Дониш"

# База данных SQLite (файл создаётся автоматически при первом запуске)
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "donish.db"))
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

# Ключ для подписи сессий (cookie). Для реального сайта замените на свою длинную случайную строку.
SECRET_KEY = os.environ.get("SECRET_KEY", "donish-talabu-buzurgi-omuz")

# Первый администратор: создаётся при первом запуске, если в базе нет ни одного администратора.
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@donish.local")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

# Gemini API (бесплатный ключ: https://aistudio.google.com/api-keys)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# Название модели вынесено в настройки: Google периодически меняет список моделей
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_API_URL = os.environ.get("GEMINI_API_URL", "https://generativelanguage.googleapis.com/v1beta")
GEMINI_TIMEOUT = int(os.environ.get("GEMINI_TIMEOUT", "45"))
# Минимальная пауза между запросами генерации одного пользователя (секунды)
GENERATE_PAUSE = int(os.environ.get("GENERATE_PAUSE", "10"))

# Ограничения на тест
MAX_QUESTIONS = 20
MIN_OPTIONS = 2
MAX_OPTIONS = 6
