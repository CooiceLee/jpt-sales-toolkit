"""Provider boundary retained when local authorization moves to a server."""

from __future__ import annotations

from abc import ABC, abstractmethod


class AuthorizationProvider(ABC):
    """Common contract for offline packages and future remote sessions."""

    @abstractmethod
    def status(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def validate_user(self, user: dict) -> bool:
        raise NotImplementedError
