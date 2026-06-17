from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "client" / "src"
SCHEDULED_TASKS_TSX = ROOT / "pages" / "tasks" / "ScheduledTasksSection.tsx"
SCHEDULE_FROM_TASK_TSX = ROOT / "pages" / "tasks" / "ScheduleFromTaskButton.tsx"
TASKS_TSX = ROOT / "pages" / "Tasks.tsx"
LAYOUT_TSX = ROOT / "components" / "Layout.tsx"


def test_scheduled_tasks_section_uses_native_schedule_status_contract():
    src = SCHEDULED_TASKS_TSX.read_text(encoding="utf-8")

    assert "label?: string" in src
    assert "count?: number" in src
    assert "scheduleStatus.count" in src
    assert "job.label" in src


def test_scheduled_tasks_section_surfaces_write_errors_instead_of_silently_ignoring_them():
    src = SCHEDULED_TASKS_TSX.read_text(encoding="utf-8")

    assert "ApiError" in src
    assert "errorMsg" in src
    assert 'data-testid="text-scheduled-error"' in src
    assert 'aria-label={t("tasks.schedule.dismiss_error")}' in src
    assert "setErrorMsg" in src


def test_add_to_schedule_error_dismiss_button_is_accessible():
    src = SCHEDULE_FROM_TASK_TSX.read_text(encoding="utf-8")

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


def test_each_task_form_exposes_add_to_schedule_control():
    form_names = [
        "SiteConfigForm.tsx",
        "WebCrawlForm.tsx",
        "AdhocUrlForm.tsx",
        "FileImportForm.tsx",
        "WebSearchForm.tsx",
        "CatalogForm.tsx",
        "MarkdownForm.tsx",
        "ChunkForm.tsx",
        "RagIndexForm.tsx",
    ]

    for form_name in form_names:
        src = (ROOT / "pages" / "tasks" / form_name).read_text(encoding="utf-8")
        assert "ScheduleFromTaskButton" in src, form_name
        assert "buildTask" in src or "buildCollectionTask" in src, form_name


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
    src = (ROOT / "hooks" / "use-task-options.ts").read_text(encoding="utf-8")
    settings_src = (ROOT / "pages" / "settings" / "MarkdownConversionTab.tsx").read_text(encoding="utf-8")

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
    assert "<RagIndexForm onSubmit={handleSubmitTask} submitting={submitting} />" in tasks_src
    assert '"/api/rag/knowledge-bases"' in rag_src
    assert 'type: "rag_indexing"' in rag_src
    assert "kb_id: selectedKbId" in rag_src
    assert "force_reindex: forceReindex" in rag_src
    assert "ScheduleFromTaskButton" in rag_src


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
    assert 'testId="select-bind-kb"' in src
    assert "binding_mode: bindingMode" in src
    assert "kb_id: bindToKb ? selectedKbId : undefined" in src


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


def test_rag_index_form_supports_explicit_file_urls():
    src = (ROOT / "pages" / "tasks" / "RagIndexForm.tsx").read_text(encoding="utf-8")

    assert "fileUrlsInput" in src
    assert "parseFileUrls" in src
    assert "file_urls: fileUrls.length > 0 ? fileUrls : undefined" in src
    assert 'data-testid="input-rag-file-urls"' in src


def test_tasks_page_exposes_agentic_site_monitoring_form():
    tasks_src = TASKS_TSX.read_text(encoding="utf-8")
    form_src = (ROOT / "pages" / "tasks" / "WebListeningForm.tsx").read_text(encoding="utf-8")

    assert 'type: "web_listening"' in tasks_src
    assert "<WebListeningForm" in tasks_src
    assert '"/api/web-listening/rules/draft"' in form_src
    assert '"/api/web-listening/rules/validate"' in form_src
    assert '"/api/web-listening/rules/materialize"' in form_src
    assert '"/api/schedule/reinit"' in form_src
    assert 'scheduled-tasks:changed' in form_src
    assert 'data-testid="form-web-listening"' in form_src


def test_web_listening_entry_uses_site_permission_not_tasks_run_only():
    tasks_src = TASKS_TSX.read_text(encoding="utf-8")
    filter_src = (ROOT / "pages" / "tasks" / "FilterBar.tsx").read_text(encoding="utf-8")

    assert 'tt.type === "web_listening"' in tasks_src
    assert "return canManageSites" in tasks_src
    assert "const canShowTaskEntryGrid = visibleTaskTypes.length > 0" in tasks_src
    assert "{canShowTaskEntryGrid ? <div>" in tasks_src
    assert '<option value="rag_indexing">RAG Indexing</option>' in filter_src


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
