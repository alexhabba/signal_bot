import enum
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# USDT has 6 decimals on Tron; keep the same precision for every amount.
Amount = Numeric(18, 6)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class InvoiceStatus(str, enum.Enum):
    PENDING = "pending"  # issued, waiting for a transfer
    PAID = "paid"
    UNDERPAID = "underpaid"  # a transfer arrived but short; resolved by an admin
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


# Statuses whose amount is reserved and must not be reused by a new invoice.
ACTIVE_INVOICE_STATUSES = (InvoiceStatus.PENDING,)


class SubscriptionSource(str, enum.Enum):
    PAYMENT = "payment"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram user id
    username: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str | None] = mapped_column(String(256))
    language: Mapped[str | None] = mapped_column(String(8))
    # Overpayments are credited here and spent on the next renewal.
    balance: Mapped[Decimal] = mapped_column(Amount, default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(64))
    days: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Amount)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    network: Mapped[str] = mapped_column(String(16))
    address: Mapped[str] = mapped_column(String(128))
    amount: Mapped[Decimal] = mapped_column(Amount, index=True)
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, values_callable=lambda e: [m.value for m in e], native_enum=False, length=16),
        default=InvoiceStatus.PENDING,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    plan: Mapped[Plan] = relationship()
    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice")


class Payment(Base):
    """An incoming on-chain transfer. tx_hash is unique so a transfer is never credited twice."""

    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("network", "tx_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    network: Mapped[str] = mapped_column(String(16))
    tx_hash: Mapped[str] = mapped_column(String(128))
    from_address: Mapped[str] = mapped_column(String(128))
    amount: Mapped[Decimal] = mapped_column(Amount)
    block_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    invoice: Mapped[Invoice | None] = relationship(back_populates="payments")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[SubscriptionSource] = mapped_column(
        Enum(SubscriptionSource, values_callable=lambda e: [m.value for m in e], native_enum=False, length=16)
    )
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Reminder and removal bookkeeping, so the scheduler acts on each subscription once.
    reminded_days: Mapped[int | None] = mapped_column(Integer)
    access_revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship(back_populates="subscriptions")


class Signal(Base):
    """A signal sent to subscribers' private chats. The text is kept as the admin wrote it."""

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    recipients: Mapped[int] = mapped_column(Integer, default=0)  # delivered
    failed: Mapped[int] = mapped_column(Integer, default=0)  # blocked the bot or unreachable
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(BigInteger)  # None for automatic actions
    action: Mapped[str] = mapped_column(String(64))
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
