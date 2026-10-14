"""Errors raised by the independent credit system."""


class CreditError(Exception):
    """Base class for credit-domain failures."""


class CreditConfigurationError(CreditError):
    """Database configuration is missing or unsafe."""


class CreditConflictError(CreditError):
    """An idempotency key was reused for different business data."""


class CreditNotFoundError(CreditError):
    """The requested user, job, order, or reservation does not exist."""


class InsufficientCreditsError(CreditError):
    """The user does not have enough available credits."""

    def __init__(self, *, required: int, available: int) -> None:
        self.required = required
        self.available = available
        super().__init__(f"Insufficient credits: required={required}, available={available}")


class CreditStateError(CreditError):
    """The requested transition is invalid for the current record state."""
