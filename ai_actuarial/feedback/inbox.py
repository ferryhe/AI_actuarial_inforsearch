"""Local feedback inbox; HTTP management only, independent of public intake and AI."""

from __future__ import annotations

import argparse
import http.client
import importlib
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from ai_actuarial.feedback.store import FeedbackRequest
from ai_actuarial.postgres import resolve_data_root
from ai_actuarial.shared_runtime import SitesConfigError, load_sites_config

EXIT_CODES = {
    "config": 2,
    "authentication": 3,
    "permission": 4,
    "connection": 5,
    "remote": 6,
    "local_write": 7,
    "local_read": 8,
    "protocol": 9,
    "not_found": 10,
    "busy": 11,
}
_SITE_KEY = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_FIELDS = {
    "id",
    "feedback_id",
    "client_request_id",
    "site_key",
    "content",
    "kind",
    "origin",
    "user_id",
    "page_path",
    "locale",
    "status",
    "created_at",
    "updated_at",
}


class InboxError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code

    def payload(self):
        return {"code": self.code, "message": str(self)}


class FeedbackArgumentParser(argparse.ArgumentParser):
    """Keep feedback --json usage failures in the same stdout contract."""

    def parse_known_args(self, args=None, namespace=None):
        raw = list(sys.argv[1:] if args is None else args)
        words = self.prog.split() + raw
        self._feedback_json = "feedback" in words and "--json" in raw
        self._feedback_command = next(
            (word for word in ("pull", "list", "mark") if word in words), "feedback"
        )
        return super().parse_known_args(args, namespace)

    def error(self, message):
        if getattr(self, "_feedback_json", False):
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "command": self._feedback_command,
                        "success": False,
                        "outcome": "failed",
                        "items": [],
                        "sites": [],
                        "error": {
                            "code": "config",
                            "message": "Invalid feedback arguments; use feedback <command> --help",
                        },
                    }
                )
            )
            self.exit(EXIT_CODES["config"])
        super().error(message)


def _sites(config):
    section = config.get("feedback_inbox", {})
    sites = section.get("sites", []) if isinstance(section, dict) else None
    if not isinstance(sites, list) or not sites:
        raise InboxError("config", "Configure feedback_inbox.sites before remote operations")
    seen = set()
    for site in sites:
        if not isinstance(site, dict) or set(site) != {"site_key", "url", "token_env"}:
            raise InboxError("config", "Each inbox site requires only site_key, url and token_env")
        key, url, env = site["site_key"], site["url"], site["token_env"]
        if not isinstance(key, str) or not _SITE_KEY.fullmatch(key) or key in seen:
            raise InboxError("config", "Inbox site_key must be valid, stable and unique")
        seen.add(key)
        if not isinstance(env, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env):
            raise InboxError("config", "token_env must name an environment variable")
        try:
            parsed = urllib.parse.urlsplit(url)
            valid = (
                isinstance(url, str)
                and parsed.scheme in {"https", "http"}
                and parsed.hostname
                and not parsed.username
                and not parsed.password
                and not parsed.query
                and not parsed.fragment
                and parsed.port != 0
                and not any(char.isspace() or ord(char) < 32 for char in url)
            )
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            raise InboxError(
                "config", "Inbox URL must be an HTTP(S) base URL without credentials or query"
            )
    return sites


