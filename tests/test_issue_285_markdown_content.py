import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_ROOT = REPO_ROOT / "client" / "src"
MARKDOWN_COMPONENT = CLIENT_ROOT / "components" / "MarkdownContent.tsx"
MARKDOWN_COMPONENT_TEST = CLIENT_ROOT / "components" / "MarkdownContent.test.tsx"
CHAT_TSX = CLIENT_ROOT / "pages" / "Chat.tsx"
FILE_DETAIL_TSX = CLIENT_ROOT / "pages" / "FileDetail.tsx"
NATIVE_FILE_DETAIL_TSX = CLIENT_ROOT / "pages" / "NativeFileDetail.tsx"
FILE_PREVIEW_TSX = CLIENT_ROOT / "pages" / "FilePreview.tsx"
NPM_COMMAND = "npm.cmd" if os.name == "nt" else "npm"


def test_shared_markdown_component_has_fixed_safe_contract():
    src = MARKDOWN_COMPONENT.read_text(encoding="utf-8")

    assert 'import ReactMarkdown' in src
    assert 'import remarkGfm from "remark-gfm"' in src
    assert 'import remarkBreaks from "remark-breaks"' in src
    assert "const REMARK_PLUGINS" in src
    assert "const MARKDOWN_COMPONENTS" in src
    assert "skipHtml" in src
    assert "urlTransform={transformMarkdownUrl}" in src
    assert 'disallowedElements={DISALLOWED_ELEMENTS}' in src
    assert 'const DISALLOWED_ELEMENTS = ["img"]' in src
    assert "memo(MarkdownContentImpl)" in src
    assert "dangerouslySetInnerHTML" not in src
    assert "rehypeRaw" not in src
    assert "rehype-raw" not in src
    assert "highlight.js" not in src
    assert "...props" not in src


def test_chat_and_file_detail_share_markdown_without_crossing_structured_ui_boundaries():
    chat = CHAT_TSX.read_text(encoding="utf-8")
    detail = FILE_DETAIL_TSX.read_text(encoding="utf-8")

    assert 'import { MarkdownContent } from "@/components/MarkdownContent";' in chat
    assert 'import { MarkdownContent } from "@/components/MarkdownContent";' in detail
    assert "const MessageBubble = memo(function MessageBubble" in chat
    assert "isUser ? message.content : <MarkdownContent content={message.content} />" in chat
    assert "!isUser && message.citations" in chat
    assert "!isUser && <RetrievedBlocks" in chat
    assert "!isUser && <AgenticTrace" in chat
    assert "function MarkdownRenderer" not in detail
    assert "<MarkdownContent content={markdownContent}" in detail
    assert "MarkdownContent" not in NATIVE_FILE_DETAIL_TSX.read_text(encoding="utf-8")
    assert "MarkdownContent" not in FILE_PREVIEW_TSX.read_text(encoding="utf-8")


def test_markdown_component_runtime_fixtures():
    completed = subprocess.run(
        [NPM_COMMAND, "exec", "--", "tsx", str(MARKDOWN_COMPONENT_TEST)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "MarkdownContent component assertions passed" in completed.stdout
