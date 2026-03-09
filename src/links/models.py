import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models import Base


class Link(Base):
    """Таблица коротких ссылок.

    Хранит основную информацию о ссылке: оригинальный URL, короткий код, статистику переходов, время жизни и принадлежность проекту.

    Attributes:
        id: Уникальный UUID идентификатор.
        short_code: Короткий код (генерируется автоматически или задаётся пользователем).
        original_url: Оригинальный длинный URL.
        user_id: UUID владельца (None для анонимных пользователей).
        created_at: Дата и время создания ссылки.
        expires_at: Дата и время истечения ссылки (None - бессрочная).
        last_used_at: Дата и время последнего перехода.
        click_count: Количество переходов по ссылке.
        is_active: Флаг активности (False - ссылка деактивирована).
        project: Название проекта для группировки ссылок.
    """

    __tablename__ = "links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    short_code: Mapped[str] = mapped_column(
        String(20), unique=True, index=True, nullable=False
    )
    original_url: Mapped[str] = mapped_column(Text, nullable=False)  
    # Внешний ключ на пользователя; nullable - анонимные пользователи не авторизованы
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Счётчик переходов - обновляется при каждом GET /{short_code}
    click_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    project: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )


class LinkHistory(Base):
    """Таблица истории деактивированных ссылок.

    Записи создаются при удалении, истечении срока или очистке неиспользуемых ссылок. Позволяет просматривать аналитику по истёкшим ссылкам.

    Attributes:
        id: Уникальный UUID идентификатор записи.
        short_code: Короткий код удалённой ссылки.
        original_url: Оригинальный URL.
        user_id: UUID бывшего владельца (None для анонимных).
        created_at: Дата создания ссылки.
        deactivated_at: Дата деактивации ссылки.
        reason: Причина деактивации: "expired", "deleted", "unused".
        click_count: Итоговое количество переходов.
        project: Проект, к которому принадлежала ссылка.
    """

    __tablename__ = "link_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    short_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deactivated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Причина деактивации - одно из трёх значений
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    click_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    project: Mapped[str | None] = mapped_column(String(100), nullable=True)
