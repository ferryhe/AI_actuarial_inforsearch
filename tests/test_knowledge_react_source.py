from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "client" / "src" / "pages"
KNOWLEDGE_TSX = ROOT / "Knowledge.tsx"
KB_DETAIL_TSX = ROOT / "KBDetail.tsx"
I18N_TS = ROOT.parent / "hooks" / "use-i18n.ts"
READY_DATA_UI_STATE_TS = ROOT.parent / "lib" / "ready-data-ui-state.ts"


def test_knowledge_pages_surface_reembed_action_for_embedding_mismatch():
    knowledge_src = KNOWLEDGE_TSX.read_text(encoding="utf-8")
    detail_src = KB_DETAIL_TSX.read_text(encoding="utf-8")

    assert "handleReembedKB" in knowledge_src
    assert 'data-testid={`button-reembed-kb-${kbId}`}' in knowledge_src
    assert "kb.needs_reindex || kb.embedding_compatible === false" in knowledge_src

    assert "needsEmbeddingRebuild" in detail_src
    assert 'data-testid="banner-embedding-mismatch"' in detail_src
    assert 'data-testid="button-reembed-current-embedding"' in detail_src


def test_knowledge_create_uses_backend_embedding_configuration_only():
    src = KNOWLEDGE_TSX.read_text(encoding="utf-8")

    assert '"/api/config/ai-models"' not in src
    assert "embeddingModels" not in src
    assert "embedding_model: kbForm" not in src
    assert 'data-testid="select-kb-embedding"' not in src
    assert 'data-testid="text-kb-backend-embedding"' not in src
    assert "currentEmbeddingLabel" not in src
    assert "current_embeddings" in src


def test_knowledge_create_supports_document_and_category_multiselects():
    src = KNOWLEDGE_TSX.read_text(encoding="utf-8")

    assert "/api/rag/files/selectable?" in src
    assert '"/api/rag/categories/mapping"' in src
    assert 'data-testid="kb-document-picker"' in src
    assert 'data-testid="kb-category-picker"' in src
    assert "file_urls: kbForm.kb_mode === \"manual\" ? kbForm.file_urls : []" in src
    assert "categories: kbForm.categories" in src
    assert "toggleKbFile" in src
    assert "toggleKbCategory" in src
    assert 'data-testid="input-kb-categories"' not in src
    assert '"/api/rag/categories/stats"' in src
    assert 'data-testid="kb-category-stats"' in src
    assert 'data-testid="button-submit-kb-index"' in src
    assert "`/api/rag/knowledge-bases/${encodeURIComponent(finalKbId)}/index`" in src


def test_knowledge_create_supports_select_all_and_all_mode():
    src = KNOWLEDGE_TSX.read_text(encoding="utf-8")

    assert '<option value="all">{t("knowledge.mode_all")}</option>' in src
    assert "kbForm.kb_mode === \"all\"" in src
    assert "handleSelectAllKbFiles" in src
    assert 'data-testid="button-select-all-kb-files"' in src
    assert "selectableFiles.every((file) => current.file_urls.includes(file.url))" in src


def test_knowledge_create_surfaces_create_and_index_errors():
    src = KNOWLEDGE_TSX.read_text(encoding="utf-8")

    assert "formatApiErrorDetail" in src
    assert "function formatActionErrorDetail(err: unknown): string" not in src
    assert "kbActionError" in src
    assert "setKbActionError" in src
    assert "kbActionNotice" in src
    assert 'data-testid="alert-kb-action-error"' in src
    assert 'data-testid="alert-kb-action-notice"' in src
    assert 'type="button"' in src
    assert "indexFailed" in src
    assert "knowledge.create_index_partial_error" in src


def test_knowledge_create_uses_existing_chunk_profile_not_inline_chunk_settings():
    src = KNOWLEDGE_TSX.read_text(encoding="utf-8")

    assert 'data-testid="select-kb-chunk-profile"' in src
    assert "chunk_profile_id: kbForm.chunk_profile_id" in src
    assert 'params.set("profile_id", kbForm.chunk_profile_id)' in src
    assert 'data-testid="input-kb-chunk-size"' not in src
    assert 'data-testid="input-kb-chunk-overlap"' not in src
    assert "chunk_size: kbForm.chunk_size" not in src
    assert "chunk_overlap: kbForm.chunk_overlap" not in src


def test_kb_detail_bind_dialog_uses_kb_chunk_profile_and_chunk_bindings():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")

    assert "chunk_profile_id?: string" in src
    assert 'params.set("profile_id", meta.chunk_profile_id)' in src
    assert "chunk_set_id?: string" in src
    assert "`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/bindings`" in src
    assert "bindings: selectedBindFiles.map" in src
    assert "chunk_set_id: file.chunk_set_id" in src
    assert "canBindFiles" in src
    assert "disabled={!canBindFiles}" in src
    assert "if (!canBindFiles) return;" in src


