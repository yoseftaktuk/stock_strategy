from decimal import Decimal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.enums import TradingMode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    trading_mode: TradingMode = TradingMode.BACKTEST
    broker: str = "IBKR"

    ibkr_host: str = Field(default="ib-gateway", alias="IBKR_HOST")
    ibkr_port: int = Field(default=4002, alias="IBKR_PORT")
    ibkr_client_id: int = Field(default=10, alias="IBKR_CLIENT_ID")

    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="momentum_trader", alias="POSTGRES_DB")
    postgres_user: str = Field(default="momentum", alias="POSTGRES_USER")
    postgres_password: str = Field(default="change_me", alias="POSTGRES_PASSWORD")
    postgres_test_db: str = Field(default="momentum_trader_test", alias="POSTGRES_TEST_DB")

    data_provider: str = Field(default="CSV", alias="DATA_PROVIDER")
    csv_data_path: str = Field(default="data/raw", alias="CSV_DATA_PATH")
    market_data_insert_batch_size: int = Field(default=2000, alias="MARKET_DATA_INSERT_BATCH_SIZE")

    universe: list[str] = Field(default_factory=list)
    momentum_lookback: int = 252
    momentum_skip: int = 21
    top_n: int = 10
    min_price: Decimal = Decimal("10")
    liquidity_window_days: int = 20
    min_dollar_volume: Decimal = Decimal("20000000")
    market_ma_period: int = 200
    slippage: Decimal = Decimal("0.001")

    @property
    def database_url(self) -> str:
        return self._build_database_url(self.postgres_db)

    @property
    def test_database_url(self) -> str:
        return self._build_database_url(self.postgres_test_db)

    def _build_database_url(self, database_name: str) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{database_name}"
        )
