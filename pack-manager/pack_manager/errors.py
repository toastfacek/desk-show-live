class ValidationError(ValueError):
    """Raised when pack manager input is invalid."""


class ConflictError(RuntimeError):
    """Raised when an operation conflicts with persisted domain state."""
