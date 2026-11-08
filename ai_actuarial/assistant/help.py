from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

HELP_ROOT = Path(__file__).resolve().parents[2] / "docs" / "help"
MAX_RESULTS = 10
MAX_SNIPPET_LENGTH = 280
HELP_ID_PATTERN = r"[a-z0-9][a-z0-9-]{0,63}"
HELP_FILES = frozenset({"user-guide.en.md", "user-guide.zh.md"})
_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)
_HEADING = re.compile(r"^##\s+(.+?)\s+\{#([a-z0-9][a-z0-9-]*)\}\s*$", re.MULTILINE)
_WORD = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
# shortcut: curated corpus words, expand when another function-word-only false match appears.
_EN_STOPWORDS = frozenset(
    "a an and are as at be by can cannot could did do does for from how i in is it may of on or "
    "the to was were what when where which with you your about after another but has have if its "
    "not one only s some that their then those this while yet tell something system".split()
)


class HelpIndexError(ValueError):
    pass


@dataclass(frozen=True)
class HelpSection:
    doc_id: str
    section_id: str
    section_title: str
    language: str
    title: str
    source_version: str
    content_hash: str
    content: str

    def reference(self) -> dict[str, str]:
        return {
            "doc_id": self.doc_id,
            "section_id": self.section_id,
            "language": self.language,
            "title": self.title,
            "source_version": self.source_version,
            "content_hash": self.content_hash,
        }


def _tokens(text: str) -> set[str]:
    lowered = text.casefold()
    tokens = set(_WORD.findall(lowered))
    for run in _CJK.findall(lowered):
        tokens.update(run[index : index + 2] for index in range(len(run) - 1))
        tokens.update(run[index : index + 3] for index in range(len(run) - 2))
    return tokens


def _parse_doc(path: Path) -> list[HelpSection]:
    text = path.read_text(encoding="utf-8")
    match = _FRONT_MATTER.fullmatch(text)
    if not match:
        raise HelpIndexError(f"Malformed help metadata: {path.name}")
    metadata: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if not separator or key.strip() in metadata:
            raise HelpIndexError(f"Malformed help metadata: {path.name}")
        metadata[key.strip()] = value.strip().strip("\"'")
    if set(metadata) != {"doc_id", "language", "title", "source_version"}:
        raise HelpIndexError(f"Invalid help metadata fields: {path.name}")
    if not all(metadata.values()) or metadata["language"] not in {"en", "zh"}:
        raise HelpIndexError(f"Invalid help metadata values: {path.name}")
    if (
        not re.fullmatch(HELP_ID_PATTERN, metadata["doc_id"])
        or len(metadata["title"]) > 160
        or len(metadata["source_version"]) > 40
    ):
        raise HelpIndexError(f"Invalid help metadata values: {path.name}")

    body = match.group(2)
    headings = list(_HEADING.finditer(body))
    if len(re.findall(r"^##\s+.+$", body, re.MULTILINE)) != len(headings):
        raise HelpIndexError(f"Malformed help section heading: {path.name}")
    if not headings:
        raise HelpIndexError(f"Help document has no sections: {path.name}")
    sections: list[HelpSection] = []
    for index, heading in enumerate(headings):
        content = body[
            heading.end() : headings[index + 1].start() if index + 1 < len(headings) else len(body)
        ].strip()
        if not content:
            raise HelpIndexError(f"Help section has no content: {path.name}#{heading.group(2)}")
        section_id = heading.group(2)
        if not re.fullmatch(HELP_ID_PATTERN, section_id):
            raise HelpIndexError(f"Invalid help section ID: {path.name}#{section_id}")
        sections.append(
            HelpSection(
                **metadata,
                section_id=section_id,
                section_title=heading.group(1),
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                content=content,
            )
        )
    return sections


def load_help_sections(root: Path = HELP_ROOT) -> list[HelpSection]:
    """Reload only the approved top-level Markdown files on every request."""
    if not root.is_dir():
        return []
    sections: list[HelpSection] = []
    seen_docs: set[str] = set()
    seen_sections: set[tuple[str, str]] = set()
    resolved_root = root.resolve()
    for path in sorted(root.iterdir()):
        if path.name not in HELP_FILES:
            continue
        if path.is_symlink() or not path.is_file() or path.resolve().parent != resolved_root:
            raise HelpIndexError(f"Help file must be a regular file inside docs/help: {path.name}")
        doc_sections = _parse_doc(path)
        doc_id = doc_sections[0].doc_id
        if doc_id in seen_docs:
            raise HelpIndexError(f"Duplicate help doc_id: {doc_id}")
        seen_docs.add(doc_id)
        for section in doc_sections:
            key = (section.doc_id, section.section_id)
            if key in seen_sections:
                raise HelpIndexError(f"Duplicate help section: {key[0]}#{key[1]}")
            seen_sections.add(key)
            sections.append(section)
    return sections


def search_help(
    query: str, *, language: str | None = None, limit: int = 5, root: Path = HELP_ROOT
) -> list[dict[str, object]]:
    query_tokens = _tokens(query) - _EN_STOPWORDS
    if not query_tokens:
        return []
    ranked: list[tuple[int, int, HelpSection]] = []
    for section in load_help_sections(root):
        if language and section.language != language:
            continue
        tokens = _tokens(f"{section.title} {section.section_title} {section.content}")
        score = len(query_tokens & tokens)
        if score:
            ranked.append((score, len(query_tokens & _tokens(section.section_title)), section))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2].doc_id, item[2].section_id))
    return [
        {
            **section.reference(),
            "snippet": section.content[:MAX_SNIPPET_LENGTH],
        }
        for _score, _heading_score, section in ranked[: max(1, min(limit, MAX_RESULTS))]
    ]
