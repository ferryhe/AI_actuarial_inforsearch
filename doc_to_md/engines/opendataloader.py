"""Engine adapter for the OpenDataLoader PDF parser."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from config.settings import get_settings
from doc_to_md.engines.base import Engine, EngineAsset, EngineResponse


class OpenDataLoaderEngine(Engine):
    """Convert PDFs to Markdown with opendataloader-pdf.

    OpenDataLoader requires Java 11+ on PATH. The Python package itself remains
    optional and is imported only when this engine is selected.
    """

    name = "opendataloader"

    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        self._hybrid = settings.opendataloader_hybrid
        self._use_struct_tree = settings.opendataloader_use_struct_tree
        self.model = model or (f"opendataloader-hybrid:{self._hybrid}" if self._hybrid else "opendataloader")

    def _ensure_java(self) -> None:
        if shutil.which("java") is None:
            raise RuntimeError(
                "OpenDataLoader engine requires Java 11+ but `java` was not found on PATH."
            )
        result = subprocess.run(
            ["java", "-version"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "OpenDataLoader engine requires a working Java runtime, but "
                f"`java -version` failed with exit code {result.returncode}."
            )
        version_output = result.stderr or result.stdout
        match = re.search(r'"(\d+)(?:\.(\d+))?', version_output)
        if not match:
            raise RuntimeError(f"Could not determine Java version from: {version_output}")
        major = int(match.group(1))
        effective = int(match.group(2) or "0") if major == 1 else major
        if effective < 11:
            raise RuntimeError(f"OpenDataLoader engine requires Java 11+, but Java {effective} was found.")

    @staticmethod
    def _ensure_package() -> None:
        try:
            import opendataloader_pdf  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "OpenDataLoader engine requires `opendataloader-pdf`. Install it with `pip install opendataloader-pdf`."
            ) from exc

    def convert(self, path: Path) -> EngineResponse:  # pragma: no cover - heavy optional dependency
        self._ensure_java()
        self._ensure_package()
        import opendataloader_pdf  # type: ignore

        if path.suffix.lower() != ".pdf":
            raise ValueError(f"OpenDataLoader engine only supports PDF files; got '{path.suffix}'.")

        with tempfile.TemporaryDirectory(prefix="opendataloader_") as temp_dir:
            convert_kwargs: dict[str, object] = {
                "input_path": [str(path)],
                "output_dir": temp_dir,
                "format": "markdown",
            }
            if self._hybrid:
                convert_kwargs["hybrid"] = self._hybrid
            if self._use_struct_tree:
                convert_kwargs["use_struct_tree"] = True

            opendataloader_pdf.convert(**convert_kwargs)

            output_root = Path(temp_dir)
            expected_md = output_root / f"{path.stem}.md"
            if expected_md.is_file():
                md_path = expected_md
            else:
                md_files = sorted(output_root.rglob("*.md"))
                if not md_files:
                    raise RuntimeError("OpenDataLoader did not produce a Markdown file.")
                if len(md_files) > 1:
                    raise RuntimeError(
                        "OpenDataLoader produced multiple Markdown files; cannot determine which one to use."
                    )
                md_path = md_files[0]

            markdown = md_path.read_text(encoding="utf-8")
            assets: list[EngineAsset] = []
            for asset_path in output_root.rglob("*"):
                if asset_path.is_file() and asset_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
                    assets.append(EngineAsset(filename=asset_path.name, data=asset_path.read_bytes(), subdir="images"))

        return EngineResponse(markdown=markdown, model=self.model, assets=assets)
