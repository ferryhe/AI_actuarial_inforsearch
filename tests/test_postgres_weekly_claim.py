from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import psycopg2
import pytest

from ai_actuarial.postgres import initialize_postgresql_schema, postgresql_schema_status
from ai_actuarial.storage import Storage


def _new_schema_url(base_url: str, *, prefix: str) -> tuple[str, str]:
    schema = f"{prefix}_{uuid4().hex}"
    admin = psycopg2.connect(base_url)
    admin.autocommit = True
    with admin.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA "{schema}"')
    admin.close()

    parsed = urlsplit(base_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["options"] = f"-c search_path={schema}"
    database_url = urlunsplit(parsed._replace(query=urlencode(query).replace("+", "%20")))
    return schema, database_url


def _drop_schema(base_url: str, schema: str) -> None:
    admin = psycopg2.connect(base_url)
    admin.autocommit = True
    with admin.cursor() as cursor:
        cursor.execute(f'DROP SCHEMA "{schema}" CASCADE')
    admin.close()


def _test_url() -> str:
    base_url = os.getenv("POSTGRES_TEST_URL") or os.getenv("DATABASE_URL")
    if not base_url:
        pytest.fail("POSTGRES_TEST_URL is required for PostgreSQL integration tests")
    return base_url


def test_postgresql_schema_initialization_is_serialized_across_connections():
    base_url = _test_url()
    schema, database_url = _new_schema_url(base_url, prefix="test_schema_race")
    barrier = threading.Barrier(2)

    def initialize():
        barrier.wait(timeout=10)
        initialize_postgresql_schema(database_url)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(initialize) for _ in range(2)]
            for future in futures:
                future.result(timeout=30)
        assert postgresql_schema_status(database_url)["state"] == "current"
    finally:
        _drop_schema(base_url, schema)


def test_first_weekly_explanation_claim_is_atomic_across_connections(
    monkeypatch: pytest.MonkeyPatch,
):
    base_url = _test_url()
    schema, database_url = _new_schema_url(base_url, prefix="test_weekly_claim")
    storage = Storage(database_url)
    contender = Storage(database_url)
    snapshot_id = "weekly-concurrent-first-claim"
    storage.publish_weekly_snapshot(
        {
            "id": snapshot_id,
            "period_start": "2026-10-01",
            "period_end": "2026-10-07",
            "file_count": 0,
        },
        members=[],
    )
    barrier = threading.Barrier(2)
    local = threading.local()
    get_explanation = Storage.get_weekly_explanation

    def wait_after_both_initial_reads(self, *, snapshot_id: str):
        result = get_explanation(self, snapshot_id=snapshot_id)
        if result is None and not getattr(local, "waited", False):
            local.waited = True
            barrier.wait(timeout=10)
        return result

    monkeypatch.setattr(Storage, "get_weekly_explanation", wait_after_both_initial_reads)
    attempt = {
        "snapshot_id": snapshot_id,
        "input_fingerprint": "fingerprint-v1",
        "provider": "fixture",
        "model": "fixture",
        "prompt_version": "weekly-v1",
    }

    def claim(database: Storage):
        return database.claim_weekly_explanation(attempt, lease_ttl_seconds=60)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(claim, (storage, contender)))
        assert sorted(result["state"] for result in results) == ["busy", "claimed"]
        winner = next(result for result in results if result["state"] == "claimed")
        loser = next(result for result in results if result["state"] == "busy")
        assert winner["claim_token"]
        assert loser["claim_token"] == ""
        assert loser["explanation"]["claim_token"] == winner["claim_token"]
    finally:
        storage.close()
        contender.close()
        _drop_schema(base_url, schema)


def test_same_fingerprint_claim_cannot_reclaim_after_complete_finalization(
    monkeypatch: pytest.MonkeyPatch,
):
    base_url = _test_url()
    schema, database_url = _new_schema_url(base_url, prefix="test_weekly_claim_complete_race")
    seed = Storage(database_url)
    contender = Storage(database_url)
    owner = Storage(database_url)
    snapshot_id = "weekly-complete-race"
    seed.publish_weekly_snapshot(
        {
            "id": snapshot_id,
            "period_start": "2026-10-01",
            "period_end": "2026-10-07",
            "file_count": 0,
        },
        members=[],
    )
    attempt = {
        "snapshot_id": snapshot_id,
        "input_fingerprint": "fingerprint-v1",
        "provider": "fixture",
        "model": "fixture",
        "prompt_version": "weekly-v1",
    }
    seed_claim = seed.claim_weekly_explanation(attempt, lease_ttl_seconds=60)
    assert seed_claim["state"] == "claimed"
    failed = seed.finalize_weekly_explanation(
        {**attempt, "status": "failed", "error": "seed failure"},
        claim_token=seed_claim["claim_token"],
    )
    assert failed["finalized"] is True

    initial_read_complete = threading.Event()
    resume_contender = threading.Event()
    first_read = [True]
    original_get = contender.get_weekly_explanation

    def pause_after_read(*, snapshot_id: str):
        current = original_get(snapshot_id=snapshot_id)
        if first_read[0]:
            first_read[0] = False
            assert current is not None
            assert current["status"] == "failed"
            assert current["claim_token"] == ""
            initial_read_complete.set()
            assert resume_contender.wait(timeout=10)
        return current

    monkeypatch.setattr(contender, "get_weekly_explanation", pause_after_read)
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        contender_future = executor.submit(
            contender.claim_weekly_explanation, attempt, lease_ttl_seconds=60
        )
        assert initial_read_complete.wait(timeout=10)
        owner_claim = owner.claim_weekly_explanation(attempt, lease_ttl_seconds=60)
        assert owner_claim["state"] == "claimed"
        owner_finalized = owner.finalize_weekly_explanation(
            {
                **attempt,
                "explanation_zh": "完成",
                "explanation_en": "Complete",
                "status": "complete",
                "error": "",
            },
            claim_token=owner_claim["claim_token"],
        )
        assert owner_finalized["finalized"] is True
        resume_contender.set()
        contender_result = contender_future.result(timeout=10)
        persisted = owner.get_weekly_explanation(snapshot_id=snapshot_id)
    finally:
        resume_contender.set()
        executor.shutdown(wait=True)
        seed.close()
        contender.close()
        owner.close()
        _drop_schema(base_url, schema)

    assert contender_result["state"] == "complete"
    assert contender_result["claim_token"] == ""
    assert contender_result["explanation"]["status"] == "complete"
    assert persisted is not None
    assert persisted["status"] == "complete"
    assert persisted["claim_token"] == ""
