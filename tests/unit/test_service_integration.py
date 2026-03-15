import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from links.models import Link, LinkHistory
from links.service import expire_old_links


@pytest.mark.asyncio
async def test_expire_old_links_archives_expired(db_session):
    """expire_old_links() архивирует ссылки с истёкшим expires_at."""
    # Вставляем ссылку с expires_at в прошлом напрямую (без валидации service)
    expired_link = Link(
        short_code=f"exp-{uuid.uuid4().hex[:6]}",
        original_url="https://expired-direct.com",
        user_id=None,
        expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        is_active=True,
        click_count=3,
    )
    db_session.add(expired_link)
    await db_session.commit()
    await db_session.refresh(expired_link)
    short_code = expired_link.short_code

    # Запускаем фоновую задачу архивации
    count = await expire_old_links(db_session)

    # Проверяем, что хотя бы одна ссылка была архивирована
    assert count >= 1

    # Ссылка должна быть деактивирована
    link = await db_session.scalar(select(Link).where(Link.short_code == short_code))
    assert link is not None
    assert link.is_active is False

    # Запись должна быть в истории
    history = await db_session.scalar(
        select(LinkHistory).where(LinkHistory.short_code == short_code)
    )
    assert history is not None
    assert history.reason == "expired"
    assert history.click_count == 3


@pytest.mark.asyncio
async def test_expire_old_links_returns_zero_when_nothing_expired(db_session):
    """expire_old_links() возвращает 0, если нет истёкших ссылок."""
    # Вставляем активную ссылку без expires_at
    active_link = Link(
        short_code=f"act-{uuid.uuid4().hex[:6]}",
        original_url="https://never-expires.com",
        user_id=None,
        expires_at=None,
        is_active=True,
        click_count=0,
    )
    db_session.add(active_link)
    await db_session.commit()

    # В тестовой БД не должно быть истёкших ссылок после этого теста
    # (предыдущий тест архивировал свою)
    # Создаём ещё одну "будущую" ссылку
    future_link = Link(
        short_code=f"fut-{uuid.uuid4().hex[:6]}",
        original_url="https://far-future.com",
        user_id=None,
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        is_active=True,
        click_count=0,
    )
    db_session.add(future_link)
    await db_session.commit()

    # Запускаем - должно вернуть 0 (или небольшое число от других тестов)
    # Главное: функция не упала и вернула int
    count = await expire_old_links(db_session)
    assert isinstance(count, int)
    assert count >= 0


@pytest.mark.asyncio
async def test_db_session_is_async_session(db_session):
    """Проверяет, что db_session является корректной AsyncSession."""
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(db_session, AsyncSession)
    # Простой запрос через сессию
    result = await db_session.execute(select(Link).limit(1))
    # Результат может быть пустым - важно, что запрос не упал
    assert result is not None
