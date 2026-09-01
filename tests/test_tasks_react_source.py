from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "client" / "src"
SCHEDULED_TASKS_TSX = ROOT / "pages" / "tasks" / "ScheduledTasksSection.tsx"
SCHEDULE_FROM_TASK_TSX = ROOT / "pages" / "tasks" / "ScheduleFromTaskButton.tsx"
TASKS_TSX = ROOT / "pages" / "Tasks.tsx"
TASK_CARD_TSX = ROOT / "pages" / "tasks" / "TaskCard.tsx"
TASKS_TYPES_TS = ROOT / "pages" / "tasks" / "Tasks.types.ts"
LAYOUT_TSX = ROOT / "components" / "Layout.tsx"


def test_scheduled_tasks_section_uses_native_schedule_status_contract():
    src = SCHEDULED_TASKS_TSX.read_text(encoding="utf-8")

    assert "label?: string" in src
    assert "count?: number" in src
    assert "scheduleStatus.count" in src
    assert "job.label" in src


def test_scheduled_tasks_section_surfaces_write_errors_instead_of_silently_ignoring_them():
    src = SCHEDULED_TASKS_TSX.read_text(encoding="utf-8")

    assert "return formatApiErrorDetail(error) || t(fallbackKey);" in src
    assert "import { ApiError" not in src
    assert "error.detail || error.message" not in src
    assert "errorMsg" in src
    assert 'data-testid="text-scheduled-error"' in src
    assert 'aria-label={t("tasks.schedule.dismiss_error")}' in src
    assert "setErrorMsg" in src


def test_scheduled_tasks_section_does_not_offer_old_full_pipeline_type():
    src = SCHEDULED_TASKS_TSX.read_text(encoding="utf-8")

    assert "scheduledParamFields" in src
    assert "weekly_summary: [" in src
    assert '{ value: "weekly_summary", label: t("tasks.type.weekly_summary") }' in src
    assert "full_pipeline: [" not in src
    assert '{ value: "full_pipeline", label: t("tasks.type.full_pipeline") }' not in src
    assert 'value: "file"' not in src
    assert "data-testid={`input-sched-param-${field.key}`}" in src
    assert 'data-testid="input-sched-params"' in src
    assert 't("tasks.sched.advanced_parameters")' in src
    assert "parseParamsObject(formParams) || {}" in src
    assert "JSON.stringify(params, null, 2)" in src
    assert '{ key: "site", labelKey: "tasks.sched.param.site" }' in src
    assert '{ key: "max_depth", labelKey: "tasks.sched.param.max_depth", type: "number" }' in src
    assert '{ key: "count", labelKey: "tasks.sched.param.count", type: "number" }' in src
    assert '{ key: "urls", labelKey: "tasks.sched.param.urls", type: "textarea"' in src
    assert (
        '{ key: "overwrite_existing", labelKey: "tasks.sched.param.overwrite_existing", type: "boolean" }'
        in src
    )
    assert 'key: "source_dir"' not in src
    assert 'key: "force", labelKey: "tasks.sched.param.force"' not in src
    assert "const nextNumber = Number(trimmed);" in src
    assert "Number.isFinite(nextNumber)" in src
    assert 'value.trim().toLowerCase() === "true"' in src
    assert "url: [" in src
    assert '{ key: "urls", labelKey: "tasks.sched.param.urls", type: "textarea"' in src
    assert '{ key: "query", labelKey: "tasks.sched.param.query" }' in src


def test_add_to_schedule_error_dismiss_button_is_accessible():
    src = SCHEDULE_FROM_TASK_TSX.read_text(encoding="utf-8")

    assert 'return formatApiErrorDetail(error) || t("tasks.sched.save_fail");' in src
    assert "import { ApiError" not in src
    assert "error.detail || error.message" not in src
    assert 'data-testid="text-add-schedule-error"' in src
    assert 'aria-label={t("tasks.schedule.dismiss_error")}' in src


def test_layout_no_longer_renders_fastapi_native_mode_badge():
    src = LAYOUT_TSX.read_text(encoding="utf-8")

    assert "layout.fastapiNativeMode" not in src


