from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import DB_HOST, DB_NAME, DB_PASS, DB_PORT, DB_USER

# URL для asyncpg-драйвера (асинхронное подключение)
DATABASE_URL = (
    f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# Асинхронный движок SQLAlchemy
engine = create_async_engine(DATABASE_URL, echo=False)

# Фабрика сессий - expire_on_commit=False чтобы объекты не сбрасывались после коммита
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Генератор асинхронных сессий для dependency injection в FastAPI.

    Yields:
        AsyncSession: Активная сессия базы данных.
    """
    async with async_session_maker() as session:
        yield session
