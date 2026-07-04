from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ServiceError(Exception):
    status_code: int
    code: str
    message: str
    details: dict[str, Any] | None = None

    def to_body(self, request_id: str | None = None) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details or {},
                "request_id": request_id,
            }
        }


def invalid_request(message: str, details: dict[str, Any] | None = None) -> ServiceError:
    return ServiceError(400, "INVALID_REQUEST", message, details)


def not_found(kind: str, value: str) -> ServiceError:
    return ServiceError(404, f"{kind.upper()}_NOT_FOUND", f"{kind} not found: {value}", {f"{kind}_id": value})


def conflict(code: str, message: str, details: dict[str, Any] | None = None) -> ServiceError:
    return ServiceError(409, code, message, details)
