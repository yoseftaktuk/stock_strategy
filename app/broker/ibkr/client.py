from app.config.settings import Settings


class IBKRClient:
    """Encapsulates communication with Interactive Brokers TWS API and IB Gateway."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connected = False

    def connect(self) -> None:
        raise NotImplementedError("IBKR integration not implemented")

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected
