import io
from typing import Optional

import qrcode
from fastapi import APIRouter, Depends, Query, status

from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi_cache import FastAPICache
from fastapi_cache.decorator import cache
from sqlalchemy.ext.asyncio import AsyncSession

from auth.db import User
from auth.users import current_active_user, current_user_optional
from config import BASE_URL
from database import get_async_session
from links import service
from links.schemas import (
    CleanupResponse,
    LinkCreate,
    LinkHistoryResponse,
    LinkResponse,
    LinkStats,
    LinkUpdate,
    ProjectStats,
)

# Префикс /links - все эндпоинты работы со ссылками
router = APIRouter(prefix="/links", tags=["Ссылки"])


def _links_key_builder(func, namespace="", request=None, response=None, args=(), kwargs=None):
    """Строит ключ кэша, исключая объект AsyncSession из kwargs.

    Стандартный key_builder включает все аргументы функции в ключ, в том числе объект AsyncSession - он уникален для каждого запроса, что делает кэш бесполезным.
    Этот builder фильтрует session и оставляет только значимые параметры.

    Args:
        func: Кэшируемая функция.
        namespace: Пространство имён кэша.
        request: HTTP-запрос (не используется).
        response: HTTP-ответ (не используется).
        args: Позиционные аргументы функции.
        kwargs: Именованные аргументы функции.

    Returns:
        str: Строковый ключ кэша.
    """

    if kwargs is None:
        kwargs = {}

    # Исключаем AsyncSession - уникальный объект, ломающий кэш
    filtered = {k: v for k, v in kwargs.items() if not isinstance(v, AsyncSession)}
    # Namespace уже содержит префикс (например, "fastapi-cache:links") из декоратора @cache.
    return f"{namespace}:{func.__module__}:{func.__qualname__}:{args}:{filtered}"


def _to_response(link) -> LinkResponse:
    """Конвертирует ORM-объект Link в схему ответа LinkResponse.

    Args:
        link: ORM-объект Link.

    Returns:
        LinkResponse: Pydantic-схема с данными ссылки.
    """
    return LinkResponse(
        id=link.id,
        short_code=link.short_code,
        short_url=f"{BASE_URL}/links/{link.short_code}",
        original_url=link.original_url,
        created_at=link.created_at,
        expires_at=link.expires_at,
        project=link.project,
        is_active=link.is_active,
    )