def test_tasks_page_has_dedicated_scheduled_tasks_view():
    src = TASKS_TSX.read_text(encoding="utf-8")

    assert 'data-testid="tasks-view-tabs"' in src
    assert 'data-testid="tab-run-tasks"' in src
    assert 'data-testid="tab-scheduled-tasks"' in src
    assert 'taskView === "scheduled"' in src
    assert "<ScheduledTasksSection />" in src


def test_add_to_schedule_uses_current_task_payload_without_manual_params_field():
    src = SCHEDULE_FROM_TASK_TSX.read_text(encoding="utf-8")

    assert "/api/scheduled-tasks/add" in src
    assert "taskParamsFromPayload" in src
    assert "delete params.type" in src
    assert 'data-testid="button-add-to-schedule"' in src
    assert 'testId="input-schedule-task-name"' in src
    assert 'testId="input-schedule-interval"' in src
    assert "input-sched-params" not in src


def test_legacy_collection_forms_expose_add_to_schedule_control():
    form_names = [
        "SiteConfigForm.tsx",
        "WebCrawlForm.tsx",
        "AdhocUrlForm.tsx",
        "FileImportForm.tsx",
        "WebSearchForm.tsx",
        "CatalogForm.tsx",
        "MarkdownForm.tsx",
        "ChunkForm.tsx",
    ]

    for form_name in form_names:
        src = (ROOT / "pages" / "tasks" / form_name).read_text(encoding="utf-8")
        assert "ScheduleFromTaskButton" in src, form_name
        assert "buildTask" in src or "buildCollectionTask" in src, form_name

    rag_src = (ROOT / "pages" / "tasks" / "RagIndexForm.tsx").read_text(encoding="utf-8")
    assert "ScheduleFromTaskButton" not in rag_src


def test_file_import_form_uses_browser_upload_batches_not_server_folder_browser():
    src = (ROOT / "pages" / "tasks" / "FileImportForm.tsx").read_text(encoding="utf-8")
    api_src = (ROOT / "lib" / "api.ts").read_text(encoding="utf-8")
    tasks_src = TASKS_TSX.read_text(encoding="utf-8")

    assert '"/api/files/import-batches"' in src
    assert "apiPostForm" in src
    assert 'data-testid="input-local-files"' in src
    assert 'data-testid="input-local-directory"' in src
    assert "upload_batch_id" in src
    assert "directory_path" not in src
    assert "FolderBrowser" not in src
    assert "FolderBrowser" not in tasks_src
    assert "body instanceof FormData" in api_src
    assert "fileMatchesExtensions" in src
    assert "selectedExtensions" in src
    assert "appendFiles(formData" in src


def test_recommended_markdown_conversion_tools_are_in_frontend_defaults():
    settings_src = (ROOT / "pages" / "settings" / "MarkdownConversionTab.tsx").read_text(
        encoding="utf-8"
    )

    assert '"/api/config/markdown-conversion"' in settings_src
    assert "default_tool" in settings_src
    assert "candidate_chain" in settings_src


def test_task_options_uses_native_ai_config_response_contracts():
    src = (ROOT / "hooks" / "use-task-options.ts").read_text(encoding="utf-8")
    web_search_src = (ROOT / "pages" / "tasks" / "WebSearchForm.tsx").read_text(encoding="utf-8")

    assert "value: e.id || e.value || e.key" in src
    assert "available: e.configured ?? (e.available !== false)" in src
    assert "prov.filter(providerUsable).map(providerName)" in src
    assert "selectedEngineAvailable" in web_search_src
    assert "disabled={submitting || !query.trim() || !selectedEngineAvailable}" in web_search_src


