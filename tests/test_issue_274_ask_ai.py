from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "client" / "src"
TSX = ROOT / "node_modules" / ".bin" / ("tsx.cmd" if os.name == "nt" else "tsx")


def _run_typescript(script: str) -> None:
    wrapped = f"""
    (async () => {{
    {textwrap.dedent(script)}
    }})().catch((error) => {{
      console.error(error);
      process.exitCode = 1;
    }});
    """
    completed = subprocess.run(
        [str(TSX), "-"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        input=textwrap.dedent(wrapped),
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_ask_ai_url_category_matrix_and_one_shot_runtime_contracts() -> None:
    _run_typescript(
        """
        const assert = (await import("node:assert/strict")).default;
        const navigationImport = await import("./client/src/lib/navigation.ts");
        const kbImport = await import("./client/src/lib/chat-knowledge-bases.ts");
        const routeImport = await import("./client/src/pages/chat/routeTarget.ts");
        const navigation = navigationImport.default || navigationImport;
        const kbHelpers = kbImport.default || kbImport;
        const routeHelpers = routeImport.default || routeImport;
        const {
          buildAskAiChatPath,
          getAskAiChatTargetKey,
          parseAskAiChatTarget,
        } = navigation;
        const { findDedicatedCategoryKnowledgeBaseId } = kbHelpers;
        const { resolveAskAiRouteInitialization } = routeHelpers;

        const exactKbId = "KB / A&B?中文";
        const path = buildAskAiChatPath(exactKbId);
        const parsedUrl = new URL(path, "https://app.test");
        assert.equal(parsedUrl.pathname, "/chat");
        assert.equal(parsedUrl.searchParams.get("kb_id"), exactKbId);
        assert.equal(parsedUrl.searchParams.get("rag_mode"), "agentic");
        assert.deepEqual(parseAskAiChatTarget(parsedUrl.search), {
          kbId: exactKbId,
          ragMode: "agentic",
        });
        assert.throws(() => buildAskAiChatPath("   "));

        for (const invalidSearch of [
          "",
          "?kb_id=&rag_mode=agentic",
          "?kb_id=%20%20&rag_mode=agentic",
          "?kb_id=A",
          "?rag_mode=agentic",
          "?kb_id=A&kb_id=B&rag_mode=agentic",
          "?kb_id=A&rag_mode=agentic&rag_mode=standard",
          "?kb_id=A&rag_mode=standard",
          "?kb_id=A&rag_mode=AGENTIC",
          "?kb_id=A&rag_mode=agentic&manifest_profile=general",
          "?kb_id=%E0%A4%A&rag_mode=agentic",
        ]) {
          assert.equal(parseAskAiChatTarget(invalidSearch), null, invalidSearch);
        }

        const categorized = [
          { kb_id: "A-only", categories: ["A"] },
          { kb_id: "A-shared", categories: ["A", "B"] },
          { kb_id: "C-one", categories: ["C"] },
          { kb_id: "C-two", categories: ["C"] },
          { kb_id: "D-unavailable", categories: ["D"] },
          { kb_id: "E-case", categories: ["E"] },
          { kb_id: "F-only", categories: [" F ", "F"] },
        ];
        const chatKbs = [
          { kb_id: "A-only", usable: true },
          { kb_id: "A-shared", usable: true },
          { kb_id: "C-one", usable: true },
          { kb_id: "C-two", usable: true },
          { kb_id: "D-unavailable", usable: false },
          { kb_id: "E-case", usable: true },
          { kb_id: "F-only" },
        ];
        assert.equal(findDedicatedCategoryKnowledgeBaseId("A", categorized, chatKbs), "A-only");
        assert.equal(findDedicatedCategoryKnowledgeBaseId("B", categorized, chatKbs), null);
        assert.equal(findDedicatedCategoryKnowledgeBaseId("C", categorized, chatKbs), null);
        assert.equal(findDedicatedCategoryKnowledgeBaseId("D", categorized, chatKbs), null);
        assert.equal(findDedicatedCategoryKnowledgeBaseId("e", categorized, chatKbs), null);
        assert.equal(findDedicatedCategoryKnowledgeBaseId(" F ", categorized, chatKbs), "F-only");
        assert.equal(findDedicatedCategoryKnowledgeBaseId("missing", categorized, chatKbs), null);

        const targetA = parseAskAiChatTarget("?kb_id=A-only&rag_mode=agentic");
        const targetF = parseAskAiChatTarget("?kb_id=F-only&rag_mode=agentic");
        assert.ok(targetA && targetF);
        let initialized = resolveAskAiRouteInitialization({
          target: targetA,
          knowledgeBases: [],
          knowledgeBasesLoaded: false,
          processedTargetKey: null,
        });
        assert.deepEqual(initialized, { processedTargetKey: null, selection: null });

        initialized = resolveAskAiRouteInitialization({
          target: targetA,
          knowledgeBases: chatKbs,
          knowledgeBasesLoaded: true,
          processedTargetKey: initialized.processedTargetKey,
        });
        assert.equal(initialized.processedTargetKey, getAskAiChatTargetKey(targetA));
        assert.deepEqual(initialized.selection, {
          ragMode: "agentic",
          selectedKbs: ["A-only"],
        });

        const sameTargetAfterUserChange = resolveAskAiRouteInitialization({
          target: targetA,
          knowledgeBases: chatKbs,
          knowledgeBasesLoaded: true,
          processedTargetKey: initialized.processedTargetKey,
        });
        assert.equal(sameTargetAfterUserChange.selection, null);

        const newTarget = resolveAskAiRouteInitialization({
          target: targetF,
          knowledgeBases: chatKbs,
          knowledgeBasesLoaded: true,
          processedTargetKey: sameTargetAfterUserChange.processedTargetKey,
        });
        assert.deepEqual(newTarget.selection?.selectedKbs, ["F-only"]);

        for (const unavailableTarget of [
          parseAskAiChatTarget("?kb_id=unknown&rag_mode=agentic"),
          parseAskAiChatTarget("?kb_id=D-unavailable&rag_mode=agentic"),
        ]) {
          assert.ok(unavailableTarget);
          const rejected = resolveAskAiRouteInitialization({
            target: unavailableTarget,
            knowledgeBases: chatKbs,
            knowledgeBasesLoaded: true,
            processedTargetKey: null,
          });
          assert.equal(rejected.selection, null);
          assert.equal(rejected.processedTargetKey, getAskAiChatTargetKey(unavailableTarget));
        }

        const rearmed = resolveAskAiRouteInitialization({
          target: null,
          knowledgeBases: chatKbs,
          knowledgeBasesLoaded: true,
          processedTargetKey: newTarget.processedTargetKey,
        });
        assert.equal(rearmed.processedTargetKey, null);
        assert.deepEqual(resolveAskAiRouteInitialization({
          target: targetA,
          knowledgeBases: chatKbs,
          knowledgeBasesLoaded: true,
          processedTargetKey: rearmed.processedTargetKey,
        }).selection?.selectedKbs, ["A-only"]);
        """
    )


def test_ask_ai_entry_points_permissions_and_i18n_source_contracts() -> None:
    chat = (CLIENT / "pages" / "Chat.tsx").read_text(encoding="utf-8")
    knowledge = (CLIENT / "pages" / "Knowledge.tsx").read_text(encoding="utf-8")
    detail = (CLIENT / "pages" / "KBDetail.tsx").read_text(encoding="utf-8")
    categories = (CLIENT / "pages" / "Categories.tsx").read_text(encoding="utf-8")
    i18n = (CLIENT / "hooks" / "use-i18n.ts").read_text(encoding="utf-8")

    for source in (knowledge, detail, categories):
        assert 'permissions.includes("chat.view") && permissions.includes("chat.query")' in source
        assert "buildAskAiChatPath" in source
        assert 't("common.ask_ai")' in source
        assert "disabled={!" in source

    assert 'data-testid={`button-ask-ai-kb-${kbId}`}' in knowledge
    assert 'data-testid="button-ask-ai-kb-detail"' in detail
    assert categories.count("button-ask-ai-category-") == 1
    assert 'apiGet<KnowledgeBasesResponse>("/api/rag/knowledge-bases")' in categories
    assert "findDedicatedCategoryKnowledgeBaseId" in categories
    assert "fetchChatKnowledgeBases" in knowledge
    assert "fetchChatKnowledgeBases" in detail
    assert "fetchChatKnowledgeBases" in categories

    assert "parseAskAiChatTarget(rawSearch)" in chat
    assert "resolveAskAiRouteInitialization" in chat
    initialization_effect = chat[
        chat.index("const initialization = resolveAskAiRouteInitialization"):
        chat.index("async function loadDocumentCategories")
    ]
    assert "setRagMode(initialization.selection.ragMode)" in initialization_effect
    assert "setSelectedKbs(initialization.selection.selectedKbs)" in initialization_effect
    assert "sendMessage" not in initialization_effect
    assert "createConversation" not in initialization_effect
    assert "manifest_profile: agenticProfile" not in chat
    assert "profile: agenticProfile" not in chat

    for key in (
        "common.ask_ai",
        "common.ask_ai_unavailable",
        "categories.ask_ai_unavailable",
    ):
        assert i18n.count(f'"{key}"') == 2
    assert '"common.ask_ai": "Ask AI"' in i18n
    assert '"common.ask_ai": "问 AI"' in i18n
