"""Chat session + message models (LobeChat-inspired, simplified two-layer).

参考 LobeChat session/topic/message/messageGroup 四层，简化为 ChatSession+ChatMessage
两层：用 is_compressed 布尔 + summary 字段替代 MessageGroup 表。
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ChatSession(Base):
    """聊天会话（一个用户可有多条会话，每条独立上下文）。"""

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(100), default="新对话", nullable=False)
    agent_ids: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str | None] = mapped_column(Text)  # 上下文压缩摘要
    summary_upto_msg_id: Mapped[int | None] = mapped_column(Integer)  # 摘要到哪条消息
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime)


class ChatMessage(Base):
    """聊天消息（user/assistant/system，带压缩标记）。"""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user / assistant / system
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    agents_used: Mapped[list] = mapped_column(JSON, default=list)
    stocks_detected: Mapped[list] = mapped_column(JSON, default=list)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    is_compressed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
