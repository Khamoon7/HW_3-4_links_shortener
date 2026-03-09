import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from links.models import Link, LinkHistory
from links.schemas import LinkCreate, LinkUpdate


def _now_utc() -> datetime:
    """Возвращает текущее UTC-время с информацией о часовом поясе.

    Returns:
        datetime: Текущий момент в UTC.
    """
    return datetime.now(timezone.utc)


async def _generate_unique_code(session: AsyncSession, length: int = 8) -> str:
    """Генерирует уникальный short_code, проверяя отсутствие коллизий в БД.

    Args:
        session: Асинхронная сессия SQLAlchemy.
        length: Длина генерируемого кода (по умолчанию 8 символов).

    Returns:
        str: Уникальный короткий код.

    Raises:
        HTTPException 503: Если не удалось сгенерировать уникальный код за 10 попыток.
    """
    for _ in range(10):
        # Берём первые `length` символов из URL-безопасного токена
        code = secrets.token_urlsafe(length)[:length]
        exists = await session.scalar(select(Link.id).where(Link.short_code == code))
        if not exists:
            return code
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Не удалось сгенерировать уникальный код. Попробуйте позже.",
    )


async def _archive_link(session: AsyncSession, link: Link, reason: str) -> None:
    """Переносит ссылку в таблицу истории и деактивирует её.

    Args:
        session: Асинхронная сессия SQLAlchemy.
        link: ORM-объект ссылки для архивации.
        reason: Причина деактивации ("expired", "deleted", "unused").
    """
    # Добавляем запись в историю
    history_entry = LinkHistory(
        short_code=link.short_code,
        original_url=link.original_url,
        user_id=link.user_id,
        created_at=link.created_at,
        reason=reason,
        click_count=link.click_count,
        project=link.project,
    )
    session.add(history_entry)
    # Деактивируем исходную запись
    link.is_active = False
    await session.flush()


async def create_link(
    session: AsyncSession,
    data: LinkCreate,
    user_id: Optional[uuid.UUID],
) -> Link:
    """Создаёт новую короткую ссылку.

    Если передан custom_alias - проверяет его уникальность.
    Иначе генерирует случайный short_code.

    Args:
        session: Асинхронная сессия SQLAlchemy.
        data: Pydantic-схема с параметрами новой ссылки.
        user_id: UUID пользователя или None для анонимного.

    Returns:
        Link: Созданная ORM-запись.

    Raises:
        HTTPException 409: Если custom_alias уже занят.
        HTTPException 422: Если expires_at в прошлом.
    """
    # Проверяем, что срок истечения не в прошлом
    if data.expires_at and data.expires_at <= _now_utc():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Дата истечения должна быть в будущем.",
        )

    if data.custom_alias:
        # Проверяем уникальность alias
        existing = await session.scalar(
            select(Link.id).where(Link.short_code == data.custom_alias)
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Alias '{data.custom_alias}' уже занят.",
            )
        short_code = data.custom_alias
    else:
        short_code = await _generate_unique_code(session)

    link = Link(
        short_code=short_code,
        original_url=str(data.original_url),
        user_id=user_id,
        expires_at=data.expires_at,
        project=data.project,
    )
    session.add(link)
    await session.commit()
    await session.refresh(link)
    return link


async def get_link_by_code(session: AsyncSession, short_code: str) -> Link:
    """Возвращает активную ссылку по short_code.

    Выполняет ленивую проверку срока истечения: если ссылка истекла - архивирует её и возвращает 410.

    Args:
        session: Асинхронная сессия SQLAlchemy.
        short_code: Короткий код ссылки.

    Returns:
        Link: Активная ORM-запись ссылки.

    Raises:
        HTTPException 404: Если ссылка не найдена.
        HTTPException 410: Если ссылка истекла или была деактивирована.
    """
    link = await session.scalar(select(Link).where(Link.short_code == short_code))

    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка не найдена.")

    # Сначала проверяем is_active - уже архивированная ссылка не должна создавать дубль
    if not link.is_active:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Ссылка была деактивирована.",
        )

    # Ленивая проверка срока истечения (только для активных ссылок)
    if link.expires_at and link.expires_at <= _now_utc():
        await _archive_link(session, link, reason="expired")
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Срок действия ссылки истёк.",
        )

    # Обновляем статистику перехода
    link.click_count += 1
    link.last_used_at = _now_utc()
    await session.commit()

    return link


