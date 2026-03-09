import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from redis import asyncio as aioredis

from auth.schemas import UserCreate, UserRead
from auth.users import auth_backend, fastapi_users
from config import REDIS_HOST, REDIS_PORT
from database import async_session_maker
from links.router import router as links_router

logger = logging.getLogger(__name__)


async def _cleanup_expired_loop() -> None:
    """Бесконечный цикл фоновой задачи: удаляет истёкшие ссылки каждые 30 минут.

    Запускается при старте приложения через asyncio.create_task.
    При возникновении ошибки - логирует и продолжает работу.
    """
    from links.service import expire_old_links

    while True:
        try:
            async with async_session_maker() as session:
                count = await expire_old_links(session)
                if count:
                    logger.info(f"Фоновая задача: архивировано истёкших ссылок - {count}")
        except Exception as exc:
            logger.error(f"Ошибка фоновой очистки ссылок: {exc}")
        # Ждём 30 минут перед следующей проверкой
        await asyncio.sleep(30 * 60)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Управляет жизненным циклом приложения: старт и завершение.

    При старте:
    - Подключается к Redis и инициализирует кэш
    - Запускает фоновую задачу очистки истёкших ссылок

    При завершении:
    - Отменяет фоновую задачу

    Args:
        _: Экземпляр FastAPI (не используется напрямую).

    Yields:
        None: Управление передаётся приложению.
    """
    # Инициализация Redis-кэша
    redis_url = f"redis://{REDIS_HOST}:{REDIS_PORT}"
    redis = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=False)
    FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")
    logger.info(f"Redis-кэш подключён: {redis_url}")

    # Запуск фоновой задачи очистки истёкших ссылок
    cleanup_task = asyncio.create_task(_cleanup_expired_loop())
    logger.info("Фоновая задача очистки ссылок запущена.")

    yield

    # Отменяем фоновую задачу при завершении
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("Приложение завершено.")


# Создание экземпляра FastAPI
app = FastAPI(
    title="URL Shortener API",
    description=(
        "Сервис сокращения ссылок на FastAPI. "
        "Поддерживает JWT-аутентификацию, кастомные alias, "
        "Redis-кэширование и группировку по проектам."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS - разрешаем все источники (для разработки и Swagger UI)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Роутеры аутентификации от fastapi-users
app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["Аутентификация"],
)
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["Аутентификация"],
)

# Роутер ссылок
app.include_router(links_router)


@app.get("/", tags=["Общее"], summary="Корень API")
async def root():
    """Возвращает приветственное сообщение и ссылку на документацию.

    Returns:
        dict: Базовая информация о сервисе.
    """
    return {
        "service": "URL Shortener API",
        "version": "1.0.0",
        "docs": "/docs",
    }


if __name__ == "__main__":
    uvicorn.run("main:app", reload=True, host="0.0.0.0", port=8000, log_level="info")
