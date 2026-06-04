from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from bot.constants import DEFAULT_NAME_STYLE


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    telegram_tag: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telegram_channel_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name_style: Mapped[str] = mapped_column(Text, nullable=False, default=DEFAULT_NAME_STYLE)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