async def get_link_stats(session: AsyncSession, short_code: str) -> Link:
    """Возвращает ссылку для отображения статистики (без инкремента счётчика).

    Args:
        session: Асинхронная сессия SQLAlchemy.
        short_code: Короткий код ссылки.

    Returns:
        Link: ORM-запись ссылки.

    Raises:
        HTTPException 404: Если ссылка не найдена.
    """
    link = await session.scalar(select(Link).where(Link.short_code == short_code))
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка не найдена.")
    return link


async def update_link(
    session: AsyncSession,
    short_code: str,
    data: LinkUpdate,
    user_id: uuid.UUID,
) -> Link:
    """Обновляет данные ссылки (только владелец).

    Можно изменить original_url, expires_at, project.

    Args:
        session: Асинхронная сессия SQLAlchemy.
        short_code: Короткий код ссылки.
        data: Pydantic-схема с обновляемыми полями.
        user_id: UUID текущего пользователя.

    Returns:
        Link: Обновлённая ORM-запись.

    Raises:
        HTTPException 404: Если ссылка не найдена.
        HTTPException 403: Если пользователь не является владельцем.
    """
    link = await session.scalar(
        select(Link).where(Link.short_code == short_code, Link.is_active == True)
    )
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка не найдена.")
    if link.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет прав на изменение этой ссылки.",
        )

    # Применяем только переданные (не None) поля
    if data.original_url is not None:
        link.original_url = str(data.original_url)
    if data.expires_at is not None:
        # Проверяем, что новый срок истечения не в прошлом
        if data.expires_at <= _now_utc():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Дата истечения должна быть в будущем.",
            )
        link.expires_at = data.expires_at
    if data.project is not None:
        link.project = data.project

    await session.commit()
    await session.refresh(link)
    return link


async def delete_link(
    session: AsyncSession,
    short_code: str,
    user_id: uuid.UUID,
) -> None:
    """Удаляет (архивирует) ссылку - переводит в историю с причиной "deleted".

    Args:
        session: Асинхронная сессия SQLAlchemy.
        short_code: Короткий код ссылки.
        user_id: UUID текущего пользователя.

    Raises:
        HTTPException 404: Если ссылка не найдена.
        HTTPException 403: Если пользователь не является владельцем.
    """
    link = await session.scalar(
        select(Link).where(Link.short_code == short_code, Link.is_active == True)
    )
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка не найдена.")
    if link.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет прав на удаление этой ссылки.",
        )

    await _archive_link(session, link, reason="deleted")
    await session.commit()


async def search_links(
    session: AsyncSession,
    original_url: str,
    skip: int = 0,
    limit: int = 20,
) -> list[Link]:
    """Ищет активные ссылки по оригинальному URL (поиск по подстроке).

    Args:
        session: Асинхронная сессия SQLAlchemy.
        original_url: URL или его часть для поиска.
        skip: Смещение для пагинации.
        limit: Максимальное количество результатов.

    Returns:
        list[Link]: Список найденных активных ссылок.
    """
    result = await session.scalars(
        select(Link)
        .where(Link.original_url.ilike(f"%{original_url}%"), Link.is_active == True)
        .offset(skip)
        .limit(limit)
    )
    return list(result.all())


