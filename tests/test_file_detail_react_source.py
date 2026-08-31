import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "client" / "src"
FILE_DETAIL_TSX = ROOT / "pages" / "FileDetail.tsx"
FILE_PREVIEW_TSX = ROOT / "pages" / "FilePreview.tsx"
NATIVE_FILE_DETAIL_TSX = ROOT / "pages" / "NativeFileDetail.tsx"
LATEST_REQUEST_HOOK_TS = ROOT / "hooks" / "use-latest-request.ts"
REPO_ROOT = Path(__file__).resolve().parents[1]
NPM_COMMAND = "npm.cmd" if os.name == "nt" else "npm"


def test_file_detail_ai_explain_passes_loaded_markdown_to_chat():
    src = FILE_DETAIL_TSX.read_text(encoding="utf-8")

    assert "function explainCurrentFile()" in src
    assert 'navigate("/chat"' in src
    assert "document_content: markdown.markdown_content" in src
    assert "file_url: file.url" in src
    assert "filename," in src
    assert "title: file.title || filename" in src
    assert "category: file.category || \"\"" in src
    assert "keywords: file.keywords || []" in src
    assert 'data-testid="button-ai-explain"' in src
    assert "disabled={!canExplain}" in src


def test_file_detail_renders_markdown_with_shared_renderer():
    src = FILE_DETAIL_TSX.read_text(encoding="utf-8")

    assert 'import { MarkdownContent } from "@/components/MarkdownContent";' in src
    assert "function MarkdownRenderer" not in src
    assert "<MarkdownContent content={markdownContent}" in src
    assert '<pre className="whitespace-pre-wrap text-sm font-sans">{markdown?.markdown_content}</pre>' not in src


def test_file_detail_uses_permission_gates_for_mutating_actions():
    src = FILE_DETAIL_TSX.read_text(encoding="utf-8")

    assert "FILE_DELETION_AUTH_TOKEN" not in src
    assert "setStoredAuthToken" not in src
    assert "window.prompt" not in src
    assert "const { permissions } = useAuth()" in src
    assert 'permissions.includes("files.download")' in src
    assert 'permissions.includes("files.delete")' in src
    assert 'permissions.includes("catalog.write")' in src
    assert 'permissions.includes("markdown.write")' in src
    assert 'permissions.includes("tasks.run")' in src
    assert 'permissions.includes("rag.write")' not in src


def test_file_detail_chunk_modal_runs_fixed_chunk_embedding_pair_without_kb_options():
    src = FILE_DETAIL_TSX.read_text(encoding="utf-8")

    assert "body.profile_id = chunkProfileId" in src
    assert 'type: "embedding_generation"' in src
    assert "chunk_set_ids" in src
    assert 'data-testid="select-file-chunk-profile"' in src
    assert "body.kb_id" not in src
    assert "binding_mode" not in src
    assert "overwrite_same_profile" not in src
    assert '.filter((chunkSet) => chunkSet.status === "ready"' in src


def test_file_detail_chunk_generation_does_not_prompt_for_legacy_auth_token():
    src = FILE_DETAIL_TSX.read_text(encoding="utf-8")

    assert "chunk_auth_token_prompt" not in src
    assert "setStoredAuthToken" not in src
    assert "window.prompt" not in src


def test_file_preview_passes_download_permission_to_original_pane():
    src = FILE_PREVIEW_TSX.read_text(encoding="utf-8")

    assert "function OriginalPane({ fileInfo, canDownload }" in src
    assert "canDownload={canDownload}" in src


