import uuid
from datetime import datetime
from typing import Optional

from pydantic import AwareDatetime, BaseModel, HttpUrl, field_validator


class LinkCreate(BaseModel):
    """Схема запроса на создание короткой ссылки.

    Attributes:
        original_url: Оригинальный длинный URL.
        custom_alias: Кастомный короткий код (опционально).
        expires_at: Дата истечения ссылки в UTC (опционально).
        project: Название проекта для группировки (опционально).
    """

    original_url: HttpUrl
    custom_alias: Optional[str] = None
    expires_at: Optional[AwareDatetime] = None
    project: Optional[str] = None

    @field_validator("expires_at")
    @classmethod
    def truncate_expires_at(cls, value: Optional[AwareDatetime]) -> Optional[AwareDatetime]:
        """Обрезает expires_at до точности в минуту (секунды и микросекунды обнуляются).

        Args:
            value: Дата истечения или None.

        Returns:
            AwareDatetime с нулевыми секундами и микросекундами, или None.
        """
        if value is None:
            return value
        return value.replace(second=0, microsecond=0)

    @field_validator("custom_alias")
    @classmethod
    def validate_alias(cls, value: Optional[str]) -> Optional[str]:
        """Валидирует кастомный alias: только буквы, цифры и дефис, длина 3–20 символов.

        Запрещены зарезервированные пути API: search, top, shorten и др.

        Args:
            value: Строка alias.

        Returns:
            Очищенный alias или None.

        Raises:
            ValueError: Если alias не соответствует требованиям.
        """
        # Зарезервированные пути - пересекаются со статичными GET-маршрутами /links/
        _RESERVED = {"search", "top", "shorten", "history", "cleanup", "projects"}
        if value is None:
            return value
        value = value.strip()
        if not (3 <= len(value) <= 20):
            raise ValueError("Alias должен содержать от 3 до 20 символов.")
        if not value.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Alias может содержать только буквы, цифры, дефис и подчёркивание.")
        if value.lower() in _RESERVED:
            raise ValueError(f"Alias '{value}' зарезервирован системой.")
        return value


class LinkUpdate(BaseModel):
    """Схема запроса на обновление ссылки.

    Attributes:
        original_url: Новый оригинальный URL (опционально).
        expires_at: Новая дата истечения (опционально).
        project: Новый проект (опционально).
    """

    original_url: Optional[HttpUrl] = None
    expires_at: Optional[AwareDatetime] = None
    project: Optional[str] = None

    @field_validator("expires_at")
    @classmethod
    def truncate_expires_at(cls, value: Optional[AwareDatetime]) -> Optional[AwareDatetime]:
        """Обрезает expires_at до точности в минуту (секунды и микросекунды обнуляются).

        Args:
            value: Дата истечения или None.

        Returns:
            AwareDatetime с нулевыми секундами и микросекундами, или None.
        """
        if value is None:
            return value
        return value.replace(second=0, microsecond=0)


class LinkResponse(BaseModel):
    """Схема ответа с данными о созданной или обновлённой короткой ссылке.

    Attributes:
        id: UUID ссылки.
        short_code: Короткий код.
        short_url: Полный короткий URL (BASE_URL + short_code).
        original_url: Оригинальный URL.
        created_at: Дата создания.
        expires_at: Дата истечения.
        project: Проект.
        is_active: Активна ли ссылка.
    """

    id: uuid.UUID
    short_code: str
    short_url: str
    original_url: str
    created_at: datetime
    expires_at: Optional[datetime]
    project: Optional[str]
    is_active: bool

    model_config = {"from_attributes": True}


class LinkStats(BaseModel):
    """Схема ответа со статистикой по короткой ссылке.

    Attributes:
        short_code: Короткий код.
        original_url: Оригинальный URL.
        created_at: Дата создания.
        expires_at: Дата истечения.
        click_count: Количество переходов.
        last_used_at: Дата последнего перехода.
        project: Проект.
        is_active: Активна ли ссылка.
    """

    short_code: str
    original_url: str
    created_at: datetime
    expires_at: Optional[datetime]
    click_count: int
    last_used_at: Optional[datetime]
    project: Optional[str]
    is_active: bool

    model_config = {"from_attributes": True}


class LinkHistoryResponse(BaseModel):
    """Схема ответа с записью из истории деактивированных ссылок.

    Attributes:
        short_code: Бывший короткий код.
        original_url: Оригинальный URL.
        created_at: Дата создания ссылки.
        deactivated_at: Дата деактивации.
        reason: Причина: "expired" / "deleted" / "unused".
        click_count: Итоговое количество переходов.
        project: Проект.
    """

    short_code: str
    original_url: str
    created_at: datetime
    deactivated_at: datetime
    reason: str
    click_count: int
    project: Optional[str]

    model_config = {"from_attributes": True}


class ProjectStats(BaseModel):
    """Схема ответа с агрегированной статистикой по проекту.

    Attributes:
        project: Название проекта.
        total_links: Общее количество активных ссылок.
        total_clicks: Суммарное количество переходов.
        avg_clicks: Среднее количество переходов на ссылку.
        top_link: Короткий код самой популярной ссылки.
        top_link_clicks: Количество переходов по самой популярной ссылке.
    """

    project: str
    total_links: int
    total_clicks: int
    avg_clicks: float
    top_link: Optional[str]
    top_link_clicks: int


class CleanupResponse(BaseModel):
    """Схема ответа после очистки неиспользуемых ссылок.

    Attributes:
        deleted_count: Количество удалённых ссылок.
        days: Порог неактивности в днях.
    """

    deleted_count: int
    days: int