def test_tasks_page_restores_rag_indexing_task_form():
    tasks_src = TASKS_TSX.read_text(encoding="utf-8")
    rag_src = (ROOT / "pages" / "tasks" / "RagIndexForm.tsx").read_text(encoding="utf-8")

    assert 'type: "rag_index"' in tasks_src
    assert 'apiType: "rag_indexing"' in tasks_src
    assert "<RagIndexForm onSubmit={handleSubmitRagIndex} submitting={submitting} />" in tasks_src
    assert "`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/index`" in tasks_src
    assert '"/api/rag/knowledge-bases"' in rag_src
    assert "kb_id: selectedKbId" in rag_src
    assert "force_rebuild: forceRebuild" in rag_src
    assert 'type: "rag_indexing"' not in rag_src
    assert "const [incremental" not in rag_src
    assert "incremental," not in rag_src


def test_tasks_page_orders_markdown_before_catalog_and_links_create_kb():
    src = TASKS_TSX.read_text(encoding="utf-8")

    markdown_pos = src.index('type: "markdown"')
    catalog_pos = src.index('type: "catalog"')
    assert markdown_pos < catalog_pos
    assert 'type: "create_kb"' in src
    assert 'route: "/knowledge?open=create"' in src
    assert "navigate(route)" in src


def test_chunk_form_uses_existing_or_custom_chunk_profiles():
    src = (ROOT / "pages" / "tasks" / "ChunkForm.tsx").read_text(encoding="utf-8")

    assert '"/api/chunk/profiles"' in src
    assert 'testId="select-chunk-profile"' in src
    assert 'value: "__custom__"' in src
    assert "task.profile_id = profileSelection" in src
    assert 'profileSelection === "__custom__"' in src
    assert 'testId="input-chunk-profile"' in src
    assert 'testId="select-bind-kb"' not in src
    assert "binding_mode" not in src
    assert "kb_id" not in src
    assert "overwrite_same_profile" not in src
    assert 'name: "Chunk & Embedding"' in src


def test_markdown_settings_wait_for_async_options_before_replacing_saved_tool():
    src = (ROOT / "pages" / "tasks" / "MarkdownForm.tsx").read_text(encoding="utf-8")

    assert "loading: taskOptionsLoading" in src
    assert "if (taskOptionsLoading) return;" in src
    assert "[conversionToolsInfo, defaultConversionTool, taskOptionsLoading, tool]" in src


def test_task_category_scopes_use_backend_selects_not_free_text_datalists():
    for form_name, test_id in (
        ("CatalogForm.tsx", "select-category"),
        ("MarkdownForm.tsx", "select-md-category"),
        ("ChunkForm.tsx", "select-chunk-category"),
    ):
        src = (ROOT / "pages" / "tasks" / form_name).read_text(encoding="utf-8")
        assert "<datalist" not in src, form_name
        assert 'list="' not in src, form_name
        assert f'testId="{test_id}"' in src, form_name
        assert "categoryOptions" in src, form_name


def test_rag_index_form_uses_only_canonical_full_kb_inputs():
    src = (ROOT / "pages" / "tasks" / "RagIndexForm.tsx").read_text(encoding="utf-8")

    assert "fileUrlsInput" not in src
    assert "file_urls" not in src
    assert "force_reindex:" not in src
    assert "force_rebuild: forceRebuild" in src


def test_tasks_page_exposes_agentic_site_monitoring_form():
    tasks_src = TASKS_TSX.read_text(encoding="utf-8")
    form_src = (ROOT / "pages" / "tasks" / "WebListeningForm.tsx").read_text(encoding="utf-8")

    assert 'type: "web_listening"' in tasks_src
    assert "<WebListeningForm" in tasks_src
    assert '"/api/web-listening/rules/explore"' in form_src
    assert 'data-testid="button-web-listening-explore"' in form_src
    assert 'data-testid="panel-web-listening-exploration"' in form_src
    assert '"/api/web-listening/rules/draft"' in form_src
    assert '"/api/web-listening/rules/validate"' in form_src
    assert '"/api/web-listening/rules/materialize"' in form_src
    assert '"/api/schedule/reinit"' in form_src
    assert "scheduled-tasks:changed" in form_src
    assert 'data-testid="form-web-listening"' in form_src
    assert 'data-testid="checkbox-web-listening-tool-crawler"' in form_src
    assert 'data-testid="checkbox-web-listening-tool-search"' in form_src
    assert 'data-testid="checkbox-web-listening-content-file"' in form_src
    assert 'data-testid="checkbox-web-listening-content-webpage"' in form_src
    assert 'data-testid="input-web-listening-allow-patterns"' in form_src
    assert 'data-testid="input-web-listening-queries"' in form_src
    i18n_src = (ROOT / "hooks" / "use-i18n.ts").read_text(encoding="utf-8")
    assert "scheduled collection task" in i18n_src
    assert "定时采集任务" in i18n_src


