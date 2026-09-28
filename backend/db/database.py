from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from backend.core.config import get_settings

def _get_async_url_and_args() -> tuple[str, dict]:
    url = get_settings().DATABASE_URL.strip()
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    if "?" in url:
        url = url.split("?")[0]
    connect_args = {}
    if "neon.tech" in url or "render.com" in url or "aws" in url:
        connect_args["ssl"] = "require"
    return url, connect_args


_url, _args = _get_async_url_and_args()
engine = create_async_engine(_url, connect_args=_args, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session():
    async with SessionLocal() as s:
        yield s
