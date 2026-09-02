from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.database.repositories.market_data import PostgresMarketDataRepository
from app.domain.models.market_bar import MarketBar
from tests.fixtures.market_data import SAMPLE_BAR, SAMPLE_BAR_MSFT, UTC


def _bar(symbol: str, day: date, close: str) -> MarketBar:
    price = Decimal(close)
    return MarketBar(
        symbol=symbol,
        timestamp=datetime(day.year, day.month, day.day, 14, 30, tzinfo=UTC),
        open=price,
        high=price + Decimal("1.00"),
        low=price - Decimal("1.00"),
        close=price,
        adjusted_close=price,
        volume=1_000,
    )


@pytest.mark.integration
def test_market_data_repository_save_and_get_bars(db_session: Session) -> None:
    repository = PostgresMarketDataRepository(db_session)
    inserted = repository.save_bars([SAMPLE_BAR, SAMPLE_BAR_MSFT])
    db_session.commit()

    assert inserted == 2
    bars = repository.get_bars("AAPL", SAMPLE_BAR.timestamp.date(), SAMPLE_BAR.timestamp.date())
    assert len(bars) == 1
    assert bars[0].close == SAMPLE_BAR.close


@pytest.mark.integration
def test_market_data_repository_get_latest_bar(db_session: Session) -> None:
    repository = PostgresMarketDataRepository(db_session)
    earlier = _bar("AAPL", date(2024, 1, 2), "154.00")
    later = _bar("AAPL", date(2024, 1, 5), "160.00")
    repository.save_bars([later, earlier])
    db_session.commit()

    latest = repository.get_latest_bar("AAPL")
    assert latest is not None
    assert latest.timestamp == later.timestamp
    assert latest.close == Decimal("160.00")


@pytest.mark.integration
def test_market_data_repository_date_filtering(db_session: Session) -> None:
    repository = PostgresMarketDataRepository(db_session)
    bars = [
        _bar("AAPL", date(2025, 1, 2), "243.85"),
        _bar("AAPL", date(2025, 1, 3), "245.20"),
        _bar("AAPL", date(2025, 1, 6), "247.15"),
    ]
    repository.save_bars(bars)

    filtered = repository.get_bars("AAPL", date(2025, 1, 3), date(2025, 1, 5))
    assert len(filtered) == 1
    assert filtered[0].timestamp.date() == date(2025, 1, 3)


@pytest.mark.integration
def test_market_data_repository_prevents_duplicates(db_session: Session) -> None:
    repository = PostgresMarketDataRepository(db_session)
    first = repository.save_bars([SAMPLE_BAR])
    second = repository.save_bars([SAMPLE_BAR])

    assert first == 1
    assert second == 0
    bars = repository.get_bars("AAPL", SAMPLE_BAR.timestamp.date(), SAMPLE_BAR.timestamp.date())
    assert len(bars) == 1


@pytest.mark.integration
def test_market_data_repository_multiple_symbols(db_session: Session) -> None:
    repository = PostgresMarketDataRepository(db_session)
    repository.save_bars(
        [
            _bar("AAPL", date(2025, 1, 2), "243.85"),
            _bar("MSFT", date(2025, 1, 2), "421.25"),
        ]
    )

    apple = repository.get_bars("AAPL", date(2025, 1, 1), date(2025, 1, 31))
    microsoft = repository.get_bars("MSFT", date(2025, 1, 1), date(2025, 1, 31))
    assert len(apple) == 1
    assert len(microsoft) == 1
    assert apple[0].symbol == "AAPL"
    assert microsoft[0].symbol == "MSFT"


@pytest.mark.integration
def test_market_data_repository_returns_chronological_order(db_session: Session) -> None:
    repository = PostgresMarketDataRepository(db_session)
    repository.save_bars(
        [
            _bar("AAPL", date(2025, 1, 6), "247.15"),
            _bar("AAPL", date(2025, 1, 2), "243.85"),
            _bar("AAPL", date(2025, 1, 3), "245.20"),
        ]
    )

    bars = repository.get_bars("AAPL", date(2025, 1, 1), date(2025, 1, 31))
    assert [bar.timestamp.date() for bar in bars] == [
        date(2025, 1, 2),
        date(2025, 1, 3),
        date(2025, 1, 6),
    ]


@pytest.mark.integration
def test_market_data_repository_transaction_rollback(db_engine) -> None:
    factory = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    session = factory()
    repository = PostgresMarketDataRepository(session)
    unique_bar = _bar("NVDA", date(2025, 6, 1), "100.00")
    repository.save_bars([unique_bar])
    session.flush()
    session.rollback()
    session.close()

    session = factory()
    repository = PostgresMarketDataRepository(session)
    assert repository.get_latest_bar("NVDA") is None
    session.close()


@pytest.mark.integration
def test_historical_provider_service_import_idempotent(db_session: Session) -> None:
    from app.data.import_summary import MarketDataImportStatus
    from app.data.market_data import MarketDataService
    from app.data.providers.historical import HistoricalMarketDataProvider

    rows = [
        {
            "date": date(2014, 1, 2),
            "open": "10.00",
            "high": "11.00",
            "low": "9.50",
            "close": "10.50",
            "adjusted_close": "10.40",
            "volume": 1000,
        },
        {
            "date": date(2014, 1, 3),
            "open": "10.50",
            "high": "11.50",
            "low": "10.00",
            "close": "11.00",
            "adjusted_close": "10.90",
            "volume": 1100,
        },
    ]
    provider = HistoricalMarketDataProvider(downloader=lambda *_: rows)
    repository = PostgresMarketDataRepository(db_session)
    service = MarketDataService(provider=provider, repository=repository)

    first = service.import_history(["AAPL"], date(2014, 1, 1), date(2014, 1, 31))[0]
    second = service.import_history(["AAPL"], date(2014, 1, 1), date(2014, 1, 31))[0]
    db_session.commit()

    assert first.rows_inserted == 2
    assert first.status == MarketDataImportStatus.SUCCESS
    assert second.rows_inserted == 0
    assert second.duplicates == 2
    bars = repository.get_bars("AAPL", date(2014, 1, 1), date(2014, 1, 31))
    assert len(bars) == 2
    assert bars[0].adjusted_close == Decimal("10.40")