async def get_expired_history(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 50,
) -> list[LinkHistory]:
    """Возвращает историю деактивированных ссылок (все причины).

    Args:
        session: Асинхронная сессия SQLAlchemy.
        skip: Смещение для пагинации.
        limit: Максимальное количество результатов.

    Returns:
        list[LinkHistory]: Список записей истории, отсортированных по дате деактивации.
    """
    result = await session.scalars(
        select(LinkHistory)
        .order_by(LinkHistory.deactivated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.all())


async def cleanup_unused_links(
    session: AsyncSession,
    days: int,
    user_id: uuid.UUID,
) -> int:
    """Удаляет неиспользуемые ссылки текущего пользователя, переводя их в историю.

    Критерий неиспользуемости: last_used_at < (now - days) или (last_used_at is NULL AND created_at < (now - days)).

    Args:
        session: Асинхронная сессия SQLAlchemy.
        days: Порог неактивности в днях.
        user_id: UUID пользователя - удаляются только его ссылки.

    Returns:
        int: Количество удалённых ссылок.
    """
    threshold = _now_utc() - timedelta(days=days)

    # Находим кандидаты на удаление - только ссылки текущего пользователя
    result = await session.scalars(
        select(Link).where(
            Link.user_id == user_id,
            Link.is_active == True,
            # Ссылка не имеет переходов вообще, либо последний переход давно
            (
                (Link.last_used_at < threshold)
                | (Link.last_used_at.is_(None) & (Link.created_at < threshold))
            ),
        )
    )
    links = list(result.all())

    # Архивируем каждую
    for link in links:
        await _archive_link(session, link, reason="unused")

    await session.commit()
    return len(links)


async def get_user_links(
    session: AsyncSession,
    user_id: uuid.UUID,
    project: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
) -> list[Link]:
    """Возвращает все активные ссылки пользователя с опциональной фильтрацией по проекту.

    Args:
        session: Асинхронная сессия SQLAlchemy.
        user_id: UUID пользователя.
        project: Фильтр по проекту (опционально).
        skip: Смещение для пагинации.
        limit: Максимальное количество результатов.

    Returns:
        list[Link]: Список активных ссылок пользователя.
    """
    query = select(Link).where(Link.user_id == user_id, Link.is_active == True)
    if project:
        query = query.where(Link.project == project)
    query = query.order_by(Link.created_at.desc()).offset(skip).limit(limit)

    result = await session.scalars(query)
    return list(result.all())


async def get_top_links(
    session: AsyncSession,
    limit: int = 10,
) -> list[Link]:
    """Возвращает топ активных ссылок по количеству переходов.

    Args:
        session: Асинхронная сессия SQLAlchemy.
        limit: Количество ссылок в топе (по умолчанию 10).

    Returns:
        list[Link]: Список ссылок, отсортированных по убыванию click_count.
    """
    result = await session.scalars(
        select(Link)
        .where(Link.is_active == True)
        .order_by(Link.click_count.desc())
        .limit(limit)
    )
    return list(result.all())


async def get_project_stats(
    session: AsyncSession,
    project: str,
    user_id: uuid.UUID,
) -> dict:
    """Вычисляет агрегированную статистику по всем активным ссылкам проекта.

    Args:
        session: Асинхронная сессия SQLAlchemy.
        project: Название проекта.
        user_id: UUID пользователя (владельца).

    Returns:
        dict: Словарь со статистикой проекта.

    Raises:
        HTTPException 404: Если проект не найден или не принадлежит пользователю.
    """
    # Агрегируем: общее число ссылок, суммарные клики
    row = await session.execute(
        select(
            func.count(Link.id).label("total_links"),
            func.coalesce(func.sum(Link.click_count), 0).label("total_clicks"),
        ).where(Link.user_id == user_id, Link.project == project, Link.is_active == True)
    )
    agg = row.one()

    if agg.total_links == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Проект '{project}' не найден.",
        )

    # Находим самую популярную ссылку
    top = await session.scalar(
        select(Link)
        .where(Link.user_id == user_id, Link.project == project, Link.is_active == True)
        .order_by(Link.click_count.desc())
        .limit(1)
    )

    return {
        "project": project,
        "total_links": agg.total_links,
        "total_clicks": int(agg.total_clicks),
        "avg_clicks": round(int(agg.total_clicks) / agg.total_links, 2),
        "top_link": top.short_code if top else None,
        "top_link_clicks": top.click_count if top else 0,
    }


async def expire_old_links(session: AsyncSession) -> int:
    """Фоновая задача: архивирует все ссылки с истёкшим сроком действия.

    Вызывается периодически из lifespan-задачи в main.py.

    Args:
        session: Асинхронная сессия SQLAlchemy.

    Returns:
        int: Количество архивированных ссылок.
    """
    now = _now_utc()
    result = await session.scalars(
        select(Link).where(
            Link.is_active == True,
            Link.expires_at.isnot(None),
            Link.expires_at <= now,
        )
    )
    links = list(result.all())

    for link in links:
        await _archive_link(session, link, reason="expired")

    if links:
        await session.commit()
        # Инвалидируем кэш: архивированные ссылки не должны появляться в search/top
        from fastapi_cache import FastAPICache
        await FastAPICache.clear(namespace="links")

    return len(links)