def test_kb_detail_manual_mode_can_add_files_with_select_all_and_category_index_prompt():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")

    assert "formatApiErrorDetail" in src
    assert "function formatActionErrorDetail(err: unknown): string" not in src
    assert "isManualMode" in src
    assert "handleSelectAllBindFiles" in src
    assert 'data-testid="button-select-all-bind-files"' in src
    assert "`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/files`" in src
    assert "file_urls: selectedBindFiles" in src
    assert "meta.kb_mode === \"manual\"" in src
    assert 'data-testid="banner-category-index-required"' in src


def test_knowledge_list_surfaces_agentic_manifest_status_and_build_action():
    src = KNOWLEDGE_TSX.read_text(encoding="utf-8")
    i18n_src = I18N_TS.read_text(encoding="utf-8")
    state_src = READY_DATA_UI_STATE_TS.read_text(encoding="utf-8")

    assert "interface AgenticReadyManifest" not in src
    assert "AgenticReadyManifest" in state_src
    assert "AgenticReadyManifest," in src
    assert "manifest_profile?: string" in src
    assert "agentic_ready_manifest?: AgenticReadyManifest" in src
    assert 'manifest_profile: "general"' in src
    assert "manifest_profile: kbForm.manifest_profile" in src
    assert 'data-testid="select-kb-manifest-profile"' in src
    assert "status: \"missing\" | \"ready\" | \"building\" | \"failed\" | \"stale\"" in state_src
    assert "usable: boolean" in state_src
    assert "fallback_mode?: string" in state_src
    assert "stale_reason?: string" in state_src
    assert "handleBuildAgenticManifest" in src
    assert "validation?: { valid?: boolean; errors?: string[] }" in src
    assert "res.validation?.valid !== false" in src
    assert 't("knowledge.manifest_profile")' in src
    assert 't("knowledge.manifest_profile_hint")' in src
    assert 't("knowledge.manifest_build_completed")' in src
    assert 't("knowledge.manifest_build_not_ready").replace("{detail}", detail)' in src
    assert 't("knowledge.manifest_build_failed")' in src
    assert "getManifestFallbackMessage(manifest, manifestServing, t)" in src
    assert "getManifestActionLabel(manifest, t)" in src
    assert "Agentic manifest profile" not in src
    assert "Agentic manifest build did not produce ready data" not in src
    assert '"knowledge.manifest_profile"' in i18n_src
    assert '"knowledge.manifest_build_not_ready"' in i18n_src
    assert "`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/agentic-ready-manifest/build`" in src
    assert "buildingManifestKb === kbId" in src
    assert 'data-testid={`badge-agentic-manifest-${kbId}`}' in src
    assert 'data-testid={`message-agentic-manifest-${kbId}`}' in src
    assert 'data-testid={`button-build-agentic-manifest-${kbId}`}' in src


def test_kb_detail_surfaces_agentic_manifest_endpoint_status_and_build_action():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")
    i18n_src = I18N_TS.read_text(encoding="utf-8")
    state_src = READY_DATA_UI_STATE_TS.read_text(encoding="utf-8")

    assert "interface AgenticReadyManifest" in state_src
    assert "manifest_profile?: string" in src
    assert "agentic_ready_manifest?: AgenticReadyManifest" in src
    assert "loadAgenticManifest" in src
    assert "`/api/rag/knowledge-bases/${encodeURIComponent(requestRoute.kbId)}/agentic-ready-manifest`" in src
    assert "`/api/rag/knowledge-bases/${encodeURIComponent(mutationKbId)}/agentic-ready-manifest/build`" in src
    assert "handleBuildAgenticManifest" in src
    assert "validation?: { valid?: boolean; errors?: string[] }" in src
    assert "res.validation?.valid !== false" in src
    assert 't("knowledge.manifest_build_completed")' in src
    assert 't("knowledge.manifest_build_not_ready").replace("{detail}", detail)' in src
    assert 't("knowledge.manifest_build_failed")' in src
    assert 't("knowledge.manifest_built")' in src
    assert "getManifestFallbackMessage(manifest, manifestServing, t)" in src
    assert "getManifestActionLabel(manifest, t)" in src
    assert "Agentic manifest build did not produce ready data" not in src
    assert '"knowledge.manifest_built"' in i18n_src
    assert "manifest.profile || meta.manifest_profile" in src
    assert "manifest.doc_count" in src
    assert "manifest.section_count" in src
    assert "manifest.output_dir" not in src
    assert "observed_index_version_id" in src
    assert "current_ready_index_version_id" in src
    assert 'data-testid="panel-agentic-manifest"' in src
    assert 'data-testid="badge-agentic-manifest-detail"' in src
    assert 'data-testid="button-build-agentic-manifest-detail"' in src


