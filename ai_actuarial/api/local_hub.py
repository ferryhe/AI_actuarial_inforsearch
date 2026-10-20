from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
from typing import Any, Callable

import psycopg2
import uvicorn
from fastapi import FastAPI, HTTPException, Query

from .hub_read import HubReader


def _viewer_auth() -> dict[str, Any]:
    return {
        "success": True,
        "data": {
            "require_auth": False,
            "authenticated": False,
            "user": None,
            "permissions": ["files.read"],
            "read_only": True,
        },
    }


def _read_database_url(config_path: Path) -> str:
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Could not read the local Content Hub connection config") from exc
    database_url = config.get("database_url") if isinstance(config, dict) else None
    if not isinstance(database_url, str) or not database_url.strip():
        raise RuntimeError("The local Content Hub config has no database_url")
    return database_url.strip()


def create_app(
    connection_config: str | Path | None = None,
    *,
    connection_factory: Callable[[], Any] | None = None,
) -> FastAPI:
    if connection_factory is None:
        if connection_config is None:
            raise ValueError("A local Content Hub connection config is required")
        database_url = _read_database_url(Path(connection_config))

        def connection_factory() -> Any:
            return psycopg2.connect(
                database_url,
                options="-c default_transaction_read_only=on",
                connect_timeout=5,
            )

    app = FastAPI(title="Local Content Hub Viewer", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.hub_reader = HubReader(connection_factory)

    app.add_api_route("/api/auth/me", _viewer_auth, methods=["GET"])

    @app.get("/api/hub/sources")
    def sources() -> dict[str, Any]:
        return {"sources": app.state.hub_reader.sources()}

    @app.get("/api/hub/categories")
    def categories() -> dict[str, Any]:
        return {"categories": app.state.hub_reader.categories()}

    @app.get("/api/hub/files")
    def files(
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=1_000_000),
        query: str = "",
        source: str = "",
        category: str = "",
        order_by: str = "last_seen",
        order_dir: str = "desc",
    ) -> dict[str, Any]:
        if order_by not in {"title", "source_site", "last_seen", "first_seen", "bytes"}:
            order_by = "last_seen"
        if order_dir not in {"asc", "desc"}:
            order_dir = "desc"
        return app.state.hub_reader.list_files(
            limit=limit,
            offset=offset,
            query=query,
            source=source,
            category=category,
            order_by=order_by,
            order_dir=order_dir,
        )

    @app.get("/api/hub/files/{content_version_id}")
    def file_detail(content_version_id: int) -> dict[str, Any]:
        file_data = app.state.hub_reader.file_detail(content_version_id)
        if file_data is None:
            raise HTTPException(status_code=404, detail="Content version not found")
        return {"file": file_data}

    return app


def _loopback_host(value: str) -> str:
    try:
        host = ipaddress.ip_address(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("host must be a loopback IP address") from exc
    if not host.is_loopback:
        raise argparse.ArgumentTypeError("the local Hub viewer may bind only to loopback")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the local Content Hub in read-only mode")
    parser.add_argument("--connection-config", required=True, type=Path)
    parser.add_argument("--host", type=_loopback_host, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    uvicorn.run(
        create_app(args.connection_config), host=args.host, port=args.port, access_log=False
    )


if __name__ == "__main__":
    main()