def test_site_config_form_manages_agentic_monitoring_strategy():
    form_src = (ROOT / "pages" / "tasks" / "SiteConfigForm.tsx").read_text(encoding="utf-8")

    for test_id in (
        "input-site-goal",
        "button-site-explore",
        "checkbox-site-tool-crawler",
        "checkbox-site-tool-search",
        "checkbox-site-content-file",
        "checkbox-site-content-webpage",
        "input-site-allow-patterns",
        "input-site-queries",
    ):
        assert f'data-testid="{test_id}"' in form_src
    assert 'testId="input-site-file-exts"' in form_src
    assert "acquisition_tools: formTools" in form_src
    assert 'collect_linked_files: formContentTypes.includes("file")' in form_src
    assert 'collect_page_content: formContentTypes.includes("webpage")' in form_src
    assert 'formTools.includes("search") && parseList(formQueries).length === 0' in form_src
    assert 'setFormTools(["crawler"])' in form_src
    assert 's.queries?.length ? ["search"] : []' in form_src
    assert "const [saveError, setSaveError]" in form_src
    assert 'setSaveError(e instanceof Error ? e.message : t("tasks.sites.save_error"))' in form_src
    assert 'data-testid="text-site-save-error"' in form_src
    assert 'setExploreError(e instanceof Error ? e.message : "Failed to save site")' not in form_src
    i18n_src = (ROOT / "hooks" / "use-i18n.ts").read_text(encoding="utf-8")
    assert '"tasks.sites.save_error": "Failed to save site"' in i18n_src
    assert '"tasks.sites.save_error": "保存站点失败"' in i18n_src


def test_web_listening_entry_uses_site_permission_not_tasks_run_only():
    tasks_src = TASKS_TSX.read_text(encoding="utf-8")
    filter_src = (ROOT / "pages" / "tasks" / "FilterBar.tsx").read_text(encoding="utf-8")

    assert 'tt.type === "web_listening"' in tasks_src
    assert "return canManageSites" in tasks_src
    assert "const canShowTaskEntryGrid = visibleTaskTypes.length > 0" in tasks_src
    assert "{canShowTaskEntryGrid ? <div>" in tasks_src
    assert '<option value="rag_indexing">RAG Indexing</option>' in filter_src
    assert '<option value="full_pipeline">Full Pipeline</option>' not in filter_src


