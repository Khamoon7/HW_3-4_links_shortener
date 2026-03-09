import uuid

from fastapi_users import schemas


class UserRead(schemas.BaseUser[uuid.UUID]):
    """Схема ответа с данными пользователя (без пароля)."""
    pass


class UserCreate(schemas.BaseUserCreate):
    """Схема запроса на регистрацию пользователя (email + password)."""
    pass