def test_kb_detail_closes_ready_data_publication_management_loop():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")
    i18n_src = I18N_TS.read_text(encoding="utf-8")
    state_src = READY_DATA_UI_STATE_TS.read_text(encoding="utf-8")

    assert "publication_state?: ReadyDataPublicationState" in state_src
    assert "automation_state" in state_src
    assert "automatic_build_enabled" in state_src
    assert "automatic_publish_enabled" in state_src
    assert "canManageKnowledge" in src
    assert "canRunKnowledgeTasks" in src
    assert "handleAutomaticBuildChange" in src
    assert "enabled ? Boolean(manifest?.automatic_publish_enabled) : false" in src
    assert "disabled={!manifest?.automatic_build_enabled" in src
    assert "handleRollbackPublication" in src
    assert "expected_active_publication_id" in src
    assert "expected_previous_publication_id" in src
    assert "window.confirm" in src
    assert "status === 409" in src
    assert "setTimeout" in src
    assert "clearTimeout" in src
    assert "observed_index_version_id" in state_src
    assert "current_ready_index_version_id" in state_src
    assert "manifest?.current_ready_index_version_id" in src
    assert "activePublication?.current_ready_index_version_id" in src
    assert "displayValue(currentReadyIndexVersion)" in src
    assert 'previousPublication?.status === "previous"' in src
    assert "index_consumed_by_builder" in state_src
    assert "manifest.output_dir" not in src
    assert 'data-testid="ready-data-serving-status"' in src
    assert 'data-testid="ready-data-automation-status"' in src
    assert 'data-testid="button-rollback-ready-data"' in src
    for key in (
        "knowledge.ready_serving_status",
        "knowledge.ready_automation_status",
        "knowledge.ready_automatic_build",
        "knowledge.ready_automatic_publish",
        "knowledge.ready_rollback",
        "knowledge.ready_authoritative_source",
        "knowledge.ready_observed_index",
        "knowledge.ready_current_index",
    ):
        assert i18n_src.count(f'"{key}"') == 2


def test_kb_detail_always_renders_server_name_as_page_heading():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")

    heading = (
        '<h1 className="text-xl font-serif font-bold tracking-tight" '
        'data-testid="text-kb-name">{meta.name}</h1>'
    )
    assert heading in src
    assert src.index(heading) < src.index("{canManageKnowledge && (")
    assert 'data-testid="text-kb-name-readonly"' not in src
    assert 'data-testid="input-kb-edit-name"' in src


def test_kb_detail_exposes_explicit_ready_publish_confirmation():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")

    assert "agentic-ready-manifest/publish" in src
    assert 'data-testid="button-publish-ready-data"' in src
    assert 'manifestAutomationState === "awaiting_publish"' in src
    assert "last_attempt_publication_id" in src
    assert "expected_active_publication_id" in src
    assert "window.confirm" in src


def test_kb_detail_keeps_ready_build_input_from_dedicated_manifest_get():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")
    state_src = READY_DATA_UI_STATE_TS.read_text(encoding="utf-8")

    assert '"ready_build_input",' in state_src
    assert "const readyBuildInput = manifestResponse.manifest?.ready_build_input;" in src
    assert "agentic-ready-manifest/build" in src
    assert "readyBuildInput," in src
    assert "include_ready_build_input=true" in src


def test_knowledge_list_separates_serving_and_automation_status():
    src = KNOWLEDGE_TSX.read_text(encoding="utf-8")
    detail_src = KB_DETAIL_TSX.read_text(encoding="utf-8")
    state_src = READY_DATA_UI_STATE_TS.read_text(encoding="utf-8")

    assert "automation_state?: string" in state_src
    assert "serving_status?:" in state_src
    assert "serving_usable?: boolean" in state_src
    assert "serving_stale?: boolean" in state_src
    assert "resolveReadyDataServingState" in state_src
    assert "resolveReadyDataOperationState" in state_src
    assert "isReadyDataAutomationBusy" in state_src
    assert "normalizeReadyAutomationStatus" in state_src
    assert "isReadyDataAutomationBusy(manifest)" in src
    assert 'data-testid={`badge-agentic-automation-${kbId}`}' in src
    assert "getServingStatusLabel(manifestServing, t)" in src
    assert "getAutomationStatusLabel(manifestOperation.status, t)" in src
    for page_src in (src, detail_src):
        assert "resolveReadyDataServingState" in page_src
        assert "resolveReadyDataOperationState" in page_src
        assert "readyDataOperationKindTranslationKey" in page_src
        assert "isReadyDataAutomationBusy" in page_src
        assert "function normalizeReadyServingStatus" not in page_src
        assert 't(`knowledge.ready_serving_' not in page_src
        assert 't(`knowledge.ready_automation_' not in page_src
        assert 'case "unavailable":' in page_src
        assert 'case "awaiting_manual_confirmation":' in page_src
        assert 'return t("knowledge.ready_serving_missing")' in page_src
        assert 'return t("knowledge.ready_automation_idle")' in page_src


