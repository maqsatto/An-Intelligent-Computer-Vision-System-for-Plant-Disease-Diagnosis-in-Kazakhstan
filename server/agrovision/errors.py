from fastapi import Request
from fastapi.responses import JSONResponse


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details


def error_response(request: Request, status: int, code: str, message: str, details=None):
    return JSONResponse(
        status_code=status,
        content={
            "code": code,
            "message": message,
            "details": details,
            "request_id": getattr(request.state, "request_id", "unknown"),
        },
    )
