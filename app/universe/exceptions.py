"""Universe-layer errors."""


class UniverseError(Exception):
    """Base error for universe operations."""


class UniverseSourceError(UniverseError):
    """Raised when the historical universe source cannot be loaded or parsed."""


class UniverseValidationError(UniverseError):
    """Raised when membership intervals fail validation and must not be persisted."""

    def __init__(self, message: str, *, issues: tuple[str, ...] = ()) -> None:
        self.issues = issues
        super().__init__(message)


class UniverseProviderError(UniverseError):
    """Raised when a universe provider cannot be constructed."""
