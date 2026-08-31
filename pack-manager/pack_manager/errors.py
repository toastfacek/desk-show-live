class ValidationError(ValueError):
    """Raised when pack manager input is invalid."""


class ConflictError(RuntimeError):
    """Raised when an operation conflicts with persisted domain state."""


class IntegrityError(RuntimeError):
    """Raised when a locked baseline fails integrity verification."""
