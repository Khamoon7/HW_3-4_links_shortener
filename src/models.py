from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовый класс для всех SQLAlchemy-моделей.

    Все таблицы проекта наследуют от этого класса, что позволяет Alembic обнаруживать их при автогенерации миграций.
    """
    pass