def api_request(site, *, cursor=None, feedback_id=None, status=None):
    token = os.getenv(site["token_env"], "").strip()
    if not token or any(ord(char) < 32 for char in token):
        raise InboxError("authentication", "Management credential is missing or invalid; renew it")
    url = site["url"].rstrip("/") + "/api/admin/feedback"
    data = None
    if feedback_id is None:
        url += "?" + urllib.parse.urlencode(
            {"status": "new", "site_key": site["site_key"], "limit": 100, "cursor": cursor}
        )
    else:
        url += "/" + str(UUID(feedback_id))
        data = json.dumps({"status": status}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="GET" if data is None else "PATCH",
        headers={"Content-Type": "application/json"},
    )
    request.add_unredirected_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise InboxError(
                "authentication", "Management credential is invalid or expired; renew it"
            ) from exc
        if exc.code == 403:
            raise InboxError(
                "permission",
                "Management credential lacks feedback.read or feedback.manage permission",
            ) from exc
        if exc.code == 404:
            raise InboxError(
                "not_found", "Feedback management endpoint or record was not found"
            ) from exc
        raise InboxError("remote", f"Feedback API returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
        raise InboxError(
            "connection", "Feedback API connection failed; retry the same operation"
        ) from exc
    except (ValueError, UnicodeError) as exc:
        raise InboxError("protocol", "Feedback API returned invalid JSON") from exc


def _record(record, *, site_key=None):
    try:
        if not isinstance(record, dict) or set(record) != _FIELDS:
            raise ValueError
        key = record["site_key"]
        if not isinstance(key, str) or not _SITE_KEY.fullmatch(key):
            raise ValueError
        if site_key is not None and key != site_key:
            raise ValueError
        if type(record["id"]) is not int or not 0 < record["id"] <= 9223372036854775807:
            raise ValueError
        if record["user_id"] is not None and type(record["user_id"]) is not int:
            raise ValueError
        if record["status"] not in {"new", "reviewed", "closed"}:
            raise ValueError
        if str(UUID(record["feedback_id"])) != record["feedback_id"]:
            raise ValueError
        normalized = FeedbackRequest.model_validate(record).model_dump(mode="json")
        if any(record[field] != value for field, value in normalized.items()):
            raise ValueError
        for field in ("created_at", "updated_at"):
            if datetime.fromisoformat(record[field]).tzinfo is None:
                raise ValueError
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise InboxError(
            "protocol", "Feedback record is incomplete, invalid or belongs to another site"
        ) from exc
    return dict(record)


def _key(record):
    return record["site_key"], record["feedback_id"]


def _read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError, UnicodeError) as exc:
        raise InboxError(
            "local_read", "Cannot read local feedback data; preserve files and repair before retry"
        ) from exc


def _load(root):
    stored = _read_json(root / "inbox.json", {"schema_version": 1, "items": []})
    try:
        if stored["schema_version"] != 1 or not isinstance(stored["items"], list):
            raise ValueError
        records = [_record(row) for row in stored["items"]]
        indexed = {_key(row): row for row in records}
        if len(indexed) != len(records):
            raise ValueError
        return indexed
    except (KeyError, TypeError, ValueError, InboxError) as exc:
        raise InboxError(
            "local_read", "Local inbox is invalid; preserve files and repair before retry"
        ) from exc


def _atomic_write(path, text):
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb" if isinstance(text, bytes) else "w",
            encoding=None if isinstance(text, bytes) else "utf-8",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise InboxError(
            "local_write", "Cannot atomically write local feedback data; retry after fixing storage"
        ) from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _ordered(records):
    return sorted(
        records.values(), key=lambda row: (row["site_key"], row["id"], row["feedback_id"])
    )


def _save(root, records):
    rows = _ordered(records)
    _atomic_write(
        root / "inbox.json",
        json.dumps({"schema_version": 1, "items": rows}, ensure_ascii=False, indent=2) + "\n",
    )


def _sync_lines(sites):
    lines = ["Local cached state; not a live server view."]
    for site in sites:
        error = site["error"]
        detail = f"{error['code']}: {error['message']}" if error else "none"
        lines.append(
            f"{site['site_key']}: outcome={site['outcome']}; "
            f"last_success_at={site['last_success_at'] or 'never'}; "
            f"last_attempt_at={site['last_attempt_at']}; error={detail}"
        )
    if len(lines) == 1:
        lines.append("No sync evidence recorded.")
    return lines


def _write_report(root, records, sites):
    sections = [
        "# Feedback inbox (local cached history)\n\n" + "\n\n".join(_sync_lines(sites)) + "\n"
    ]
    for row in _ordered(records):
        # JSON blocks preserve original text without letting submitted Markdown alter the report.
        encoded = json.dumps(
            {key: value for key, value in row.items() if key != "content"},
            ensure_ascii=False,
            indent=2,
        )
        fence = "`" * max(
            3, max((len(m.group()) + 1 for m in re.finditer(r"`+", row["content"])), default=3)
        )
        sections.append(
            f"\n## {row['site_key']} / {row['feedback_id']}\n\n```json\n{encoded}\n```\n\n{fence}text\n{row['content']}\n{fence}\n"
        )
    _atomic_write(root / "inbox.md", "".join(sections))


