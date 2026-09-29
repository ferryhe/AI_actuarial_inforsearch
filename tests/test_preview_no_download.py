from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from ai_actuarial.api.app import create_app
from ai_actuarial.storage import Storage

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\0" * 4


def _build_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, dict[str, str]]:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    db_path = tmp_path / "index.db"
    config_path = tmp_path / "sites.yaml"
    categories_path = tmp_path / "categories.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "paths": {
                    "db": str(db_path),
                    "download_dir": str(files_dir),
                    "updates_dir": str(tmp_path / "updates"),
                    "last_run_new": str(tmp_path / "last_run_new.json"),
                },
                "defaults": {
                    "user_agent": "test-agent/1.0",
                    "max_pages": 10,
                    "max_depth": 1,
                    "file_exts": [".pdf", ".docx"],
                },
                "system": {"file_deletion_enabled": True},
                "sites": [],
                "scheduled_tasks": [],
            }
        ),
        encoding="utf-8",
    )
    categories_path.write_text("categories: {}\n", encoding="utf-8")

    pdf_path = files_dir / "preview.pdf"
    pdf_path.write_bytes(PDF_BYTES)
    file_url = "https://example.test/preview.pdf"
    guest_credential = "guest-preview-credential"
    read_only_credential = "read-only-preview-credential"
    admin_credential = "admin-preview-credential"
    storage = Storage(str(db_path))
    try:
        storage.insert_file(
            url=file_url,
            sha256=hashlib.sha256(PDF_BYTES).hexdigest(),
            title="Preview document",
            source_site="example.test",
            source_page_url="https://example.test",
            original_filename=pdf_path.name,
            local_path=str(pdf_path),
            bytes=len(PDF_BYTES),
            content_type="application/pdf",
        )
        png_path = files_dir / "preview.png"
        png_path.write_bytes(PNG_BYTES)
        storage.insert_file(
            url="https://example.test/preview.png",
            sha256=hashlib.sha256(PNG_BYTES).hexdigest(),
            title="Preview image",
            source_site="example.test",
            source_page_url="https://example.test",
            original_filename=png_path.name,
            local_path=str(png_path),
            bytes=len(PNG_BYTES),
            content_type="image/png",
        )
        for subject, credential, group_name in (
            ("guest-preview", guest_credential, "guest"),
            ("read-only-preview", read_only_credential, "guest"),
            ("admin-preview", admin_credential, "admin"),
        ):
            storage.upsert_auth_token_by_hash(
                subject=subject,
                group_name=group_name,
                token_hash=hashlib.sha256(credential.encode("utf-8")).hexdigest(),
                is_active=True,
            )
    finally:
        storage.close()

    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("CATEGORIES_CONFIG_PATH", str(categories_path))
    monkeypatch.setenv("FASTAPI_SESSION_SECRET", "preview-test-session-secret")
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    return TestClient(create_app()), {
        "file_url": file_url,
        "image_url": "https://example.test/preview.png",
        "guest_credential": guest_credential,
        "read_only_credential": read_only_credential,
        "admin_credential": admin_credential,
        "db_path": str(db_path),
    }