# Статичные маршруты
@router.get(
    "/",
    response_model=list[LinkResponse],
    summary="Мои ссылки",
)
async def my_links(
    project: Optional[str] = Query(None, description="Фильтр по проекту"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Возвращает все активные ссылки текущего пользователя с пагинацией.

    Поддерживает фильтрацию по названию проекта. Требует авторизации.

    Args:
        project: Название проекта для фильтрации (опционально).
        skip: Смещение пагинации.
        limit: Максимальное количество результатов.
        session: Сессия БД.
        user: Текущий аутентифицированный пользователь.

    Returns:
        list[LinkResponse]: Список ссылок пользователя.
    """
    links = await service.get_user_links(session, user.id, project, skip, limit)
    return [_to_response(link) for link in links]


@router.post(
    "/shorten",
    response_model=LinkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать короткую ссылку",
)
async def shorten_link(
    data: LinkCreate,
    session: AsyncSession = Depends(get_async_session),
    user: Optional[User] = Depends(current_user_optional),
):
    """Создаёт короткую ссылку для оригинального URL.

    Доступно всем пользователям (включая анонимных). Поддерживает кастомный alias, срок жизни и группировку по проекту.

    Args:
        data: Параметры создаваемой ссылки.
        session: Сессия БД.
        user: Текущий пользователь (None для анонимного).

    Returns:
        LinkResponse: Данные созданной ссылки.
    """

    # Для анонимных пользователей user_id = None
    user_id = user.id if user else None
    link = await service.create_link(session, data, user_id)
    # Инвалидируем кэш: новая ссылка должна появиться в search/top
    await FastAPICache.clear(namespace="links")
    return _to_response(link)


@router.get(
    "/search",
    response_model=list[LinkResponse],
    summary="Поиск ссылок по оригинальному URL",
)
@cache(expire=30, namespace="links", key_builder=_links_key_builder)
async def search_links(
    original_url: str = Query(..., description="URL или его часть для поиска"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
):
    """Ищет активные ссылки по подстроке оригинального URL (без учёта регистра).

    Доступно всем пользователям. Результат кэшируется на 30 секунд.

    Args:
        original_url: URL или его часть для поиска.
        skip: Смещение пагинации.
        limit: Максимальное количество результатов.
        session: Сессия БД.

    Returns:
        list[LinkResponse]: Список найденных ссылок.
    """
    links = await service.search_links(session, original_url, skip, limit)
    return [_to_response(link) for link in links]


@router.get(
    "/top",
    response_model=list[LinkResponse],
    summary="Топ ссылок по переходам",
)
@cache(expire=60, namespace="links", key_builder=_links_key_builder)
async def top_links(
    limit: int = Query(10, ge=1, le=50, description="Количество ссылок в топе"),
    session: AsyncSession = Depends(get_async_session),
):
    """Возвращает топ активных ссылок по количеству переходов.

    Публичный эндпоинт. Результат кэшируется на 60 секунд.

    Args:
        limit: Количество позиций в рейтинге.
        session: Сессия БД.

    Returns:
        list[LinkResponse]: Список ссылок, отсортированных по убыванию переходов.
    """
    links = await service.get_top_links(session, limit)
    return [_to_response(link) for link in links]


@router.get(
    "/history/expired",
    response_model=list[LinkHistoryResponse],
    summary="История деактивированных ссылок",
)
async def expired_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_async_session),
):
    """Возвращает историю всех деактивированных ссылок (истёкших, удалённых, неиспользуемых).

    Записи отсортированы по дате деактивации (свежие - первые).
    Доступно всем пользователям.

    Args:
        skip: Смещение пагинации.
        limit: Максимальное количество результатов.
        session: Сессия БД.

    Returns:
        list[LinkHistoryResponse]: Список записей истории.
    """
    return await service.get_expired_history(session, skip, limit)


@router.delete(
    "/cleanup",
    response_model=CleanupResponse,
    summary="Удалить неиспользуемые ссылки",
)
async def cleanup_unused(
    days: int = Query(30, ge=1, description="Порог неактивности в днях"),
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Удаляет ссылки, не использованные в течение указанного числа дней.

    Требует авторизации. Ссылки переносятся в историю с причиной "unused".

    Args:
        days: Порог неактивности в днях.
        session: Сессия БД.
        user: Текущий аутентифицированный пользователь.

    Returns:
        CleanupResponse: Количество удалённых ссылок и использованный порог.
    """
    deleted_count = await service.cleanup_unused_links(session, days, user.id)
    # Инвалидируем кэш: удалённые ссылки не должны появляться в search/top
    await FastAPICache.clear(namespace="links")
    return CleanupResponse(deleted_count=deleted_count, days=days)


@router.get(
    "/projects/{project}/stats",
    response_model=ProjectStats,
    summary="Статистика по проекту",
)
async def project_stats(
    project: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Возвращает агрегированную статистику по всем активным ссылкам проекта.

    Требует авторизации. Отображает суммарные переходы, среднее и топ-ссылку.

    Args:
        project: Название проекта.
        session: Сессия БД.
        user: Текущий аутентифицированный пользователь.

    Returns:
        ProjectStats: Агрегированная статистика проекта.
    """
    return await service.get_project_stats(session, project=project, user_id=user.id)


# Динамические маршруты с {short_code}
@router.get(
    "/{short_code}",
    summary="Перейти по короткой ссылке",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    response_class=RedirectResponse,
)
async def redirect_to_original(
    short_code: str,
    session: AsyncSession = Depends(get_async_session),
):
    """Перенаправляет на оригинальный URL по короткому коду.

    Инкрементирует счётчик переходов и обновляет last_used_at при каждом вызове. При истечении срока ссылки возвращает 410 Gone.

    Кэш не применяется намеренно: каждый переход должен учитываться в статистике. Для кэширования информации о ссылке используется /stats (кэш 30 сек).

    Args:
        short_code: Короткий код ссылки.
        session: Сессия БД.

    Returns:
        RedirectResponse: Редирект 307 на оригинальный URL.
    """
    link = await service.get_link_by_code(session, short_code)
    return RedirectResponse(url=link.original_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get(
    "/{short_code}/stats",
    response_model=LinkStats,
    summary="Статистика по короткой ссылке",
)
@cache(expire=30, namespace="links", key_builder=_links_key_builder)
async def link_stats(
    short_code: str,
    session: AsyncSession = Depends(get_async_session),
):
    """Возвращает статистику по ссылке: оригинальный URL, даты, счётчик переходов.

    Доступно всем пользователям. Результат кэшируется на 30 секунд.

    Args:
        short_code: Короткий код ссылки.
        session: Сессия БД.

    Returns:
        LinkStats: Статистика ссылки.
    """
    return await service.get_link_stats(session, short_code)


@router.put(
    "/{short_code}",
    response_model=LinkResponse,
    summary="Обновить ссылку",
)
async def update_link(
    short_code: str,
    data: LinkUpdate,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Обновляет оригинальный URL, срок истечения или проект ссылки.

    Требует авторизации. Только владелец ссылки может её изменить. Инвалидирует кэш после обновления.

    Args:
        short_code: Короткий код ссылки.
        data: Обновляемые поля (все опциональны).
        session: Сессия БД.
        user: Текущий аутентифицированный пользователь.

    Returns:
        LinkResponse: Обновлённые данные ссылки.
    """
    link = await service.update_link(session, short_code, data, user.id)
    # Инвалидируем весь кэш namespace="links" после изменения
    await FastAPICache.clear(namespace="links")
    return _to_response(link)


@router.delete(
    "/{short_code}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить ссылку",
)
async def delete_link(
    short_code: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Удаляет короткую ссылку (переводит в историю с причиной "deleted").

    Требует авторизации. Только владелец ссылки может её удалить. Инвалидирует кэш после удаления.

    Args:
        short_code: Короткий код ссылки.
        session: Сессия БД.
        user: Текущий аутентифицированный пользователь.
    """
    await service.delete_link(session, short_code, user.id)
    # Инвалидируем кэш
    await FastAPICache.clear(namespace="links")


@router.get(
    "/{short_code}/qr",
    summary="QR-код для короткой ссылки",
    response_class=StreamingResponse,
)
async def link_qr_code(
    short_code: str,
    session: AsyncSession = Depends(get_async_session),
):
    """Генерирует QR-код для короткой ссылки и возвращает его как PNG-изображение.

    Доступно всем пользователям. QR-код кодирует полный короткий URL.

    Args:
        short_code: Короткий код ссылки.
        session: Сессия БД.

    Returns:
        StreamingResponse: PNG-изображение QR-кода.
    """
    # Проверяем, что ссылка существует и активна (QR только для рабочих ссылок)
    link = await service.get_link_stats(session, short_code)
    if not link.is_active:
        from fastapi import HTTPException
        raise HTTPException(status_code=410, detail="Ссылка деактивирована.")

    # Генерируем QR-код для полного короткого URL (включая /links/ префикс)
    short_url = f"{BASE_URL}/links/{short_code}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(short_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    # Сохраняем PNG в буфер памяти и отдаём как поток
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="image/png",
        headers={"Content-Disposition": f"inline; filename={short_code}.png"},
    )
