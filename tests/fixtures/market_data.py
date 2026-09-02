from collections.abc import Sequence
from datetime import date, datetime, timezone
from decimal import Decimal

from app.domain.models.market_bar import MarketBar

UTC = timezone.utc

SAMPLE_BAR = MarketBar(
    symbol="AAPL",
    timestamp=datetime(2024, 1, 2, 16, 0, tzinfo=UTC),
    open=Decimal("150.00"),
    high=Decimal("155.00"),
    low=Decimal("149.00"),
    close=Decimal("154.00"),
    adjusted_close=Decimal("154.00"),
    volume=1_000_000,
)

SAMPLE_BAR_MSFT = MarketBar(
    symbol="MSFT",
    timestamp=datetime(2024, 1, 2, 16, 0, tzinfo=UTC),
    open=Decimal("370.00"),
    high=Decimal("375.00"),
    low=Decimal("368.00"),
    close=Decimal("372.00"),
    adjusted_close=Decimal("372.00"),
    volume=500_000,
)


class InMemoryMarketDataRepository:
    def __init__(self) -> None:
        self.saved: list[MarketBar] = []
        self.save_calls = 0
        self.fail_on_save = False

    def save_bars(self, bars: Sequence[MarketBar]) -> int:
        self.save_calls += 1
        if self.fail_on_save:
            raise RuntimeError("database down")
        existing = {(bar.symbol, bar.timestamp) for bar in self.saved}
        inserted = 0
        for bar in bars:
            key = (bar.symbol, bar.timestamp)
            if key not in existing:
                self.saved.append(bar)
                existing.add(key)
                inserted += 1
        return inserted

    def get_bars(self, symbol: str, start: date, end: date) -> Sequence[MarketBar]:
        start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc)
        matched = [
            bar
            for bar in self.saved
            if bar.symbol == symbol.upper() and start_dt <= bar.timestamp <= end_dt
        ]
        return sorted(matched, key=lambda bar: bar.timestamp)

    def get_latest_bar(self, symbol: str) -> MarketBar | None:
        matched = [bar for bar in self.saved if bar.symbol == symbol.upper()]
        if not matched:
            return None
        return max(matched, key=lambda bar: bar.timestamp)
