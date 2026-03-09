"""Конфигурация Alembic для автогенерации и применения миграций базы данных."""

import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Добавляем src в путь для импорта моделей
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import DB_USER, DB_NAME, DB_PASS, DB_PORT, DB_HOST

# Импортируем все модели для автогенерации миграций
from models import Base         # Базовый класс
from auth.db import User        # Модель пользователя (fastapi-users)
from links.models import Link, LinkHistory  # Модели ссылок

# Объект конфигурации Alembic
config = context.config

# Подставляем переменные окружения в sqlalchemy.url
section = config.config_ini_section
config.set_section_option(section, "DB_USER", DB_USER)
config.set_section_option(section, "DB_NAME", DB_NAME)
config.set_section_option(section, "DB_PASS", DB_PASS)
config.set_section_option(section, "DB_PORT", DB_PORT)
config.set_section_option(section, "DB_HOST", DB_HOST)

# Настройка логирования из alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Метаданные всех таблиц для автогенерации
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Выполняет миграции в 'offline'-режиме (без подключения к БД).

    Генерирует SQL-скрипт миграции без реального подключения к базе данных.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Выполняет миграции в 'online'-режиме (с активным подключением к БД).

    Создаёт движок SQLAlchemy и применяет миграции через него.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        # NullPool — каждый запрос получает новое соединение (важно для миграций)
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
