from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import timezone
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from pydantic import BaseModel, StringConstraints, field_validator

from ai_actuarial.postgres import postgres_connection

FeedbackKind = Literal["suggestion", "problem", "other"]
FeedbackOrigin = Literal["widget", "assistant"]
FeedbackStatus = Literal["new", "reviewed", "closed"]
StrictText = Annotated[str, StringConstraints(strict=True)]


class FeedbackRequest(BaseModel):
    client_request_id: UUID
    content: Annotated[StrictText, StringConstraints(min_length=1, max_length=4000)]
    kind: FeedbackKind = "suggestion"
    origin: FeedbackOrigin = "widget"
    page_path: Annotated[StrictText, StringConstraints(max_length=2048)] = "/"
    locale: Annotated[
        StrictText, StringConstraints(max_length=35, pattern=r"^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$")
    ] = "en"

    @field_validator("content", mode="before")
    @staticmethod
    def trim_content(value):
        if isinstance(value, str) and "\x00" in value:
            raise ValueError("content must not contain null characters")
        return value.strip() if isinstance(value, str) else value

    @field_validator("page_path")
    @staticmethod
    def local_path(value: str) -> str:
        if not value.startswith("/") or value.startswith("//") or "\\" in value:
            raise ValueError("page_path must be a site-relative path")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("page_path must not contain control characters")
        return urlsplit(value).path


class FeedbackConflict(ValueError):
    pass


@contextmanager
def _transaction(database):
    with postgres_connection(database) as connection:
        try:
            connection.execute("BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def _timestamp(value) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _receipt(row) -> dict:
    return {
        "feedback_id": str(row["feedback_id"]),
        "status": "recorded",
        "created_at": _timestamp(row["created_at"]),
    }


def submit_feedback(database, submission: FeedbackRequest, *, site_key: str, user_id: int | None):
    canonical = {**submission.model_dump(mode="json"), "site_key": site_key, "user_id": user_id}
    request_hash = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    with _transaction(database) as connection:
        row = connection.execute(
            "INSERT INTO feedback_items "
            "(feedback_id, client_request_id, request_hash, site_key, content, kind, origin, "
            "user_id, page_path, locale) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (client_request_id) DO NOTHING RETURNING *",
            (
                str(uuid4()),
                str(submission.client_request_id),
                request_hash,
                site_key,
                submission.content,
                submission.kind,
                submission.origin,
                user_id,
                submission.page_path,
                submission.locale,
            ),
        ).fetchone()
        if row is None:
            row = connection.execute(
                "SELECT * FROM feedback_items WHERE client_request_id = ?",
                (str(submission.client_request_id),),
            ).fetchone()
            if row["request_hash"] != request_hash:
                raise FeedbackConflict("client_request_id was already used for a different request")
        receipt = _receipt(row)
    return receipt


def _admin_item(row) -> dict:
    item = dict(row)
    item.pop("request_hash")
    for key in ("created_at", "updated_at"):
        item[key] = _timestamp(item[key])
    for key in ("feedback_id", "client_request_id"):
        item[key] = str(item[key])
    return item


def list_feedback(database, *, status=None, site_key=None, cursor=0, limit=50):
    clauses = ["id > ?"]
    values = [cursor]
    for column, value in (("status", status), ("site_key", site_key)):
        if value is not None:
            clauses.append(f"{column} = ?")
            values.append(value)
    with postgres_connection(database, read_only=True) as connection:
        rows = connection.execute(
            "SELECT * FROM feedback_items WHERE " + " AND ".join(clauses) + " ORDER BY id LIMIT ?",
            (*values, limit + 1),
        ).fetchall()
    return {
        "items": [_admin_item(row) for row in rows[:limit]],
        "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
    }


def update_feedback_status(database, feedback_id: UUID, status: FeedbackStatus):
    with _transaction(database) as connection:
        row = connection.execute(
            "UPDATE feedback_items SET status = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE feedback_id = ? RETURNING *",
            (status, str(feedback_id)),
        ).fetchone()
        item = _admin_item(row) if row is not None else None
    return item