def test_knowledge_pages_keep_operation_failures_out_of_serving_messages():
    list_src = KNOWLEDGE_TSX.read_text(encoding="utf-8")
    detail_src = KB_DETAIL_TSX.read_text(encoding="utf-8")

    for page_src in (list_src, detail_src):
        assert "const manifestServing = resolveReadyDataServingState(manifest);" in page_src
        assert "getManifestFallbackMessage(manifest, manifestServing, t)" in page_src
        fallback_start = page_src.index("function getManifestFallbackMessage")
        fallback_end = page_src.index("function getManifestActionLabel", fallback_start)
        fallback_src = page_src[fallback_start:fallback_end]
        assert "manifest?.last_error" not in fallback_src
        assert "manifest?.error_message" not in fallback_src
        assert "manifest?.stale_reason" not in fallback_src

    assert 'data-testid={`message-agentic-operation-${kbId}`}' in list_src
    assert 'data-testid="ready-data-last-operation-error"' in detail_src
    for page_src in (list_src, detail_src):
        assert 'manifestStatus === "building"' not in page_src
        assert "getManifestActionLabel(manifest, t)" in page_src
        assert 't("knowledge.ready_operation_status")' in page_src
        assert "t(readyDataOperationKindTranslationKey(manifestOperation.kind))" in page_src

    i18n_src = I18N_TS.read_text(encoding="utf-8")
    for key, english, chinese in (
        ("ready_operation_build", "Build", "构建"),
        ("ready_operation_publish", "Publish", "发布"),
        ("ready_operation_rollback", "Rollback", "回滚"),
    ):
        assert f'"knowledge.{key}": "{english}"' in i18n_src
        assert f'"knowledge.{key}": "{chinese}"' in i18n_src


def test_knowledge_list_bounds_busy_automation_polling_and_deduplicates_loads():
    src = KNOWLEDGE_TSX.read_text(encoding="utf-8")
    detail_src = KB_DETAIL_TSX.read_text(encoding="utf-8")

    assert "READY_DATA_LIST_POLL_INTERVAL_MS" in src
    assert "READY_DATA_LIST_MAX_POLL_ATTEMPTS" in src
    assert "isReadyDataAutomationBusy" in src
    assert "readyDataListBusy" in src
    assert "readyDataListPollAttempts.current" in src
    assert "loadDataInFlight.current" in src
    assert "if (loadDataInFlight.current) return loadDataInFlight.current" in src
    assert "window.setTimeout" in src
    assert "window.clearTimeout" in src
    assert "readyDataListPollAttempts.current >= READY_DATA_LIST_MAX_POLL_ATTEMPTS" in src
    assert "void loadData(false).finally" in src
    assert "isReadyDataAutomationBusy(kb.agentic_ready_manifest)" in src
    assert "if (!isReadyDataAutomationBusy(effectiveManifest))" in detail_src
    assert "if (kbPayload)" in src
    assert "if (profilePayload)" in src
    assert "if (ragCategoriesResp && usedCategoriesResp)" in src
    assert "void loadAgenticManifest({ preserveCurrentOnError: true }).finally" in detail_src


def test_kb_detail_starts_a_fresh_poll_episode_for_each_kb():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")

    route_effect = src.index("manifestMounted.current = true;")
    route_effect_end = src.index("}, [kbId]);", route_effect)
    route_effect_src = src[route_effect:route_effect_end]
    assert "manifestPollAttempts.current = 0;" in route_effect_src
    assert "readyDataRoute.current = syncReadyDataRoute(readyDataRoute.current, kbId);" in route_effect_src
    assert "setManifestPollVersion((current) => current + 1);" in route_effect_src
    assert "setAgenticManifest(null);" in route_effect_src
    assert "selectEffectiveReadyDataManifest(" in src
    assert "agenticManifest," in src
    assert "meta?.kb_id," in src


def test_knowledge_pages_use_fixed_manifest_mode_and_unavailable_messages():
    i18n_src = I18N_TS.read_text(encoding="utf-8")
    state_src = READY_DATA_UI_STATE_TS.read_text(encoding="utf-8")
    for page in (KNOWLEDGE_TSX, KB_DETAIL_TSX):
        src = page.read_text(encoding="utf-8")
        assert 'case "agentic": return t("knowledge.manifest_agentic_mode")' in src
        assert 'case "standard": return t("knowledge.manifest_standard_fallback")' in src
        assert 'return t("knowledge.manifest_unknown_mode")' in src
        assert '"knowledge.manifest_stale_agentic_serving"' in src
        assert 't("knowledge.manifest_unavailable_message")' in src
        assert 'case "unavailable":' in src
        assert 'status: "missing" | "ready" | "building" | "failed" | "stale" | "unavailable"' in state_src
        assert 't(`knowledge.manifest_' not in src

    for key in (
        "knowledge.manifest_agentic_mode",
        "knowledge.manifest_unknown_mode",
        "knowledge.manifest_stale_agentic_serving",
        "knowledge.manifest_unavailable_message",
    ):
        assert i18n_src.count(f'"{key}"') == 2


def test_kb_detail_coordinates_manifest_requests_after_mutations():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")

    assert "manifestRequestSequence.current" in src
    assert "manifestRequestInFlight.current" in src
    assert "manifestMounted.current" in src
    assert "requestId === manifestRequestSequence.current" in src
    assert "if (!force && manifestRequestInFlight.current)" in src
    assert src.count("preserveCurrentOnError: true") >= 4
    assert "manifestMounted.current = false" in src
    assert "manifestRequestSequence.current += 1" in src


