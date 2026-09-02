"""Security Master errors."""


class SecurityMasterError(Exception):
    """Base error for security-master operations."""


class SecurityMasterValidationError(SecurityMasterError):
    """Raised when ticker intervals fail validation and must not be persisted."""

    def __init__(self, message: str, *, issues: tuple[str, ...] = ()) -> None:
        self.issues = issues
        super().__init__(message)


class SecurityMasterSourceError(SecurityMasterError):
    """Raised when the known-identities catalog cannot be loaded."""
