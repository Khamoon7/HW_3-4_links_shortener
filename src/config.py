import os
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

# Параметры подключения к PostgreSQL
DB_USER: str = os.getenv("DB_USER", "postgres")
DB_PASS: str = os.getenv("DB_PASS", "postgres")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: str = os.getenv("DB_PORT", "5432")
DB_NAME: str = os.getenv("DB_NAME", "url_shortener")

# Параметры Redis
REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT: str = os.getenv("REDIS_PORT", "6379")

# Секрет для JWT-токенов
SECRET: str = os.getenv("SECRET", "change_me_in_production")

# Базовый URL сервиса (используется при отображении коротких ссылок)
BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")