def test_kb_detail_preserves_confirmed_mutation_manifest_when_refresh_fails():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")
    i18n_src = I18N_TS.read_text(encoding="utf-8")
    state_src = READY_DATA_UI_STATE_TS.read_text(encoding="utf-8")

    assert "preserveCurrentOnError?: boolean" in src
    assert "readyDataManifestAfterLoad(" in src
    assert "return preserveCurrentOnError ? current : null;" in state_src
    assert "let loaded = false;" in src
    assert "return loaded;" in src
    assert "const refreshed = await loadAgenticManifest({" in src
    assert "force: true," in src
    assert "preserveCurrentOnError: true," in src
    assert 'setActionError(t("knowledge.ready_refresh_failed"))' in src
    assert i18n_src.count('"knowledge.ready_refresh_failed"') == 2
    assert "readyDataRollbackErrorKey(409, refreshed)" in src
    assert i18n_src.count('"knowledge.ready_rollback_conflict_refresh_failed"') == 2


def test_kb_detail_localizes_public_ready_errors_and_smoke_statuses():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")
    i18n_src = I18N_TS.read_text(encoding="utf-8")

    for smoke_status in ("passed", "failed", "not_run", "skipped_empty"):
        assert f'case "{smoke_status}":' in src
        assert f'knowledge.ready_smoke_{smoke_status}' in src
    assert 'return t("knowledge.ready_smoke_unknown")' in src
    assert "getReadyPublicMessageLabel(manifestOperation.error, t)" in src
    assert (
        "getReadySmokeStatusLabel(manifest?.smoke_status ?? "
        "activePublication?.smoke_status, t)" in src
    )
    assert "displayValue(manifest?.last_error)" not in src
    assert "displayValue(activePublication?.smoke_status)" not in src
    assert "{ detail }) : \"\"" not in src

    for key in (
        "knowledge.ready_smoke_passed",
        "knowledge.ready_smoke_failed",
        "knowledge.ready_smoke_not_run",
        "knowledge.ready_smoke_skipped_empty",
        "knowledge.ready_smoke_unknown",
        "knowledge.ready_error_generic",
        "knowledge.ready_error_source_pending",
        "knowledge.ready_error_source_changed",
        "knowledge.ready_error_manual_confirmation",
        "knowledge.ready_error_unavailable",
    ):
        assert i18n_src.count(f'"{key}"') == 2


def test_kb_detail_guards_ready_data_mutations_by_route_epoch():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")
    state_src = READY_DATA_UI_STATE_TS.read_text(encoding="utf-8")

    build_start = src.index("const handleBuildAgenticManifest")
    automation_start = src.index("const updateReadyDataAutomation", build_start)
    publish_start = src.index("const handlePublishReadyData", automation_start)
    rollback_start = src.index("const handleRollbackPublication", publish_start)
    rollback_end = src.index("const handleSearchBindable", rollback_start)
    build_src = src[build_start:automation_start]
    automation_src = src[automation_start:publish_start]
    rollback_src = src[rollback_start:rollback_end]

    for handler_src, loading_reset in (
        (build_src, "setManifestBuilding(false)"),
        (automation_src, "setAutomationSaving(false)"),
        (rollback_src, "setRollbackRunning(false)"),
    ):
        assert "captureReadyDataRoute(readyDataRoute.current, manifestMounted.current, kbId)" in handler_src
        assert "await runReadyDataRouteRequest({" in handler_src
        assert "isCurrent: () => isCurrentReadyDataRoute(mutationKbId, mutationEpoch)" in handler_src
        assert handler_src.count("isCurrentReadyDataRoute(mutationKbId, mutationEpoch)") >= 2
        assert "onSuccess:" in handler_src
        assert "onError:" in handler_src
        assert "onSettled:" in handler_src
        assert "setActionNotice(null);" in handler_src
        assert "setActionError(null);" in handler_src
        assert loading_reset in handler_src

    assert "export function syncReadyDataRoute" in state_src
    assert "export function captureReadyDataRoute" in state_src
    assert "export function isReadyDataRouteCurrent" in state_src
    assert "export async function runReadyDataRouteRequest" in state_src


def test_kb_detail_uses_effective_current_kb_manifest_for_render_and_polling():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")
    state_src = READY_DATA_UI_STATE_TS.read_text(encoding="utf-8")

    assert "const effectiveManifest = selectEffectiveReadyDataManifest(" in src
    assert "if (metaKbId === kbId && nested?.kb_id === kbId) return nested;" in state_src
    assert "isReadyDataAutomationBusy(effectiveManifest)" in src
    assert "const manifest = effectiveManifest;" in src
    assert "agenticManifest?.automation_state," not in src
    assert "shouldPollReadyDataManifest(effectiveManifest" in src


