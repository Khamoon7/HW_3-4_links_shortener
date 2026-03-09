from fastapi import Depends
from fastapi_users.db import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_async_session
from models import Base


class User(SQLAlchemyBaseUserTableUUID, Base):
    """ORM-модель пользователя.

    Наследует стандартные поля fastapi-users (UUID id, email, hashed_password, is_active, is_superuser, is_verified) и базовый класс Base для Alembic.
    """
    pass


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    """Dependency: возвращает адаптер базы данных пользователей для fastapi-users.

    Args:
        session: Асинхронная сессия SQLAlchemy.

    Yields:
        SQLAlchemyUserDatabase: Адаптер для работы с таблицей пользователей.
    """
    yield SQLAlchemyUserDatabase(session, User)
