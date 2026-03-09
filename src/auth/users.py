import uuid
from typing import Optional

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, models
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase

from auth.db import User, get_user_db
from config import SECRET


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    """Менеджер пользователей  обрабатывает события регистрации и сброса пароля.

    Attributes:
        reset_password_token_secret: Секрет для токена сброса пароля.
        verification_token_secret: Секрет для токена верификации email.
    """

    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        """Вызывается после успешной регистрации пользователя.

        Args:
            user: Зарегистрированный пользователь.
            request: HTTP-запрос (опционально).
        """
        print(f"Пользователь {user.id} зарегистрирован.")

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        """Вызывается при запросе сброса пароля.

        Args:
            user: Пользователь, запросивший сброс.
            token: Токен сброса пароля.
            request: HTTP-запрос (опционально).
        """
        print(f"Пользователь {user.id} запросил сброс пароля. Токен: {token}")


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    """Dependency: создаёт экземпляр UserManager для обработки запросов.

    Args:
        user_db: Адаптер базы данных пользователей.

    Yields:
        UserManager: Менеджер пользователей.
    """
    yield UserManager(user_db)


# Транспорт Bearer-токен в заголовке Authorization
bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy[models.UP, models.ID]:
    """Возвращает стратегию JWT с настроенным секретом и временем жизни токена.

    Returns:
        JWTStrategy: Стратегия аутентификации через JWT.
    """
    # Токен действителен 1 час (3600 секунд)
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)


# Бэкенд аутентификации (JWT + Bearer)
auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# Основной объект fastapi-users
fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

# Dependency для получения текущего активного пользователя (обязательная авторизация)
current_active_user = fastapi_users.current_user(active=True)

# Dependency для получения текущего пользователя (опциональная авторизация  None для анонимов)
current_user_optional = fastapi_users.current_user(active=True, optional=True)
