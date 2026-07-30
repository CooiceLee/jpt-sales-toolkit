"""Typed failures shared by geocoding providers and API routes."""

from __future__ import annotations


class GeocodingError(RuntimeError):
    """A user-actionable geocoding failure without leaking provider secrets."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 503,
        retryable: bool = True,
        provider: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.provider = provider

    def as_detail(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "provider": self.provider,
        }