def test_kb_detail_merges_confirmed_automation_before_forced_refresh():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")
    state_src = READY_DATA_UI_STATE_TS.read_text(encoding="utf-8")

    assert "interface ReadyDataAutomationResponse" in state_src
    assert "mergeConfirmedReadyDataAutomation" in src
    assert "request: () => apiPut<ReadyDataAutomationResponse>" in src
    assert "pending_evaluation_generation" in state_src
    assert "pending_generation:" in state_src
    assert "const confirmedManifest = mergeConfirmedReadyDataAutomationForKb(" in src
    assert "applyReadyDataManifestUpdate(" in src
    assert "preserveCurrentOnError: true" in src


def test_kb_detail_localizes_non_conflict_rollback_failures():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")
    i18n_src = I18N_TS.read_text(encoding="utf-8")
    handler_start = src.index("const handleRollbackPublication")
    handler_end = src.index("const handleSearchBindable", handler_start)
    rollback_src = src[handler_start:handler_end]

    assert "readyDataRollbackErrorKey(" in rollback_src
    assert "formatApiErrorDetail" not in rollback_src
    assert i18n_src.count('"knowledge.ready_rollback_failed"') == 2
    assert '"knowledge.ready_rollback_failed": "Ready-data rollback failed."' in i18n_src
    assert '"knowledge.ready_rollback_failed": "Ready-data 回滚失败。"' in i18n_src


def test_kb_detail_guards_every_route_bound_loader_and_profile_fallback():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")
    state_src = READY_DATA_UI_STATE_TS.read_text(encoding="utf-8")
    loader_names = (
        "loadMeta",
        "loadAgenticManifest",
        "loadStats",
        "loadFiles",
        "loadCategories",
        "loadAll",
    )
    for index, loader_name in enumerate(loader_names):
        start = src.index(f"const {loader_name} = useCallback")
        next_start = (
            src.index(f"const {loader_names[index + 1]} = useCallback", start)
            if index + 1 < len(loader_names)
            else src.index("useEffect(() =>", start)
        )
        loader_src = src[start:next_start]
        capture_name = (
            "captureReadyDataRoute("
            if loader_name == "loadAgenticManifest"
            else "captureReadyDataRequest("
        )
        assert capture_name in loader_src
        assert "runReadyDataRouteRequest({" in loader_src
        assert (
            "isCurrent: () => isReadyDataRouteCurrent(" in loader_src
            or "isCurrent: () => isReadyDataRequestCurrent(" in loader_src
            or "isCurrent," in loader_src
        )

    route_effect = src.index("manifestMounted.current = true;")
    route_effect_end = src.index("}, [kbId]);", route_effect)
    route_effect_src = src[route_effect:route_effect_end]
    for reset in (
        "setMeta(null);",
        "setStats(null);",
        "setFiles([]);",
        "setCategories([]);",
        "setUnmappedCategories([]);",
        'setEditName("");',
        'setEditDesc("");',
        "setLoading(true);",
    ):
        assert reset in route_effect_src

    automation_start = src.index("const updateReadyDataAutomation")
    rollback_start = src.index("const handleRollbackPublication", automation_start)
    automation_src = src[automation_start:rollback_start]
    rollback_end = src.index("const handleSearchBindable", rollback_start)
    rollback_src = src[rollback_start:rollback_end]
    assert "selectReadyDataMutationProfile(" in automation_src
    assert "selectReadyDataMutationProfile(" in rollback_src
    assert "effectiveManifest?.profile || meta?.manifest_profile" not in src
    assert "export async function runReadyDataRouteRequest" in state_src
    assert "export function selectReadyDataMutationProfile" in state_src


def test_kb_detail_uses_latest_sequence_for_each_same_route_resource_and_episode():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")
    state_src = READY_DATA_UI_STATE_TS.read_text(encoding="utf-8")

    assert "export function captureReadyDataRequest" in state_src
    assert "export function isReadyDataRequestCurrent" in state_src
    sequence_names = (
        "metaRequestSequence",
        "statsRequestSequence",
        "filesRequestSequence",
        "categoriesRequestSequence",
        "unmappedRequestSequence",
        "loadAllRequestSequence",
    )
    for sequence_name in sequence_names:
        assert f"const {sequence_name} = useRef(0);" in src

    loader_sequences = (
        ("loadMeta", "loadAgenticManifest", "metaRequestSequence"),
        ("loadStats", "loadFiles", "statsRequestSequence"),
        ("loadFiles", "loadCategories", "filesRequestSequence"),
        ("loadCategories", "loadAll", "categoriesRequestSequence"),
        ("loadAll", "useEffect(() =>", "loadAllRequestSequence"),
    )
    for loader_name, next_marker, sequence_name in loader_sequences:
        start = src.index(f"const {loader_name} = useCallback")
        end = src.index(
            (
                f"const {next_marker} = useCallback"
                if not next_marker.startswith("useEffect")
                else next_marker
            ),
            start,
        )
        loader_src = src[start:end]
        assert "captureReadyDataRequest(" in loader_src
        assert "isReadyDataRequestCurrent(" in loader_src
        assert sequence_name in loader_src
    categories_start = src.index("const loadCategories = useCallback")
    categories_end = src.index("const loadAll = useCallback", categories_start)
    categories_src = src[categories_start:categories_end]
    assert "unmappedRequestSequence" in categories_src

    route_effect = src.index("manifestMounted.current = true;")
    route_effect_end = src.index("}, [kbId]);", route_effect)
    route_effect_src = src[route_effect:route_effect_end]
    for sequence_name in sequence_names:
        assert f"{sequence_name}.current += 1;" in route_effect_src


