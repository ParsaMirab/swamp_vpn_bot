from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.database.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    last_active: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class RequiredChannel(Base):
    __tablename__ = "required_channels"
    __table_args__ = (UniqueConstraint("channel_id", name="uq_required_channels_channel_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_username: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    plans: Mapped[list[Plan]] = relationship(
        back_populates="service",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    orders: Mapped[list[Order]] = relationship(back_populates="service")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    inbound_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    traffic_limit_gb: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30, server_default="30")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    service: Mapped[Service] = relationship(back_populates="plans")
    orders: Mapped[list[Order]] = relationship(back_populates="plan")


class BankCard(Base):
    __tablename__ = "bank_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    card_number: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class DiscountCode(Base):
    __tablename__ = "discount_codes"
    __table_args__ = (UniqueConstraint("code", name="uq_discount_codes_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    discount_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    usage_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    per_user_usage_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    usages: Mapped[list[DiscountUsage]] = relationship(
        back_populates="discount",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    orders: Mapped[list[Order]] = relationship(back_populates="discount")


class DiscountUsage(Base):
    __tablename__ = "discount_usages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discount_id: Mapped[int] = mapped_column(
        ForeignKey("discount_codes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    discount: Mapped[DiscountCode] = relationship(back_populates="usages")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False, index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), nullable=False, index=True)
    discount_id: Mapped[int | None] = mapped_column(
        ForeignKey("discount_codes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    original_price: Mapped[int] = mapped_column(Integer, nullable=False)
    final_price: Mapped[int] = mapped_column(Integer, nullable=False)
    receipt_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sub_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")
    payment_type: Mapped[str] = mapped_column(String(16), nullable=False, default="wallet", server_default="wallet")
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    service: Mapped[Service] = relationship(back_populates="orders")
    plan: Mapped[Plan] = relationship(back_populates="orders")
    discount: Mapped[DiscountCode | None] = relationship(back_populates="orders")


class Setting(Base):
    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("key", name="uq_settings_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(String(512), nullable=False, server_default="")


class UserWallet(Base):
    __tablename__ = "user_wallets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column("type", String(16), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    receipt_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RechargePackage(Base):
    __tablename__ = "recharge_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