def _headers(credential: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {credential}"}


def test_guest_can_get_inline_raw_preview_without_download_permission(
    tmp_path: Path, monkeypatch
) -> None:
    client, seed = _build_client(tmp_path, monkeypatch)

    response = client.get(
        "/api/rag/files/preview/raw",
        params={"file_url": seed["file_url"]},
        headers=_headers(seed["guest_credential"]),
    )

    assert response.status_code == 200, response.text
    assert response.content == PDF_BYTES
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    download = client.get(
        "/api/download",
        params={"url": seed["file_url"]},
        headers=_headers(seed["guest_credential"]),
    )
    assert download.status_code == 403


def test_authenticated_read_only_user_can_get_raw_preview_but_not_download(
    tmp_path: Path, monkeypatch
) -> None:
    client, seed = _build_client(tmp_path, monkeypatch)
    headers = _headers(seed["read_only_credential"])

    preview = client.get(
        "/api/rag/files/preview/raw", params={"file_url": seed["file_url"]}, headers=headers
    )
    download = client.get("/api/download", params={"url": seed["file_url"]}, headers=headers)

    assert preview.status_code == 200, preview.text
    assert download.status_code == 403


def test_anonymous_can_preview_but_cannot_download(tmp_path: Path, monkeypatch) -> None:
    client, seed = _build_client(tmp_path, monkeypatch)

    preview = client.get("/api/rag/files/preview/raw", params={"file_url": seed["file_url"]})
    download = client.get("/api/download", params={"url": seed["file_url"]})

    assert preview.status_code == 200, preview.text
    assert preview.headers["content-disposition"].startswith("inline;")
    assert download.status_code == 401


def test_guest_can_preview_inline_png(tmp_path: Path, monkeypatch) -> None:
    client, seed = _build_client(tmp_path, monkeypatch)

    response = client.get(
        "/api/rag/files/preview/raw",
        params={"file_url": seed["image_url"]},
        headers=_headers(seed["guest_credential"]),
    )

    assert response.status_code == 200
    assert response.content == PNG_BYTES
    assert response.headers["content-type"].startswith("image/png")
    assert response.headers["content-disposition"].startswith("inline;")


def test_raw_preview_rejects_unknown_and_mismatched_file_types(tmp_path: Path, monkeypatch) -> None:
    client, seed = _build_client(tmp_path, monkeypatch)
    storage = Storage(seed["db_path"])
    try:
        storage._conn.execute(
            "UPDATE files SET original_filename = ? WHERE url = ?",
            ("preview.svg", seed["file_url"]),
        )
        storage._conn.commit()
    finally:
        storage.close()

    unsupported = client.get(
        "/api/rag/files/preview/raw",
        params={"file_url": seed["file_url"]},
        headers=_headers(seed["guest_credential"]),
    )
    assert unsupported.status_code == 415

    storage = Storage(seed["db_path"])
    try:
        storage._conn.execute(
            "UPDATE files SET original_filename = ? WHERE url = ?",
            ("preview.png", seed["file_url"]),
        )
        storage._conn.commit()
    finally:
        storage.close()

    mismatched = client.get(
        "/api/rag/files/preview/raw",
        params={"file_url": seed["file_url"]},
        headers=_headers(seed["guest_credential"]),
    )
    assert mismatched.status_code == 415


def test_raw_preview_rejects_deleted_file(tmp_path: Path, monkeypatch) -> None:
    client, seed = _build_client(tmp_path, monkeypatch)
    storage = Storage(seed["db_path"])
    try:
        storage._conn.execute(
            "UPDATE files SET deleted_at = ? WHERE url = ?",
            ("2026-09-29T00:00:00Z", seed["file_url"]),
        )
        storage._conn.commit()
    finally:
        storage.close()

    response = client.get(
        "/api/rag/files/preview/raw",
        params={"file_url": seed["file_url"]},
        headers=_headers(seed["guest_credential"]),
    )

    assert response.status_code == 404
    assert str(tmp_path) not in response.text


def test_raw_preview_rejects_path_outside_managed_data_root(tmp_path: Path, monkeypatch) -> None:
    client, seed = _build_client(tmp_path, monkeypatch)
    outside_path = tmp_path.parent / f"{tmp_path.name}-outside.pdf"
    outside_path.write_bytes(PDF_BYTES)
    storage = Storage(seed["db_path"])
    try:
        storage._conn.execute(
            "UPDATE files SET local_path = ? WHERE url = ?",
            (str(outside_path), seed["file_url"]),
        )
        storage._conn.commit()
    finally:
        storage.close()

    response = client.get(
        "/api/rag/files/preview/raw",
        params={"file_url": seed["file_url"]},
        headers=_headers(seed["guest_credential"]),
    )

    assert response.status_code == 403
    assert str(outside_path) not in response.text


def test_raw_preview_supports_head_and_ranges_and_rejects_invalid_range(
    tmp_path: Path, monkeypatch
) -> None:
    client, seed = _build_client(tmp_path, monkeypatch)
    headers = _headers(seed["guest_credential"])

    head = client.head(
        "/api/rag/files/preview/raw", params={"file_url": seed["file_url"]}, headers=headers
    )
    ranged = client.get(
        "/api/rag/files/preview/raw",
        params={"file_url": seed["file_url"]},
        headers={**headers, "Range": "bytes=0-4"},
    )
    invalid_range = client.get(
        "/api/rag/files/preview/raw",
        params={"file_url": seed["file_url"]},
        headers={**headers, "Range": "bytes=999-1000"},
    )

    assert head.status_code == 200
    assert head.content == b""
    assert int(head.headers["content-length"]) == len(PDF_BYTES)
    assert ranged.status_code == 206
    assert ranged.content == PDF_BYTES[:5]
    assert ranged.headers["content-range"] == f"bytes 0-4/{len(PDF_BYTES)}"
    assert invalid_range.status_code == 416
    assert invalid_range.headers["content-range"] == f"bytes */{len(PDF_BYTES)}"


def test_admin_can_preview_and_download(tmp_path: Path, monkeypatch) -> None:
    client, seed = _build_client(tmp_path, monkeypatch)
    headers = _headers(seed["admin_credential"])

    preview = client.get(
        "/api/rag/files/preview/raw", params={"file_url": seed["file_url"]}, headers=headers
    )
    download = client.get("/api/download", params={"url": seed["file_url"]}, headers=headers)

    assert preview.status_code == 200
    assert preview.headers["content-disposition"].startswith("inline;")
    assert download.status_code == 200
    assert download.content == PDF_BYTES
    assert download.headers["content-disposition"].startswith("attachment;")


def test_file_preview_uses_raw_preview_url_instead_of_download_url() -> None:
    source = (Path(__file__).parents[1] / "client" / "src" / "pages" / "FilePreview.tsx").read_text(
        encoding="utf-8"
    )
    pdf_viewer = source.split("function PdfViewer", 1)[1].split("const PDFJS_SCRIPT_URL", 1)[0]
    image_viewer = source.split("function ImageViewer", 1)[1].split("function OriginalPane", 1)[0]

    assert "/api/rag/files/preview/raw?file_url=" in pdf_viewer
    assert '"X-Auth-Token": authToken' in pdf_viewer
    assert "apiGetBlob(`/api/rag/files/preview/raw?file_url=" in image_viewer
    assert "/api/download" not in pdf_viewer
    assert "/api/download" not in image_viewer