@contextmanager
def _lock(root):
    # Manual and scheduled read/modify/replace writers must not erase each other's pages.
    try:
        root.mkdir(parents=True, exist_ok=True)
        handle = (root / ".lock").open("a+b")
    except OSError as exc:
        raise InboxError("local_write", "Cannot open local inbox lock") from exc
    locked = False
    try:
        try:
            if os.name == "nt":
                import msvcrt

                if handle.seek(0, 2) == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl = importlib.import_module("fcntl")
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            raise InboxError("busy", "Another feedback writer is running; retry later") from exc
        yield
    finally:
        try:
            if locked:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _sync_state(root):
    state = _read_json(root / "sync.json", {"schema_version": 1, "sites": {}})
    fields = {
        "site_key",
        "success",
        "outcome",
        "new_count",
        "updated_count",
        "last_attempt_at",
        "last_success_at",
        "error",
    }
    try:
        if (
            not isinstance(state, dict)
            or set(state) != {"schema_version", "sites"}
            or type(state["schema_version"]) is not int
            or state["schema_version"] != 1
            or not isinstance(state["sites"], dict)
        ):
            raise ValueError
        for key, value in state["sites"].items():
            if (
                not _SITE_KEY.fullmatch(key)
                or not isinstance(value, dict)
                or set(value) != fields
                or value["site_key"] != key
                or type(value["success"]) is not bool
                or value["outcome"] not in {"updated", "no_new_data", "failed"}
            ):
                raise ValueError
            if any(
                type(value[field]) is not int or value[field] < 0
                for field in ("new_count", "updated_count")
            ):
                raise ValueError
            for field in ("last_attempt_at", "last_success_at"):
                timestamp = value[field]
                if timestamp is None and field == "last_success_at" and not value["success"]:
                    continue
                if (
                    not isinstance(timestamp, str)
                    or datetime.fromisoformat(timestamp).tzinfo is None
                ):
                    raise ValueError
            error = value["error"]
            if error is not None and (
                not isinstance(error, dict)
                or set(error) != {"code", "message"}
                or error["code"] not in EXIT_CODES
                or not isinstance(error["message"], str)
            ):
                raise ValueError
            if value["success"] != (value["outcome"] != "failed") or value["success"] != (
                error is None
            ):
                raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise InboxError("local_read", "Local feedback sync evidence is invalid") from exc
    return state


def _pull(root, sites, payload):
    with _lock(root):
        records = _load(root)
        state = _sync_state(root)
        for site in sites:
            key = site["site_key"]
            previous = state["sites"].get(key, {})
            result = {
                "site_key": key,
                "success": False,
                "outcome": "failed",
                "new_count": 0,
                "updated_count": 0,
                "last_attempt_at": datetime.now(timezone.utc).isoformat(),
                "last_success_at": previous.get("last_success_at"),
                "error": None,
            }
            try:
                cursor = 0
                while True:
                    page = api_request(site, cursor=cursor)
                    if (
                        not isinstance(page, dict)
                        or set(page) != {"items", "next_cursor"}
                        or not isinstance(page["items"], list)
                    ):
                        raise InboxError("protocol", "Feedback API returned an invalid page")
                    rows = [_record(row, site_key=key) for row in page["items"]]
                    ids = [row["id"] for row in rows]
                    next_cursor = page["next_cursor"]
                    if ids != sorted(set(ids)) or any(number <= cursor for number in ids):
                        raise InboxError("protocol", "Feedback API returned unordered page IDs")
                    if next_cursor is not None and (
                        type(next_cursor) is not int or not rows or next_cursor != ids[-1]
                    ):
                        raise InboxError(
                            "protocol", "Feedback API returned an invalid page continuation"
                        )
                    candidate = dict(records)
                    new_count = updated_count = 0
                    for row in rows:
                        old = candidate.get(_key(row))
                        new_count += old is None
                        updated_count += old is not None and old != row
                        candidate[_key(row)] = row
                    _save(root, candidate)
                    records = candidate
                    result["new_count"] += new_count
                    result["updated_count"] += updated_count
                    if next_cursor is None:
                        break
                    cursor = next_cursor
                result.update(
                    success=True,
                    outcome=(
                        "updated"
                        if result["new_count"] or result["updated_count"]
                        else "no_new_data"
                    ),
                    last_success_at=datetime.now(timezone.utc).isoformat(),
                )
            except InboxError as exc:
                result["error"] = exc.payload()
            state["sites"][key] = result
            payload["sites"].append(result)
            try:
                _write_report(root, records, state["sites"].values())
                _atomic_write(
                    root / "sync.json", json.dumps(state, ensure_ascii=False, indent=2) + "\n"
                )
            except InboxError as exc:
                result.update(
                    success=False,
                    outcome="failed",
                    last_success_at=previous.get("last_success_at"),
                    error=exc.payload(),
                )
                # Error evidence is best effort; failed storage must not skip the next site.
                try:
                    _atomic_write(
                        root / "sync.json", json.dumps(state, ensure_ascii=False, indent=2) + "\n"
                    )
                except InboxError:
                    pass
                try:
                    _write_report(root, records, state["sites"].values())
                except InboxError:
                    pass
    failures = [result for result in payload["sites"] if not result["success"]]
    if failures:
        payload.update(
            success=False, outcome="partial_failure" if len(failures) < len(sites) else "failed"
        )
        return EXIT_CODES[failures[0]["error"]["code"]]
    payload["outcome"] = (
        "updated"
        if any(result["outcome"] == "updated" for result in payload["sites"])
        else "no_new_data"
    )
    return 0


