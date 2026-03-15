import asyncio
import os
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# URL тестовой БД
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/url_shortener_test",
)

# Учётные данные тестового пользователя
TEST_EMAIL = "testuser@example.com"
TEST_PASSWORD = "Str0ngPass!"


@pytest.fixture(scope="session", autouse=True)
def create_test_tables():
    """Создаёт таблицы через asyncio.run() - синхронная фикстура, нет конфликтов event loop.

    Используем asyncio.run() вместо session-scoped async fixture:
    это позволяет каждому тесту создавать свой async engine в своём event loop,
    избегая ошибки "Future attached to a different loop" от asyncpg.
    """
    # Импорты здесь - чтобы гарантировать регистрацию всех моделей в Base.metadata
    import auth.db  # Регистрирует модель User
    import links.models  # Регистрирует Link и LinkHistory

    from models import Base

    async def _create():
        """Создаёт все таблицы в тестовой БД."""
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    async def _drop():
        """Удаляет все таблицы после завершения сессии."""
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(_create())
    yield
    asyncio.run(_drop())


@pytest.fixture(scope="session", autouse=True)
def override_app_lifespan():
    """Заменяет lifespan приложения: убирает Redis, инициализирует InMemoryBackend.

    Синхронная фикстура - FastAPICache.init() является sync-методом.
    Выполняется один раз на сессию до любого теста.
    """
    from fastapi_cache import FastAPICache
    from fastapi_cache.backends.inmemory import InMemoryBackend

    from main import app

    # Инициализируем кэш in-memory вместо Redis
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")

    @asynccontextmanager
    async def test_lifespan(_):
        """No-op lifespan: не подключается к Redis."""
        yield

    # Заменяем lifespan приложения на тестовый (без Redis)
    app.router.lifespan_context = test_lifespan


@pytest_asyncio.fixture
async def anon_client():
    """HTTP-клиент без авторизации, создаёт собственный async engine для теста.

    Каждый тест получает свой engine в своём event loop - это исключает
    ошибку asyncpg "Future attached to a different loop".

    Yields:
        AsyncClient: Клиент httpx, подключённый к тестовому ASGI-приложению.
    """
    from database import get_async_session
    from main import app

    # Создаём engine в текущем event loop теста
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    test_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session():
        """Генератор сессии для тестовой БД."""
        async with test_maker() as session:
            yield session

    # Подменяем dependency сессии на тестовую БД
    app.dependency_overrides[get_async_session] = override_get_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    # Очищаем overrides и закрываем engine после теста
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def auth_client(anon_client):
    """HTTP-клиент с JWT-токеном в заголовке Authorization.

    Регистрирует тестового пользователя (идемпотентно: 201 или 400) и логинится.

    Args:
        anon_client: Анонимный клиент с тестовой БД.

    Yields:
        AsyncClient: Авторизованный клиент.
    """
    # Регистрируем пользователя: 201 при первом создании, 400 если уже существует
    await anon_client.post(
        "/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )

    # fastapi-users ожидает form-data на /auth/jwt/login, не JSON
    resp = await anon_client.post(
        "/auth/jwt/login",
        data={"username": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"

    token = resp.json()["access_token"]
    anon_client.headers["Authorization"] = f"Bearer {token}"
    yield anon_client
    anon_client.headers.pop("Authorization", None)


@pytest_asyncio.fixture
async def created_link(auth_client):
    """Создаёт тестовую ссылку и возвращает её данные из ответа API.

    Args:
        auth_client: Авторизованный HTTP-клиент.

    Returns:
        dict: Данные созданной ссылки (short_code, short_url, ...).
    """
    resp = await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://example.com/fixture-link"},
    )
    assert resp.status_code == 201, f"Link creation failed: {resp.text}"
    return resp.json()


@pytest_asyncio.fixture
async def db_session():
    """Прямая сессия к тестовой БД для сервисных unit-тестов с реальной БД.

    Создаёт собственный engine в event loop теста.

    Yields:
        AsyncSession: Активная сессия тестовой БД.
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    test_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with test_maker() as session:
        yield session
    await engine.dispose()
