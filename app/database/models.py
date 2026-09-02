from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class StockModel(Base):
    __tablename__ = "stocks"
    __table_args__ = (UniqueConstraint("symbol", "exchange", name="uq_stocks_symbol_exchange"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    market_bars: Mapped[list["MarketBarModel"]] = relationship(back_populates="stock")
    signals: Mapped[list["SignalModel"]] = relationship(back_populates="stock")


class MarketBarModel(Base):
    __tablename__ = "market_bars"
    __table_args__ = (
        UniqueConstraint("stock_id", "timestamp", name="uq_market_bars_stock_timestamp"),
        Index("ix_market_bars_stock_timestamp", "stock_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    adjusted_close: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)

    stock: Mapped["StockModel"] = relationship(back_populates="market_bars")


class SignalModel(Base):
    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint("stock_id", "signal_date", name="uq_signals_stock_signal_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    signal_date: Mapped[date] = mapped_column(Date, nullable=False)
    momentum: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    stock: Mapped["StockModel"] = relationship(back_populates="signals")


class OrderModel(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    order_type: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
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

    fills: Mapped[list["FillModel"]] = relationship(back_populates="order")


class FillModel(Base):
    __tablename__ = "fills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    broker_execution_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    commission: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    order: Mapped["OrderModel"] = relationship(back_populates="fills")


class PortfolioSnapshotModel(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    exposure: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    drawdown: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)


class RebalanceModel(Base):
    __tablename__ = "rebalances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rebalance_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    market_regime: Mapped[str | None] = mapped_column(String(50), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


OPEN_INTERVAL_SENTINEL = "DATE '9999-12-31'"


class SP500ConstituentMembershipModel(Base):
    """Point-in-time S&P 500 membership intervals. Not linked to market data."""

    __tablename__ = "sp500_constituent_memberships"
    __table_args__ = (
        Index(
            "ix_sp500_constituent_memberships_pit",
            "symbol",
            "start_date",
            "end_date",
        ),
        Index(
            "uq_sp500_constituent_memberships_interval",
            "symbol",
            "start_date",
            text(f"COALESCE(end_date, {OPEN_INTERVAL_SENTINEL})"),
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SecurityModel(Base):
    """Canonical security identity. Not a ticker row; not PIT membership."""

    __tablename__ = "securities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seed_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    security_type: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    tickers: Mapped[list["SecurityTickerModel"]] = relationship(back_populates="security")
    identifiers: Mapped[list["SecurityIdentifierModel"]] = relationship(back_populates="security")


class SecurityTickerModel(Base):
    """Time-bounded listing or vendor ticker assignment."""

    __tablename__ = "security_tickers"
    __table_args__ = (
        Index("ix_security_tickers_scheme_ticker", "scheme", "ticker", "valid_from"),
        Index(
            "uq_security_tickers_interval",
            "scheme",
            "ticker",
            "valid_from",
            text(f"COALESCE(valid_to, {OPEN_INTERVAL_SENTINEL})"),
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"), nullable=False)
    scheme: Mapped[str] = mapped_column(String(20), nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    continuity: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    security: Mapped["SecurityModel"] = relationship(back_populates="tickers")


class SecurityIdentifierModel(Base):
    """External identifier attribute attached to a security."""

    __tablename__ = "security_identifiers"
    __table_args__ = (
        Index(
            "uq_security_identifiers_type_value_from",
            "id_type",
            "id_value",
            text("COALESCE(valid_from, DATE '0001-01-01')"),
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"), nullable=False)
    id_type: Mapped[str] = mapped_column(String(20), nullable=False)
    id_value: Mapped[str] = mapped_column(String(64), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    security: Mapped["SecurityModel"] = relationship(back_populates="identifiers")