def _mark(root, sites, args, payload):
    try:
        feedback_id = str(UUID(args.feedback_id))
    except ValueError as exc:
        raise InboxError("config", "mark requires a feedback UUID") from exc
    with _lock(root):
        records = _load(root)
        sync_sites = _sync_state(root)["sites"].values()
        report_path = root / "inbox.md"
        try:
            prior_report = report_path.read_bytes()
        except FileNotFoundError:
            prior_report = None
        except OSError as exc:
            raise InboxError("local_read", "Cannot read local feedback report before mark") from exc
        matches = [
            row
            for row in records.values()
            if row["feedback_id"] == feedback_id
            and (args.site_key is None or row["site_key"] == args.site_key)
        ]
        if not matches:
            raise InboxError(
                "not_found",
                "Feedback is not in local history; pull first or select the correct site",
            )
        if len(matches) != 1:
            raise InboxError("config", "Feedback ID exists on multiple sites; specify --site-key")
        site = next((site for site in sites if site["site_key"] == matches[0]["site_key"]), None)
        if site is None:
            raise InboxError("config", "Configure the retained feedback site's management endpoint")
        record = _record(
            api_request(site, feedback_id=feedback_id, status=args.status),
            site_key=site["site_key"],
        )
        if record["feedback_id"] != feedback_id:
            raise InboxError("protocol", "Feedback API returned a different feedback ID")
        records[_key(record)] = record
        # Commit canonical status last, so a report failure cannot change local status.
        _write_report(root, records, sync_sites)
        try:
            _save(root, records)
        except InboxError:
            if prior_report is None:
                try:
                    report_path.unlink(missing_ok=True)
                except OSError as exc:
                    raise InboxError("local_write", "Cannot restore local feedback report") from exc
            else:
                _atomic_write(report_path, prior_report)
            raise
        payload.update(items=[record], outcome="marked")
    return 0


def run_command(args):
    payload = {
        "schema_version": 1,
        "command": args.feedback_cmd,
        "success": True,
        "outcome": "listed",
        "items": [],
        "sites": [],
        "error": None,
    }
    try:
        config = load_sites_config(args.config)
        root = resolve_data_root(config) / "feedback"
        if args.feedback_cmd == "list":
            payload["items"] = [
                row
                for row in _ordered(_load(root))
                if (args.site_key is None or row["site_key"] == args.site_key)
                and (args.status is None or row["status"] == args.status)
            ]
            payload["sites"] = list(_sync_state(root)["sites"].values())
            code = 0
        elif args.feedback_cmd == "pull":
            code = _pull(root, _sites(config), payload)
        else:
            code = _mark(root, _sites(config), args, payload)
    except (InboxError, SitesConfigError) as exc:
        error = (
            exc
            if isinstance(exc, InboxError)
            else InboxError("config", "Cannot load authoritative inbox configuration")
        )
        payload.update(success=False, outcome="failed", error=error.payload())
        code = EXIT_CODES[error.code]
    if args.json_output:
        print(json.dumps(payload))
    elif args.feedback_cmd == "list" and payload["success"]:
        print("\n".join(_sync_lines(payload["sites"])))
        for row in payload["items"]:
            print(
                f"{row['site_key']} / {row['feedback_id']} [{row['status']}]\n{json.dumps(row, ensure_ascii=False, indent=2)}"
            )
        if not payload["items"]:
            print("No locally cached feedback")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def add_parser(subparsers):
    parser = subparsers.add_parser("feedback", help="Pull and manage the local feedback inbox")
    commands = parser.add_subparsers(dest="feedback_cmd", required=True)
    for name, help_text in (
        ("pull", "Fresh scan of server status=new; never changes server status"),
        ("list", "Read local cached history without contacting a server"),
        ("mark", "Change server status using feedback.manage; cache its authoritative response"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument(
            "--json", dest="json_output", action="store_true", help="Emit contract v1 JSON"
        )
        if name in {"list", "mark"}:
            command.add_argument("--site-key", help="Exact configured site identity")
            command.add_argument(
                "--status",
                choices=["reviewed", "closed"] if name == "mark" else ["new", "reviewed", "closed"],
                required=name == "mark",
            )
        if name == "mark":
            command.add_argument("feedback_id", help="Feedback UUID from local history")
        command.set_defaults(func=run_command)
