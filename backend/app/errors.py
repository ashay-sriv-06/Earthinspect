from __future__ import annotations


class ApiError(Exception):
    """Consistent machine code + user message for every failure surfaced to clients."""

    def __init__(self, code: str, message: str, status: int = 400, detail: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.detail = detail or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "detail": self.detail}}
