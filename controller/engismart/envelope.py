"""Every Engismart JSON answer uses the platform's envelope  {"status": bool, "data": ..., "message": str, "error": str|None}.

Streams (chat tokens) and files (pictures) are not JSON and pass through unchanged."""
from __future__ import annotations

import json
from collections.abc import Callable

from fastapi import HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute


def ok(data, message: str = "") -> dict:
    return {"status": True, "data": data, "message": message, "error": None}


def fail(message: str, error: str | None = None, data=None) -> dict:
    return {"status": False, "data": data, "message": message, "error": error}


def _headers(response: Response) -> dict:
    return {k: v for k, v in response.headers.items() if k.lower() not in ("content-length", "content-type")}


class EnvelopeRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                response = await original(request)
            except HTTPException as e:
                body = e.detail if isinstance(e.detail, dict) and {"status", "message"} <= set(e.detail) else fail(
                    str(e.detail), error=f"http_{e.status_code}")
                return JSONResponse(body, status_code=e.status_code, headers=e.headers)
            except RequestValidationError as e:
                first = e.errors()[0] if e.errors() else {}
                where = ".".join(str(x) for x in first.get("loc", ()) if x != "body")
                return JSONResponse(fail(f"Invalid request: {where + ': ' if where else ''}{first.get('msg', 'bad value')}",
                                         error="validation_error", data=json.loads(json.dumps(e.errors(), default=str))),
                                    status_code=422)
            if type(response) is JSONResponse:  # not a stream, not a file
                payload = json.loads(response.body)
                if response.status_code < 400 and not (isinstance(payload, dict) and {"status", "data", "message"} <= set(payload)):
                    return JSONResponse(ok(payload), status_code=response.status_code, headers=_headers(response))
            return response

        return handler
