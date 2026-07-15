"""Typed failures returned by import-member identity resolution."""


class MemberIdentityError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)