def test_automation_confirmation_uses_latest_functional_manifest_bases():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")
    state_src = READY_DATA_UI_STATE_TS.read_text(encoding="utf-8")
    start = src.index("const updateReadyDataAutomation")
    end = src.index("const handleAutomaticBuildChange", start)
    automation_src = src[start:end]

    assert "mergeConfirmedReadyDataAutomationForKb" in automation_src
    assert "const responseTime = selectResponseTimeReadyDataManifest(mutationKbId)" in automation_src
    assert "const confirmedManifest = mergeConfirmedReadyDataAutomationForKb(" in automation_src
    assert "applyReadyDataManifestUpdate(" in automation_src
    assert "manifestEpisodeVersion" in automation_src
    assert "automationAppliedEpisodeVersion.current" in automation_src
    assert "{ responseTimeMerged: true }" in automation_src
    assert "mergeConfirmedReadyDataAutomation(\n          mutationManifest" not in automation_src
    assert "force: true" in automation_src
    assert "preserveCurrentOnError: true" in automation_src
    assert "export function mergeConfirmedReadyDataAutomationForKb" in state_src
    assert "export function selectReadyDataManifestEpisodeUpdate" in state_src


def test_every_manifest_write_uses_publication_revision_ordering():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")
    state_src = READY_DATA_UI_STATE_TS.read_text(encoding="utf-8")

    assert "publication_revision?: number | null" in state_src
    assert "export function selectReadyDataManifestUpdate" in state_src
    assert "readyDataPublicationRevision" in state_src
    assert "const agenticManifestRef = useRef" in src
    assert "const metaRef = useRef" in src
    assert "selectResponseTimeReadyDataManifest" in src

    build_start = src.index("const handleBuildAgenticManifest")
    automation_start = src.index("const updateReadyDataAutomation", build_start)
    publish_start = src.index("const handlePublishReadyData", automation_start)
    rollback_start = src.index("const handleRollbackPublication", publish_start)
    rollback_end = src.index("const handleSearchBindable", rollback_start)
    build_src = src[build_start:automation_start]
    automation_src = src[automation_start:publish_start]
    rollback_src = src[rollback_start:rollback_end]

    assert "setAgenticManifest(nextManifest)" not in build_src
    assert "setAgenticManifest(responseManifest)" not in rollback_src
    assert "applyReadyDataManifestUpdate(" in build_src
    assert "applyReadyDataManifestUpdate(" in rollback_src
    assert "selectResponseTimeReadyDataManifest(" in automation_src
    assert "mutationManifest," not in automation_src[automation_src.index("onSuccess:"):]

    manifest_loader_start = src.index("const loadAgenticManifest")
    stats_loader_start = src.index("const loadStats", manifest_loader_start)
    manifest_loader_src = src[manifest_loader_start:stats_loader_start]
    assert "applyReadyDataManifestUpdate(" in manifest_loader_src
    assert "manifestEpisodeVersion" in manifest_loader_src

    meta_loader_start = src.index("const loadMeta")
    meta_loader_end = src.index("const loadAgenticManifest", meta_loader_start)
    meta_loader_src = src[meta_loader_start:meta_loader_end]
    assert "applyReadyDataManifestUpdate(" in meta_loader_src
    assert "manifestEpisodeVersion" in meta_loader_src
    assert "scopedCurrent.publication_state" in state_src
    assert "incoming.publication_state" in state_src


def test_build_handlers_and_knowledge_list_use_safe_revision_ordered_snapshots():
    knowledge_src = KNOWLEDGE_TSX.read_text(encoding="utf-8")
    detail_src = KB_DETAIL_TSX.read_text(encoding="utf-8")
    state_src = READY_DATA_UI_STATE_TS.read_text(encoding="utf-8")

    assert "export function mergeReadyDataKnowledgeList" in state_src
    assert "export function mergeReadyDataKnowledgeManifest" in state_src
    assert "setKbs((current) => mergeReadyDataKnowledgeList(" in knowledge_src
    assert "applyReadyDataListManifestEpisode(" in knowledge_src
    assert "mergeReadyDataKnowledgeManifest(" in knowledge_src
    assert "ready_data_snapshot?: { manifest?: AgenticReadyManifest }" in knowledge_src
    assert "const manifest = res.ready_data_snapshot?.manifest" in knowledge_src
    assert "agentic_ready_manifest: manifest," not in knowledge_src

    detail_build_start = detail_src.index("const handleBuildAgenticManifest")
    detail_build_end = detail_src.index("const updateReadyDataAutomation", detail_build_start)
    detail_build_src = detail_src[detail_build_start:detail_build_end]
    assert "ready_data_snapshot?: { manifest?: AgenticReadyManifest }" in detail_build_src
    assert "const nextManifest = res.ready_data_snapshot?.manifest || null" in detail_build_src
    assert "const nextManifest = res.manifest" not in detail_build_src


