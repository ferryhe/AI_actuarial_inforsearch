from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from ai_actuarial.api.app import create_app
from ai_actuarial.storage import Storage

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


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
        for subject, credential in (
            ("guest-preview", guest_credential),
            ("read-only-preview", read_only_credential),
        ):
            storage.upsert_auth_token_by_hash(
                subject=subject,
                group_name="guest",
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
        "guest_credential": guest_credential,
        "read_only_credential": read_only_credential,
        "db_path": str(db_path),
    }


def _headers(credential: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {credential}"}


def test_guest_can_get_inline_raw_preview_without_download_permission(tmp_path: Path, monkeypatch) -> None:
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
    assert response.headers["cache-control"] == "no-store"

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


def test_raw_preview_rejects_unauthenticated_requests(tmp_path: Path, monkeypatch) -> None:
    client, seed = _build_client(tmp_path, monkeypatch)

    response = client.get("/api/rag/files/preview/raw", params={"file_url": seed["file_url"]})

    assert response.status_code == 401


def test_file_preview_uses_raw_preview_url_instead_of_download_url() -> None:
    source = (Path(__file__).parents[1] / "client" / "src" / "pages" / "FilePreview.tsx").read_text(
        encoding="utf-8"
    )
    pdf_viewer = source.split("function PdfViewer", 1)[1].split("const PDFJS_SCRIPT_URL", 1)[0]
    image_viewer = source.split("function ImageViewer", 1)[1].split("function OriginalPane", 1)[0]

    assert "/api/rag/files/preview/raw?file_url=" in pdf_viewer
    assert "/api/rag/files/preview/raw?file_url=" in image_viewer
    assert "/api/download" not in pdf_viewer
    assert "/api/download" not in image_viewer