def test_file_routes_parse_raw_browser_search_without_changing_encoded_url_identity():
    file_urls = [
        "https://example.com/a%20b.pdf",
        "https://example.com/report%28final%29.pdf",
        "https://example.com/research%26pricing.pdf",
        "https://example.com/INVITACIO%CC%81N.pdf",
        "https://example.com/a+b.pdf",
    ]
    script = """
import { buildFileDetailPath, buildFilePreviewPath, getRawSearchParams } from './client/src/lib/navigation.ts';
const fileUrls = JSON.parse(process.argv[1]);
for (const fileUrl of fileUrls) {
  for (const [route, key] of [
    [buildFileDetailPath(fileUrl), 'url'],
    [buildFilePreviewPath(fileUrl), 'file_url'],
  ]) {
    globalThis.window = { location: { search: route.slice(route.indexOf('?')) } };
    const actual = getRawSearchParams().get(key);
    if (actual !== fileUrl) throw new Error(`${actual} !== ${fileUrl}`);
  }
}
"""

    result = subprocess.run(
        [NPM_COMMAND, "exec", "--", "tsx", "-e", script, json.dumps(file_urls)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_file_detail_and_preview_pages_use_raw_browser_search():
    for path in (FILE_DETAIL_TSX, FILE_PREVIEW_TSX, NATIVE_FILE_DETAIL_TSX):
        src = path.read_text(encoding="utf-8")

        assert "useRawSearchParams" in src
        assert "useSearch" not in src


def test_raw_search_hook_reacts_to_same_path_query_navigation():
    file_url_a = "https://example.com/A%20%28one%29%26INVITACIO%CC%81N+a.pdf"
    file_url_b = "https://example.com/B%20%28two%29%26INVITACIO%CC%81N+b.pdf"
    script = """
(async () => {
const fileUrlA = process.argv[1];
const fileUrlB = process.argv[2];
const events = new EventTarget();
globalThis.window = events;
globalThis.addEventListener = events.addEventListener.bind(events);
globalThis.removeEventListener = events.removeEventListener.bind(events);
globalThis.dispatchEvent = events.dispatchEvent.bind(events);
globalThis.location = { pathname: '/file-detail', search: '' };
globalThis.history = {
  state: null,
  pushState(state, _unused, to) {
    this.state = state;
    const next = new URL(String(to), 'https://app.example');
    location.pathname = next.pathname;
    location.search = next.search;
  },
  replaceState(state, unused, to) { this.pushState(state, unused, to); },
};

const React = await import('react');
const internals = React.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE;
let subscription;
let render;
internals.H = {
  useSyncExternalStore(subscribe, getSnapshot) {
    subscription ||= subscribe(() => render());
    return getSnapshot();
  },
};

const navigation = await import('./client/src/lib/navigation.ts');
const { useRawSearchParams } = navigation.default || navigation;
function verifySamePathQueryNavigation(path, key) {
  location.pathname = path;
  location.search = `?${key}=${encodeURIComponent(fileUrlA)}`;
  const observed = [];
  render = () => observed.push(useRawSearchParams().get(key));
  render();
  history.pushState(null, '', `${path}?${key}=${encodeURIComponent(fileUrlB)}`);
  if (observed[0] !== fileUrlA) throw new Error(`${path} initial identity changed: ${observed[0]}`);
  if (observed.at(-1) !== fileUrlB) throw new Error(`${path} query navigation did not resolve B: ${observed.at(-1)}`);
}

verifySamePathQueryNavigation('/file-detail', 'url');
verifySamePathQueryNavigation('/file-preview', 'file_url');
})().catch((error) => { console.error(error); process.exitCode = 1; });
"""

    result = subprocess.run(
        [NPM_COMMAND, "exec", "--", "tsx", "-e", script, file_url_a, file_url_b],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_query_navigation_reloads_detail_preview_and_native_detail():
    detail_src = FILE_DETAIL_TSX.read_text(encoding="utf-8")
    preview_src = FILE_PREVIEW_TSX.read_text(encoding="utf-8")
    native_src = NATIVE_FILE_DETAIL_TSX.read_text(encoding="utf-8")

    assert "const searchParams = useRawSearchParams();" in detail_src
    assert "}, [beginFileRequest, fileUrl]);" in detail_src
    assert "}, [beginMarkdownRequest, fileUrl]);" in detail_src
    assert "}, [beginChunksRequest, fileUrl]);" in detail_src
    assert "useEffect(() => { fetchFile(); }, [fetchFile]);" in detail_src
    assert "`/api/files/detail?url=${encodeURIComponent(requestIdentity)}`" in detail_src
    assert "const searchParams = useRawSearchParams();" in preview_src
    assert "}, [beginPreviewRequest, fileUrl]);" in preview_src
    assert "useEffect(() => { fetchPreview(initialChunkSetId); }, [fetchPreview, initialChunkSetId]);" in preview_src
    assert "const params = new URLSearchParams({ file_url: requestIdentity });" in preview_src
    assert "`/api/rag/files/preview?${params}`" in preview_src
    assert "const params = useRawSearchParams();" in native_src
    assert "}, [fileUrl]);" in native_src
    assert "`/api/files/detail?url=${encodeURIComponent(fileUrl)}`" in native_src


def test_latest_request_guard_rejects_deferred_stale_success_error_and_finally():
    script = """
(async () => {
const React = await import('react');
const internals = React.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE;
const refs = [];
let refIndex = 0;
internals.H = {
  useRef(initialValue) {
    const index = refIndex++;
    refs[index] ||= { current: initialValue };
    return refs[index];
  },
  useCallback(callback) { return callback; },
  useEffect() {},
};

const hooks = await import('./client/src/hooks/use-latest-request.ts');
const { useLatestRequestGuard } = hooks.default || hooks;
function render(identity) {
  refIndex = 0;
  return useLatestRequestGuard(identity);
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

async function run(request, state, beginRequest, requestIdentity) {
  const isLatest = beginRequest(requestIdentity);
  state.loading = true;
  state.error = null;
  try {
    const result = await request.promise;
    if (isLatest()) state.value = result;
  } catch (error) {
    if (isLatest()) state.error = error.message;
  } finally {
    if (isLatest()) state.loading = false;
  }
}

const staleSuccessState = { value: null, error: null, loading: false };
const successA = deferred();
const successB = deferred();
const beginSuccessA = render('A');
const runSuccessA = run(successA, staleSuccessState, beginSuccessA, 'A');
const beginSuccessB = render('B');
const runSuccessB = run(successB, staleSuccessState, beginSuccessB, 'B');
successB.resolve('B');
await runSuccessB;
successA.resolve('A');
await runSuccessA;
if (JSON.stringify(staleSuccessState) !== JSON.stringify({ value: 'B', error: null, loading: false })) {
  throw new Error(`stale A success/finally overwrote B: ${JSON.stringify(staleSuccessState)}`);
}

const staleErrorState = { value: null, error: null, loading: false };
const errorA = deferred();
const errorB = deferred();
const beginErrorA = render('A');
const runErrorA = run(errorA, staleErrorState, beginErrorA, 'A');
const beginErrorB = render('B');
const runErrorB = run(errorB, staleErrorState, beginErrorB, 'B');
errorB.resolve('B');
await runErrorB;
errorA.reject(new Error('A failed'));
await runErrorA;
if (JSON.stringify(staleErrorState) !== JSON.stringify({ value: 'B', error: null, loading: false })) {
  throw new Error(`stale A error/finally overwrote B: ${JSON.stringify(staleErrorState)}`);
}
})().catch((error) => { console.error(error); process.exitCode = 1; });
"""

    result = subprocess.run(
        [NPM_COMMAND, "exec", "--", "tsx", "-e", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_latest_request_guard_rejects_stale_callbacks_that_start_after_navigation():
    script = """
(async () => {
const React = await import('react');
const internals = React.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE;
const refs = [];
let refIndex = 0;
internals.H = {
  useRef(initialValue) {
    const index = refIndex++;
    refs[index] ||= { current: initialValue };
    return refs[index];
  },
  useCallback(callback) { return callback; },
  useEffect() {},
};

const hooks = await import('./client/src/hooks/use-latest-request.ts');
const { useLatestRequestGuard } = hooks.default || hooks;
refIndex = 0;
const beginA = useLatestRequestGuard('A');
refIndex = 0;
const beginB = useLatestRequestGuard('B');
const state = { value: null, error: null, loading: false };
let requestsStarted = 0;

async function run(beginRequest, requestIdentity, outcome) {
  const isLatest = beginRequest(requestIdentity);
  if (!isLatest()) return;
  requestsStarted += 1;
  state.loading = true;
  state.error = null;
  try {
    if (outcome instanceof Error) throw outcome;
    if (isLatest()) state.value = outcome;
  } catch (error) {
    if (isLatest()) state.error = error.message;
  } finally {
    if (isLatest()) state.loading = false;
  }
}

await run(beginB, 'B', 'B');
const afterB = JSON.stringify(state);

// Old poller and chunk-completion closures both start only after B completed.
await run(beginA, 'A', 'poller A');
await run(beginA, 'A', new Error('chunk A failed'));

if (requestsStarted !== 1) throw new Error(`stale A callback started a request: ${requestsStarted}`);
if (JSON.stringify(state) !== afterB) {
  throw new Error(`late-start stale A success/error/finally overwrote B: ${JSON.stringify(state)}`);
}
})().catch((error) => { console.error(error); process.exitCode = 1; });
"""

    result = subprocess.run(
        [NPM_COMMAND, "exec", "--", "tsx", "-e", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_file_detail_and_preview_guard_every_query_dependent_request_state():
    detail_src = FILE_DETAIL_TSX.read_text(encoding="utf-8")
    preview_src = FILE_PREVIEW_TSX.read_text(encoding="utf-8")
    hook_src = LATEST_REQUEST_HOOK_TS.read_text(encoding="utf-8")

    assert "identityRef.current === requestIdentity" in hook_src
    assert "generationRef.current === generation" in hook_src
    for request_name in ("File", "Markdown", "Chunks"):
        assert f"const begin{request_name}Request = useLatestRequestGuard(fileUrl);" in detail_src
    assert "const beginChunkSubmission = useLatestRequestGuard(fileUrl);" in detail_src
    assert detail_src.count("if (!requestIdentity || !isLatest()) return;") >= 3
    assert "const isLatest = beginChunkSubmission(requestIdentity);" in detail_src
    assert "if (isLatest()) setChunkSubmitting(false);" in detail_src
    assert detail_src.count("if (!isLatest()) return;") >= 3
    assert "if (isLatest()) setLoading(false);" in detail_src
    assert "if (isLatest()) setMarkdown(null);" in detail_src
    assert "if (isLatest()) setMdLoading(false);" in detail_src
    assert "if (isLatest()) setChunkSets([]);" in detail_src
    assert "if (isLatest()) setChunkSetsLoading(false);" in detail_src

    assert "const beginPreviewRequest = useLatestRequestGuard(fileUrl);" in preview_src
    assert "const isLatest = beginPreviewRequest(requestIdentity);" in preview_src
    assert "if (!isLatest()) return;" in preview_src
    assert "if (isLatest()) setLoading(false);" in preview_src