def test_ready_data_manifest_merging_tracks_dynamic_freshness_and_profile_identity():
    knowledge_src = KNOWLEDGE_TSX.read_text(encoding="utf-8")
    detail_src = KB_DETAIL_TSX.read_text(encoding="utf-8")
    state_src = READY_DATA_UI_STATE_TS.read_text(encoding="utf-8")

    assert "canonicalReadyDataProfile" in state_src
    assert "mergeAuthoritativeReadyDataDynamicState" in state_src
    assert "currentHasPublicProjection && !incomingHasPublicProjection" in state_src
    assert "sameReadyDataManifestProfile" in state_src
    assert "if (!sameReadyDataManifestProfile(scopedCurrent, incoming))" in state_src

    assert "manifestAuthority: ReadyDataManifestAuthority = true" in state_src
    assert "resolveReadyDataManifestEpisode" in state_src
    assert "item.manifest_profile" in state_src
    assert "manifest?.profile || item.manifest_profile" not in state_src

    assert "const readyDataListManifestVersion = useRef(0);" in knowledge_src
    assert "const readyDataListAppliedManifestEpisodes = useRef(" in knowledge_src
    assert "const requestManifestVersion = ++readyDataListManifestVersion.current;" in knowledge_src
    assert "applyReadyDataListManifestEpisode(" in knowledge_src
    assert "const mutationManifestVersion = ++readyDataListManifestVersion.current;" in knowledge_src
    assert "readyDataListAppliedManifestEpisodes.current.set(kbId, decision.applied);" in knowledge_src
    assert "mergeReadyDataKnowledgeList(" in knowledge_src

    assert "selectReadyDataMutationProfile(" in detail_src
    assert "applyReadyDataManifestUpdate(" in detail_src
    assert "manifest?.smoke_status ?? activePublication?.smoke_status" in detail_src


def test_manifest_episode_authority_is_shared_in_detail_and_scoped_per_list_item():
    detail_src = KB_DETAIL_TSX.read_text(encoding="utf-8")
    knowledge_src = KNOWLEDGE_TSX.read_text(encoding="utf-8")
    state_src = READY_DATA_UI_STATE_TS.read_text(encoding="utf-8")

    assert "export function resolveReadyDataManifestEpisode" in state_src
    assert "function compareReadyDataManifestMonotonicFreshness" in state_src
    assert "export function resolveReadyDataSafeMutationManifestEpisode" in state_src
    assert "export interface ReadyDataManifestEpisode" in state_src
    assert "const manifestEpisodeSequence = useRef(0);" in detail_src
    assert "const manifestAppliedEpisode = useRef<ReadyDataManifestEpisode | null>(null);" in detail_src
    assert "const manifestEpisodeVersion = ++manifestEpisodeSequence.current;" in detail_src
    assert detail_src.count("++manifestEpisodeSequence.current") >= 5

    for start_marker, end_marker in (
        ("const loadMeta", "const loadAgenticManifest"),
        ("const loadAgenticManifest", "const loadStats"),
        ("const handleBuildAgenticManifest", "const updateReadyDataAutomation"),
        ("const updateReadyDataAutomation", "const handleAutomaticBuildChange"),
        ("const handleRollbackPublication", "const handleSearchBindable"),
    ):
        start = detail_src.index(start_marker)
        end = detail_src.index(end_marker, start)
        section = detail_src[start:end]
        assert "manifestEpisode" in section
        assert "applyReadyDataManifestUpdate(" in section

    assert "const readyDataListAppliedManifestEpisodes = useRef(" in knowledge_src
    assert "new Map<string, ReadyDataManifestEpisode>()" in knowledge_src
    assert "readyDataListAppliedManifestVersion" not in knowledge_src
    assert "resolveReadyDataManifestEpisode(" in knowledge_src
    assert "manifestAuthorityByKb" in knowledge_src
    assert "(kbId) => manifestAuthorityByKb.get(kbId) ?? false" in knowledge_src

    detail_build = detail_src[
        detail_src.index("const handleBuildAgenticManifest"):
        detail_src.index("const updateReadyDataAutomation")
    ]
    assert "safeMutationSnapshot: true" in detail_build
    assert "resolveReadyDataSafeMutationManifestEpisode(" in detail_src
    knowledge_build = knowledge_src[
        knowledge_src.index("const handleBuildAgenticManifest"):
        knowledge_src.index("const toggleKbCategory")
    ]
    assert "resolveReadyDataSafeMutationManifestEpisode(" in knowledge_src
    assert "currentManifest," in knowledge_build
    assert "true," in knowledge_build
