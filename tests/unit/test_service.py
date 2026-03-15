import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from links.schemas import LinkCreate, LinkUpdate
from links.service import (
    _archive_link,
    _generate_unique_code,
    _now_utc,
    create_link,
    get_link_by_code,
    get_link_stats,
)


# _now_utc
def test_now_utc_returns_aware_datetime():
    """_now_utc() возвращает timezone-aware datetime в UTC."""
    dt = _now_utc()
    assert dt.tzinfo is not None
    assert dt.utcoffset().total_seconds() == 0


def test_now_utc_is_close_to_real_time():
    """_now_utc() возвращает время, близкое к реальному UTC."""
    dt = _now_utc()
    now = datetime.now(timezone.utc)
    assert abs((now - dt).total_seconds()) < 2


# _generate_unique_code
@pytest.mark.asyncio
async def test_generate_unique_code_returns_8_chars():
    """Возвращает код длиной 8 символов при отсутствии коллизии."""
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)  # код свободен
    code = await _generate_unique_code(session)
    assert len(code) == 8


@pytest.mark.asyncio
async def test_generate_unique_code_retries_on_collision():
    """Повторяет попытку при занятом коде и возвращает код с 3-й попытки."""
    session = AsyncMock()
    # Первые 2 - коллизия (возвращает существующий UUID), 3-я - свободна (None)
    session.scalar = AsyncMock(side_effect=[uuid.uuid4(), uuid.uuid4(), None])
    code = await _generate_unique_code(session)
    assert code is not None
    assert len(code) == 8
    assert session.scalar.call_count == 3


@pytest.mark.asyncio
async def test_generate_unique_code_raises_503_after_10_attempts():
    """Бросает HTTPException 503 после 10 неудачных попыток."""
    session = AsyncMock()
    # Всегда коллизия
    session.scalar = AsyncMock(return_value=uuid.uuid4())
    with pytest.raises(HTTPException) as exc_info:
        await _generate_unique_code(session)
    assert exc_info.value.status_code == 503
    assert session.scalar.call_count == 10


@pytest.mark.asyncio
async def test_generate_unique_code_custom_length():
    """Генерирует код заданной длины."""
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    code = await _generate_unique_code(session, length=12)
    assert len(code) == 12


# _archive_link
@pytest.mark.asyncio
async def test_archive_link_deactivates_link():
    """_archive_link() устанавливает is_active=False и создаёт запись истории."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    link = MagicMock()
    link.short_code = "testcode"
    link.original_url = "https://example.com"
    link.user_id = None
    link.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    link.click_count = 5
    link.project = "proj"
    link.is_active = True

    await _archive_link(session, link, reason="deleted")

    assert link.is_active is False
    session.add.assert_called_once()
    session.flush.assert_called_once()


# create_link
@pytest.mark.asyncio
async def test_create_link_past_expiry_raises_422():
    """Бросает 422, если expires_at в прошлом."""
    session = AsyncMock()
    data = LinkCreate(
        original_url="https://example.com",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    with pytest.raises(HTTPException) as exc_info:
        await create_link(session, data, user_id=None)
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_create_link_duplicate_alias_raises_409():
    """Бросает 409, если custom_alias уже занят в БД."""
    session = AsyncMock()
    # scalar вернёт UUID - значит alias уже существует
    session.scalar = AsyncMock(return_value=uuid.uuid4())
    data = LinkCreate(original_url="https://example.com", custom_alias="my-alias")
    with pytest.raises(HTTPException) as exc_info:
        await create_link(session, data, user_id=None)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_create_link_with_custom_alias_sets_short_code():
    """При наличии custom_alias - short_code равен alias."""
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)  # alias свободен
    session.add = MagicMock()
    session.commit = AsyncMock()

    # refresh должен заполнить link.id и другие поля
    async def fake_refresh(link):
        link.id = uuid.uuid4()
        link.created_at = datetime.now(timezone.utc)

    session.refresh = fake_refresh

    data = LinkCreate(original_url="https://example.com", custom_alias="my-alias")
    link = await create_link(session, data, user_id=None)
    assert link.short_code == "my-alias"


@pytest.mark.asyncio
async def test_create_link_without_alias_generates_code():
    """Без custom_alias генерируется случайный код длиной 8 символов."""
    session = AsyncMock()
    # Для _generate_unique_code: код свободен
    session.scalar = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def fake_refresh(link):
        link.id = uuid.uuid4()
        link.created_at = datetime.now(timezone.utc)

    session.refresh = fake_refresh

    data = LinkCreate(original_url="https://example.com")
    link = await create_link(session, data, user_id=None)
    assert len(link.short_code) == 8


# get_link_by_code
@pytest.mark.asyncio
async def test_get_link_by_code_not_found_raises_404():
    """Бросает 404, если ссылка не найдена в БД."""
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc_info:
        await get_link_by_code(session, "nonexistent")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_link_by_code_inactive_raises_410():
    """Бросает 410, если ссылка деактивирована (is_active=False)."""
    session = AsyncMock()
    link = MagicMock()
    link.is_active = False
    session.scalar = AsyncMock(return_value=link)
    with pytest.raises(HTTPException) as exc_info:
        await get_link_by_code(session, "inactive")
    assert exc_info.value.status_code == 410


@pytest.mark.asyncio
async def test_get_link_by_code_expired_archives_and_raises_410():
    """Ленивое истечение: архивирует ссылку и бросает 410."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    link = MagicMock()
    link.is_active = True
    link.expires_at = datetime(2020, 1, 1, tzinfo=timezone.utc)  # точно в прошлом
    link.short_code = "expcode"
    link.original_url = "https://expired.com"
    link.user_id = None
    link.created_at = datetime(2019, 1, 1, tzinfo=timezone.utc)
    link.click_count = 0
    link.project = None
    session.scalar = AsyncMock(return_value=link)

    with pytest.raises(HTTPException) as exc_info:
        await get_link_by_code(session, "expcode")
    assert exc_info.value.status_code == 410
    assert link.is_active is False  # ссылка деактивирована


