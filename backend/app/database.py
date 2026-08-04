"""Database engine and session management."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.database.url,
    echo=False,
    future=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """Dependency: get async database session.

    客户端中途断连（SSE 长流如辩论/对话）会触发 ASGI 取消请求任务，抛
    CancelledError（BaseException 子类，不被 except Exception 捕获）。若此时
    session 处于 flush 中途会进入 rollback-pending，依赖 finally 的 commit 会
    抛 PendingRollbackError，rollback 又可能撞"no active connection"二次刷屏。
    此处捕获 BaseException（含 CancelledError）做尽力 rollback（吞掉 rollback
    自身错误），原异常照常上抛，让上层（ASGI）按取消语义收尾。
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            try:
                await session.rollback()
            except BaseException:
                pass
            raise


async def init_db():
    """Create all tables + lightweight column migrations for existing DBs.

    create_all 只建缺失的表，不给已存在的表加列。新增列（如 chat_sessions.type、
    chat_messages.meta）通过 ALTER TABLE ADD COLUMN 升级旧库；新库由 create_all 直建。
    SQLite 支持 ADD COLUMN（带默认值），PRAGMA table_info 检查列存在性，幂等。
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_columns(conn)


async def _migrate_columns(conn) -> None:
    """幂等补列：对已存在的表追加后续版本新增的列。"""
    from sqlalchemy import text

    # chat_sessions.type（辩论会话标识：chat / debate）
    rows = (await conn.execute(text("PRAGMA table_info(chat_sessions)"))).fetchall()
    names = {r[1] for r in rows}
    if "type" not in names:
        await conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN type VARCHAR(10) DEFAULT 'chat' NOT NULL"))

    # chat_messages.meta（辩论 round/opinion 元数据 JSON）
    rows = (await conn.execute(text("PRAGMA table_info(chat_messages)"))).fetchall()
    names = {r[1] for r in rows}
    if "meta" not in names:
        await conn.execute(text("ALTER TABLE chat_messages ADD COLUMN meta JSON"))
