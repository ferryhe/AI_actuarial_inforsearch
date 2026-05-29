from __future__ import annotations

import sys
import types

from doc_to_md.engines.docling import DoclingEngine


def test_docling_pdf_uses_slim_text_fallback_without_full_model_stack(tmp_path, monkeypatch) -> None:
    pdf_path = tmp_path / "solvency.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    class FakePage:
        def extract_text(self) -> str:
            return "Solvency capital and actuarial governance"

    class FakePdfReader:
        def __init__(self, path: str) -> None:
            assert path == str(pdf_path)
            self.pages = [FakePage()]

    engine = DoclingEngine()
    monkeypatch.setattr(engine, "_full_pdf_pipeline_dependencies_available", lambda: False)
    monkeypatch.setattr(
        engine,
        "_ensure_converter",
        lambda: (_ for _ in ()).throw(AssertionError("Docling full converter should not be used")),
    )
    monkeypatch.setitem(sys.modules, "pypdf", types.SimpleNamespace(PdfReader=FakePdfReader))

    response = engine.convert(pdf_path)

    assert response.model == "docling-slim-text"
    assert "# solvency" in response.markdown
    assert "Solvency capital and actuarial governance" in response.markdown
