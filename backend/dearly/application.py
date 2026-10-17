"""FastAPI application assembly and exception handling."""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

import anyio
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from localization import RequestError, error_response
from web_support import BrowserSession, mount_web

from .database import Database
from .account import register_routes as register_account
from .encryption import register_routes as register_encryption
from .limits import BodyLimit
from .routes_auth import register_routes as register_auth
from .routes_chat import register_routes as register_chat
from .routes_read import register_routes as register_read
from .routes_staff import register_routes as register_staff
from .service import AppServices


def create_app(
    path: str | Path = "data/dearly.sqlite3",
    *,
    clock: Callable[[], float] = time.time,
    body_idle_timeout: float = 5.0,
    body_total_timeout: float = 15.0,
    web_dir: str | Path | None = None,
) -> FastAPI:
    if body_idle_timeout <= 0 or body_total_timeout <= 0:
        raise ValueError("Request body timeouts must be positive.")
    services = AppServices(Database(path), clock)

    @asynccontextmanager
    async def lifespan(app):
        anyio.to_thread.current_default_thread_limiter().total_tokens = 16
        yield

    app = FastAPI(
        title="Dearly API",
        version="0.5.0",
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.database = services.database
    app.add_middleware(
        BodyLimit, idle_timeout=body_idle_timeout, total_timeout=body_total_timeout
    )
    app.add_middleware(BrowserSession)

    @app.exception_handler(RequestError)
    async def request_error(request, exc):
        return error_response(
            exc.message,
            exc.status_code,
            language=request.headers.get("accept-language", ""),
            **exc.parameters,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Do not reflect submitted credentials back in validation responses.
        return error_response(
            "Invalid details. Check your username, password, and required fields.",
            422,
            language=request.headers.get("accept-language", ""),
        )

    @app.exception_handler(sqlite3.OperationalError)
    async def database_busy(request, exc):
        return error_response(
            "The database is busy. Please try again.",
            503,
            language=request.headers.get("accept-language", ""),
            headers={"Retry-After": "1"},
        )

    register_auth(app, services)
    register_account(app, services)
    register_encryption(app, services)
    register_read(app, services)
    register_staff(app, services)
    register_chat(app, services)

    selected_web = web_dir or os.environ.get("DEARLY_WEB_DIST")
    directory = (
        Path(selected_web)
        if selected_web
        else Path(__file__).resolve().parents[2] / "web" / "dist"
    )
    if (directory / "index.html").is_file():
        mount_web(app, directory, authorize_management=services.staff_access)
    elif selected_web:
        raise ValueError(
            "The selected web directory has no index.html. Run npm run build in web first."
        )
    return app