@pytest.mark.asyncio
async def test_get_link_by_code_increments_click_count():
    """Успешный вызов увеличивает click_count на 1."""
    session = AsyncMock()
    session.commit = AsyncMock()

    link = MagicMock()
    link.is_active = True
    link.expires_at = None  # бессрочная
    link.click_count = 5
    session.scalar = AsyncMock(return_value=link)

    result = await get_link_by_code(session, "validcode")
    assert result.click_count == 6


@pytest.mark.asyncio
async def test_get_link_by_code_updates_last_used_at():
    """Успешный вызов обновляет last_used_at."""
    session = AsyncMock()
    session.commit = AsyncMock()

    link = MagicMock()
    link.is_active = True
    link.expires_at = None
    link.click_count = 0
    session.scalar = AsyncMock(return_value=link)

    await get_link_by_code(session, "validcode")
    # last_used_at должен быть установлен (timezone-aware datetime)
    assert link.last_used_at is not None


# get_link_stats
@pytest.mark.asyncio
async def test_get_link_stats_not_found_raises_404():
    """get_link_stats() бросает 404, если ссылка не найдена."""
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc_info:
        await get_link_stats(session, "missing")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_link_stats_returns_link_without_incrementing():
    """get_link_stats() не изменяет click_count."""
    session = AsyncMock()
    link = MagicMock()
    link.click_count = 42
    session.scalar = AsyncMock(return_value=link)

    result = await get_link_stats(session, "anycode")
    assert result.click_count == 42


# LinkCreate - валидаторы схемы
def test_link_create_rejects_reserved_alias_search():
    """Alias 'search' зарезервирован - должна быть ошибка валидации."""
    with pytest.raises(Exception):
        LinkCreate(original_url="https://example.com", custom_alias="search")


def test_link_create_rejects_reserved_alias_top():
    """Alias 'top' зарезервирован - должна быть ошибка валидации."""
    with pytest.raises(Exception):
        LinkCreate(original_url="https://example.com", custom_alias="top")


def test_link_create_rejects_alias_too_short():
    """Alias короче 3 символов - должна быть ошибка валидации."""
    with pytest.raises(Exception):
        LinkCreate(original_url="https://example.com", custom_alias="ab")


def test_link_create_rejects_alias_too_long():
    """Alias длиннее 20 символов - должна быть ошибка валидации."""
    with pytest.raises(Exception):
        LinkCreate(original_url="https://example.com", custom_alias="a" * 21)


def test_link_create_rejects_alias_with_spaces():
    """Alias с пробелами - должна быть ошибка валидации."""
    with pytest.raises(Exception):
        LinkCreate(original_url="https://example.com", custom_alias="my link")


def test_link_create_accepts_valid_alias():
    """Валидный alias с буквами, цифрами, дефисом и подчёркиванием."""
    data = LinkCreate(original_url="https://example.com", custom_alias="my-link_2")
    assert data.custom_alias == "my-link_2"


def test_link_create_expires_at_truncated_to_minute():
    """expires_at усекается до точности минуты (секунды и мкс = 0)."""
    dt = datetime(2030, 6, 1, 12, 30, 45, 123456, tzinfo=timezone.utc)
    data = LinkCreate(original_url="https://example.com", expires_at=dt)
    assert data.expires_at.second == 0
    assert data.expires_at.microsecond == 0


def test_link_create_none_alias_allowed():
    """custom_alias=None - корректный вариант (автогенерация кода)."""
    data = LinkCreate(original_url="https://example.com")
    assert data.custom_alias is None


def test_link_update_expires_at_truncated():
    """LinkUpdate тоже усекает expires_at до минуты."""
    dt = datetime(2030, 1, 1, 0, 0, 59, 999999, tzinfo=timezone.utc)
    data = LinkUpdate(expires_at=dt)
    assert data.expires_at.second == 0
    assert data.expires_at.microsecond == 0
