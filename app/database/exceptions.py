class RepositoryError(Exception):
    """Base exception for repository operations."""


class DatabaseConnectionError(RepositoryError):
    """Raised when the database connection cannot be established."""


class EntityNotFoundError(RepositoryError):
    """Raised when a requested entity does not exist."""