def test_tasks_page_exposes_fixed_collapsible_pipeline_baton():
    tasks_src = TASKS_TSX.read_text(encoding="utf-8")
    form_src = (ROOT / "pages" / "tasks" / "PipelineBaton.tsx").read_text(encoding="utf-8")

    assert 'type: "full_pipeline"' not in tasks_src
    assert "FullPipelineForm" not in tasks_src
    assert "PipelineRuns" not in tasks_src
    assert "<PipelineBaton onViewLog={viewPipelineLog} />" in tasks_src
    assert "useState<Set<string>>(new Set())" in form_src
    assert "aria-expanded={expanded.has(step.step)}" in form_src
    for step in ("scheduled", "markdown_conversion", "catalog", "chunk_generation", "rag_indexing"):
        assert f'"pipeline-step-{step}"' in form_src
    assert 'apiGet<PipelineView>("/api/pipeline/status")' in form_src
    assert 'apiPost<PipelineView>("/api/pipeline/start")' in form_src
    assert 'apiPost<PipelineView>("/api/pipeline/config"' in form_src
    assert "<MarkdownForm" in form_src and "settingsMode" in form_src
    assert "<CatalogForm" in form_src
    assert "<ChunkForm" in form_src
    assert "<RagIndexForm" in form_src
    assert 'testId="input-pipeline-scheduled-interval"' in form_src
    assert 'testId="checkbox-pipeline-scheduled-enabled"' in form_src
    assert 'setScheduledInterval(source?.interval || "")' in form_src
    assert "setScheduledEnabled(source?.enabled ?? true)" in form_src
    assert "interval: scheduledInterval.trim()" in form_src
    assert "enabled: scheduledEnabled" in form_src
    assert 'label: "Chunk & Embedding"' in form_src
    assert "task.label || step.label" in form_src
    assert 'subtask?: "kb_index" | "ready_data_build"' in form_src
    assert "binding_mode" not in form_src
    assert "full_reindex" not in form_src
    assert 'rag_indexing: ["incremental", "force_reindex", "kb_id"]' in form_src
    assert "forbiddenFields.has(key)" in form_src
    assert "Number.isFinite(numericValue)" in form_src
    assert "throw new Error(`${key} must be a finite number`)" in form_src
    assert (
        'setError(caught instanceof Error ? caught.message : t("tasks.sched.save_fail"))'
        in form_src
    )
    assert form_src.index("Number.isFinite(numericValue)") < form_src.index(
        'apiPost("/api/scheduled-tasks/update"'
    )
    assert "advanced" not in form_src.lower()


def test_catalog_pipeline_settings_can_save_without_provider_discovery():
    src = (ROOT / "pages" / "tasks" / "CatalogForm.tsx").read_text(encoding="utf-8")

    assert src.count("!settingsMode && catalogProviders.length === 0") >= 2
    assert "!settingsMode && (" not in src


def test_tasks_page_refreshes_history_on_completion_and_exposes_global_logs():
    src = TASKS_TSX.read_text(encoding="utf-8")

    assert "previousActiveTaskIdsRef" in src
    assert "completedTaskIds" in src
    assert "void fetchHistory()" in src
    assert 'window.confirm(t("tasks.confirm_stop"))' in src
    assert 'apiGet<{ logs?: string; error?: string }>("/api/logs/global")' in src
    assert "const refreshLogModal = () =>" in src
    assert 'logModal.taskId === "global"' in src
    assert "void viewGlobalLogs()" in src
    assert 'data-testid="button-global-logs"' in src


def test_tasks_page_has_fixed_pipeline_tab_not_pipeline_runs():
    src = TASKS_TSX.read_text(encoding="utf-8")

    assert 'data-testid="tab-pipeline-baton"' in src
    assert 'data-testid="tab-pipeline-runs"' not in src
    assert 'taskView === "pipeline"' in src
    assert "<PipelineBaton onViewLog={viewPipelineLog} />" in src
    assert 'useState<"run" | "scheduled" | "pipeline">' in src
    assert "viewPipelineLog" in src


def test_pipeline_baton_i18n_keys_added_in_both_locales():
    i18n_src = (ROOT / "hooks" / "use-i18n.ts").read_text(encoding="utf-8")

    for key in (
        "tasks.pipeline.title",
        "tasks.pipeline.start",
        "tasks.pipeline.default_settings",
        "tasks.pipeline.all_indexable_kbs",
        "tasks.pipeline.view_log",
    ):
        assert f'"{key}":' in i18n_src, key
    assert '"tasks.pipeline.title": "Daily Pipeline"' in i18n_src
    assert '"tasks.pipeline.title": "每日流水线"' in i18n_src


def test_status_badge_handles_pipeline_statuses():
    src = TASK_CARD_TSX.read_text(encoding="utf-8")

    assert 'case "succeeded":' in src
    assert 'succeeded: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"' in src
    assert 'pending: "bg-muted text-muted-foreground"' in src


def test_old_pipeline_run_types_are_removed():
    src = TASKS_TYPES_TS.read_text(encoding="utf-8")

    assert "export interface PipelineRun {" not in src
    assert "export interface PipelineStage {" not in src
    assert "export interface PipelineChildRun {" not in src
    assert "export interface PipelineRunDetail {" not in src
