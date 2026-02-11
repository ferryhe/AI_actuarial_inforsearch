(function () {
    'use strict';

    const context = window.RAG_PAGE_CONTEXT || {};
    if (!context.page) return;

    const state = {
        kbs: [],
        kbCategories: {},
        categories: [],
        unmapped: [],
        currentCategory: '',
        selectedCreateFiles: new Map(),
        fileSelector: {
            pageSize: 100,
            offset: 0,
            query: '',
            category: '',
            rows: [],
            total: 0,
            target: 'create',
        },
    };

    const esc = (text) => (window.escapeHtml ? window.escapeHtml(text) : String(text || ''));

    function notify(message, type) {
        if (window.showNotification) {
            window.showNotification(message, type || 'info');
        } else {
            console.log(type || 'info', message);
        }
    }

    function formatDate(dateStr) {
        if (window.formatDate) return window.formatDate(dateStr);
        return dateStr || '-';
    }

    function formatBytes(bytes) {
        if (window.formatBytes) return window.formatBytes(bytes);
        return bytes || 0;
    }

    function getWriteHeaders() {
        const headers = { 'Content-Type': 'application/json' };
        const token =
            localStorage.getItem('config_write_token') ||
            sessionStorage.getItem('config_write_token') ||
            '';
        if (token) headers['X-Auth-Token'] = token;
        return headers;
    }

    async function api(url, options) {
        const resp = await fetch(url, options || {});
        let payload = null;
        try {
            payload = await resp.json();
        } catch (_err) {
            payload = null;
        }
        if (!resp.ok) {
            const msg = (payload && (payload.error || payload.message)) || `HTTP ${resp.status}`;
            throw new Error(msg);
        }
        return payload || {};
    }

    async function apiGet(url) {
        return api(url);
    }

    async function apiPost(url, body, write) {
        return api(url, {
            method: 'POST',
            headers: write ? getWriteHeaders() : { 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {}),
        });
    }

    async function apiPut(url, body) {
        return api(url, {
            method: 'PUT',
            headers: getWriteHeaders(),
            body: JSON.stringify(body || {}),
        });
    }

    async function apiDelete(url) {
        return api(url, {
            method: 'DELETE',
            headers: getWriteHeaders(),
        });
    }

    function openModal(id) {
        const el = document.getElementById(id);
        if (!el) return;
        el.style.display = 'flex';
        if (window.syncModalState) window.syncModalState();
    }

    function closeModal(id) {
        const el = document.getElementById(id);
        if (!el) return;
        el.style.display = 'none';
        if (window.syncModalState) window.syncModalState();
    }

    function bindModalCloseButtons() {
        document.querySelectorAll('[data-close-modal]').forEach((btn) => {
            btn.addEventListener('click', () => closeModal(btn.getAttribute('data-close-modal')));
        });
        document.querySelectorAll('.modal').forEach((modal) => {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    modal.style.display = 'none';
                    if (window.syncModalState) window.syncModalState();
                }
            });
        });
    }

    function renderCreateSelectedFiles() {
        const countEl = document.getElementById('rag-create-selected-files-count');
        const listEl = document.getElementById('rag-create-selected-files');
        if (!countEl || !listEl) return;
        countEl.textContent = `${state.selectedCreateFiles.size} files selected`;
        const items = Array.from(state.selectedCreateFiles.values());
        if (!items.length) {
            listEl.innerHTML = '<p class="text-muted">No files selected</p>';
            return;
        }
        listEl.innerHTML = items
            .map(
                (item) => `
                <div class="rag-selected-file-item">
                    <span title="${esc(item.url)}">${esc(item.title || item.original_filename || item.url)}</span>
                    <button type="button" class="btn btn-secondary btn-sm" data-remove-create-file="${esc(item.url)}">Remove</button>
                </div>
            `
            )
            .join('');
        listEl.querySelectorAll('[data-remove-create-file]').forEach((btn) => {
            btn.addEventListener('click', () => {
                state.selectedCreateFiles.delete(btn.getAttribute('data-remove-create-file'));
                renderCreateSelectedFiles();
            });
        });
    }

    function populateCategorySelects() {
        const createSelect = document.getElementById('rag-create-categories');
        const detailAddSelect = document.getElementById('rag-detail-add-category-select');
        const selector = document.getElementById('rag-file-selector-category');
        const options = state.categories
            .map((cat) => `<option value="${esc(cat)}">${esc(cat)}</option>`)
            .join('');

        if (createSelect) createSelect.innerHTML = options;
        if (detailAddSelect) detailAddSelect.innerHTML = `<option value="">Select category</option>${options}`;
        if (selector) selector.innerHTML = `<option value="">All Categories</option>${options}`;
    }

    function getKbModeBadge(mode) {
        return mode === 'category' ? 'Category' : 'Manual';
    }

    async function loadCategories() {
        const data = await apiGet('/api/categories?mode=used');
        state.categories = data.categories || [];
        populateCategorySelects();
    }

    async function loadUnmappedCategories() {
        const payload = await apiGet('/api/rag/categories/unmapped');
        const data = payload.data || {};
        state.unmapped = data.unmapped_categories || [];
        const alertEl = document.getElementById('rag-unmapped-alert');
        const countEl = document.getElementById('rag-unmapped-count');
        if (!alertEl || !countEl) return;
        if (!state.unmapped.length) {
            alertEl.style.display = 'none';
            return;
        }
        if (localStorage.getItem('rag_unmapped_dismissed') === '1') {
            alertEl.style.display = 'none';
            return;
        }
        countEl.textContent = String(state.unmapped.length);
        alertEl.style.display = 'flex';
    }

    async function loadKbs() {
        const payload = await apiGet('/api/rag/knowledge-bases');
        state.kbs = payload.data || [];
    }

    async function loadKbCategoryMappings() {
        const categoryKbs = state.kbs.filter((kb) => kb.kb_mode === 'category');
        const pairs = await Promise.all(
            categoryKbs.map(async (kb) => {
                try {
                    const payload = await apiGet(
                        `/api/rag/knowledge-bases/${encodeURIComponent(kb.kb_id)}/categories`
                    );
                    return [kb.kb_id, payload.data?.categories || []];
                } catch (_err) {
                    return [kb.kb_id, []];
                }
            })
        );
        state.kbCategories = Object.fromEntries(pairs);
    }

    function renderCategorySidebar() {
        const listEl = document.getElementById('rag-category-list');
        if (!listEl) return;
        if (!state.categories.length) {
            listEl.innerHTML = '<p class="text-muted">No categories available.</p>';
            return;
        }
        const unmappedSet = new Set(state.unmapped.map((x) => x.name));
        listEl.innerHTML = state.categories
            .map((cat) => {
                const active = cat === state.currentCategory ? 'active' : '';
                const unmapped = unmappedSet.has(cat) ? 'unmapped' : '';
                return `<div class="rag-category-item ${active} ${unmapped}" data-rag-category="${esc(cat)}"><span>${esc(cat)}</span><span>${unmapped ? 'No KB' : ''}</span></div>`;
            })
            .join('');
        listEl.querySelectorAll('[data-rag-category]').forEach((el) => {
            el.addEventListener('click', () => {
                const next = el.getAttribute('data-rag-category');
                state.currentCategory = state.currentCategory === next ? '' : next;
                renderCategorySidebar();
                renderKbTable();
            });
        });
    }

    function getFilteredKbs() {
        const query = (document.getElementById('rag-kb-search')?.value || '').trim().toLowerCase();
        const mode = (document.getElementById('rag-kb-mode-filter')?.value || '').trim();
        return state.kbs.filter((kb) => {
            if (mode && kb.kb_mode !== mode) return false;
            if (query) {
                const match =
                    (kb.name || '').toLowerCase().includes(query) ||
                    (kb.description || '').toLowerCase().includes(query) ||
                    (kb.kb_id || '').toLowerCase().includes(query);
                if (!match) return false;
            }
            if (state.currentCategory && kb.kb_mode === 'category') {
                const cats = state.kbCategories[kb.kb_id] || [];
                if (!cats.includes(state.currentCategory)) return false;
            } else if (state.currentCategory && kb.kb_mode !== 'category') {
                return false;
            }
            return true;
        });
    }

    function bindKbRowActions() {
        document.querySelectorAll('[data-kb-view]').forEach((btn) => {
            btn.addEventListener('click', () => {
                window.location.href = `/rag/${encodeURIComponent(btn.getAttribute('data-kb-view'))}`;
            });
        });
        document.querySelectorAll('[data-kb-edit]').forEach((btn) => {
            btn.addEventListener('click', async () => openEditModal(btn.getAttribute('data-kb-edit')));
        });
        document.querySelectorAll('[data-kb-delete]').forEach((btn) => {
            btn.addEventListener('click', async () => deleteKb(btn.getAttribute('data-kb-delete')));
        });
        document.querySelectorAll('[data-kb-index]').forEach((btn) => {
            btn.addEventListener('click', async () => triggerIndex(btn.getAttribute('data-kb-index'), false));
        });
        document.querySelectorAll('[data-kb-export]').forEach((btn) => {
            btn.addEventListener('click', async () => exportKb(btn.getAttribute('data-kb-export')));
        });
    }

    function renderKbTable() {
        const body = document.getElementById('rag-kb-table-body');
        if (!body) return;
        const rows = getFilteredKbs();
        if (!rows.length) {
            body.innerHTML = '<tr><td colspan="6">No knowledge bases found.</td></tr>';
            return;
        }
        body.innerHTML = rows
            .map(
                (kb) => `
                <tr>
                    <td><strong>${esc(kb.name)}</strong><br><small>${esc(kb.kb_id)}</small></td>
                    <td>${esc(getKbModeBadge(kb.kb_mode))}</td>
                    <td>${kb.file_count || 0}</td>
                    <td>${kb.chunk_count || 0}</td>
                    <td>${esc(formatDate(kb.updated_at))}</td>
                    <td>
                        <div class="rag-actions">
                            <button class="btn btn-secondary btn-sm" data-kb-view="${esc(kb.kb_id)}">View</button>
                            <button class="btn btn-secondary btn-sm" data-kb-edit="${esc(kb.kb_id)}">Edit</button>
                            <button class="btn btn-secondary btn-sm" data-kb-index="${esc(kb.kb_id)}">Index</button>
                            <button class="btn btn-secondary btn-sm" data-kb-export="${esc(kb.kb_id)}">Export</button>
                            <button class="btn btn-secondary btn-sm" data-kb-delete="${esc(kb.kb_id)}">Delete</button>
                        </div>
                    </td>
                </tr>
            `
            )
            .join('');
        bindKbRowActions();
    }

    async function triggerIndex(kbId, reindexAll) {
        try {
            const payload = await apiPost(
                `/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/index`,
                { force_reindex: !!reindexAll, reindex_all: !!reindexAll, incremental: !reindexAll },
                true
            );
            const jobId = payload.data?.job_id || '-';
            notify(`Index task created: ${jobId}`, 'success');
        } catch (err) {
            notify(`Failed to start indexing: ${err.message}`, 'error');
        }
    }

    async function deleteKb(kbId) {
        const ok = window.customConfirm
            ? await window.customConfirm(`Delete knowledge base '${kbId}'?`, 'Delete KB')
            : window.confirm(`Delete knowledge base '${kbId}'?`);
        if (!ok) return;
        try {
            await apiDelete(`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}`);
            notify('Knowledge base deleted', 'success');
            if (context.page === 'detail') {
                window.location.href = '/rag';
                return;
            }
            await refreshListPage();
        } catch (err) {
            notify(`Delete failed: ${err.message}`, 'error');
        }
    }

    async function exportKb(kbId) {
        try {
            const payload = await apiGet(`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}`);
            const blob = new Blob([JSON.stringify(payload.data || {}, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${kbId}.metadata.json`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        } catch (err) {
            notify(`Export failed: ${err.message}`, 'error');
        }
    }

    async function loadFileSelectorPage() {
        const body = document.getElementById('rag-file-selector-body');
        if (!body) return;
        body.innerHTML = '<tr><td colspan="6">Loading...</td></tr>';
        const qp = new URLSearchParams({
            limit: String(state.fileSelector.pageSize),
            offset: String(state.fileSelector.offset),
            order_by: 'last_seen',
            order_dir: 'desc',
            query: state.fileSelector.query || '',
            category: state.fileSelector.category || '',
        });
        try {
            const payload = await apiGet(`/api/files?${qp.toString()}`);
            state.fileSelector.rows = payload.files || [];
            state.fileSelector.total = payload.total || 0;
            renderFileSelectorRows();
        } catch (err) {
            body.innerHTML = `<tr><td colspan="6">${esc(err.message)}</td></tr>`;
        }
    }

    function renderFileSelectorRows() {
        const body = document.getElementById('rag-file-selector-body');
        if (!body) return;
        const selectedMap = state.fileSelector.target === 'create' ? state.selectedCreateFiles : new Map();
        const checkAll = document.getElementById('rag-file-selector-check-all');
        if (!state.fileSelector.rows.length) {
            body.innerHTML = '<tr><td colspan="6">No files found.</td></tr>';
            if (checkAll) checkAll.checked = false;
            return;
        }
        body.innerHTML = state.fileSelector.rows
            .map((row) => {
                const checked = selectedMap.has(row.url) ? 'checked' : '';
                return `
                    <tr>
                        <td><input type="checkbox" data-file-select="${esc(row.url)}" ${checked}></td>
                        <td title="${esc(row.url)}">${esc(row.title || row.original_filename || row.url)}</td>
                        <td>${esc(row.category || '-')}</td>
                        <td>${esc(row.source_site || '-')}</td>
                        <td>${esc(formatBytes(row.bytes))}</td>
                        <td>${esc(formatDate(row.last_seen || row.crawl_time))}</td>
                    </tr>
                `;
            })
            .join('');
        body.querySelectorAll('[data-file-select]').forEach((cb) => {
            cb.addEventListener('change', () => {
                if (state.fileSelector.target === 'create') {
                    const url = cb.getAttribute('data-file-select');
                    const row = state.fileSelector.rows.find((r) => r.url === url);
                    if (cb.checked && row) state.selectedCreateFiles.set(url, row);
                    if (!cb.checked) state.selectedCreateFiles.delete(url);
                    renderCreateSelectedFiles();
                }
                if (checkAll) {
                    const allRows = Array.from(body.querySelectorAll('[data-file-select]'));
                    checkAll.checked = allRows.length > 0 && allRows.every((x) => x.checked);
                }
                updateFileSelectorSummary();
            });
        });
        if (checkAll) {
            const allRows = Array.from(body.querySelectorAll('[data-file-select]'));
            checkAll.checked = allRows.length > 0 && allRows.every((x) => x.checked);
        }
        updateFileSelectorSummary();
    }

    function updateFileSelectorSummary() {
        const summary = document.getElementById('rag-file-selector-summary');
        if (!summary) return;
        const count =
            state.fileSelector.target === 'create' ? state.selectedCreateFiles.size : 0;
        summary.textContent = `${count} files selected`;
    }

    function openFileSelector(target) {
        state.fileSelector.target = target || 'create';
        openModal('rag-file-selector-modal');
        loadFileSelectorPage();
    }

    function bindFileSelector() {
        document.getElementById('rag-open-file-selector')?.addEventListener('click', () => openFileSelector('create'));
        document.getElementById('rag-file-selector-refresh')?.addEventListener('click', () => loadFileSelectorPage());
        document.getElementById('rag-file-selector-search')?.addEventListener('change', (e) => {
            state.fileSelector.query = e.target.value || '';
            state.fileSelector.offset = 0;
            loadFileSelectorPage();
        });
        document.getElementById('rag-file-selector-category')?.addEventListener('change', (e) => {
            state.fileSelector.category = e.target.value || '';
            state.fileSelector.offset = 0;
            loadFileSelectorPage();
        });
        document.getElementById('rag-file-selector-prev')?.addEventListener('click', () => {
            state.fileSelector.offset = Math.max(0, state.fileSelector.offset - state.fileSelector.pageSize);
            loadFileSelectorPage();
        });
        document.getElementById('rag-file-selector-next')?.addEventListener('click', () => {
            const next = state.fileSelector.offset + state.fileSelector.pageSize;
            if (next >= state.fileSelector.total) return;
            state.fileSelector.offset = next;
            loadFileSelectorPage();
        });
        document.getElementById('rag-file-selector-clear')?.addEventListener('click', () => {
            if (state.fileSelector.target === 'create') state.selectedCreateFiles.clear();
            renderCreateSelectedFiles();
            updateFileSelectorSummary();
            loadFileSelectorPage();
        });
        document.getElementById('rag-file-selector-check-all')?.addEventListener('change', (e) => {
            const checked = !!e.target.checked;
            document.querySelectorAll('[data-file-select]').forEach((cb) => {
                if (cb.checked === checked) return;
                cb.checked = checked;
                cb.dispatchEvent(new Event('change'));
            });
        });
        document.getElementById('rag-file-selector-apply')?.addEventListener('click', async () => {
            if (state.fileSelector.target === 'detail') {
                const checked = Array.from(document.querySelectorAll('[data-file-select]:checked')).map(
                    (cb) => cb.getAttribute('data-file-select')
                );
                if (!checked.length) {
                    notify('Select at least one file', 'warning');
                    return;
                }
                try {
                    await apiPost(`/api/rag/knowledge-bases/${encodeURIComponent(context.kbId)}/files`, { file_urls: checked }, true);
                    notify('Files added to knowledge base', 'success');
                    await loadDetailFiles();
                } catch (err) {
                    notify(`Add files failed: ${err.message}`, 'error');
                }
            }
            closeModal('rag-file-selector-modal');
        });
    }

    async function openEditModal(kbId) {
        try {
            const payload = await apiGet(`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}`);
            const kb = payload.data || {};
            const form = document.getElementById('rag-edit-kb-form');
            if (!form) return;
            form.kb_id.value = kb.kb_id || '';
            form.name.value = kb.name || '';
            form.description.value = kb.description || '';
            form.kb_mode.value = kb.kb_mode || '';
            form.embedding_model.value = kb.embedding_model || '';
            openModal('rag-edit-kb-modal');
        } catch (err) {
            notify(`Failed to load KB: ${err.message}`, 'error');
        }
    }

    function bindCreateEditForms() {
        const createForm = document.getElementById('rag-create-kb-form');
        const editForm = document.getElementById('rag-edit-kb-form');
        const modeInputs = document.querySelectorAll('input[name="kb_mode"]');

        modeInputs.forEach((input) => {
            input.addEventListener('change', () => {
                const isCategory = input.checked && input.value === 'category';
                const c = document.getElementById('rag-create-category-fields');
                const m = document.getElementById('rag-create-manual-fields');
                if (c) c.style.display = isCategory ? 'block' : 'none';
                if (m) m.style.display = isCategory ? 'none' : 'block';
            });
        });

        document.getElementById('rag-open-create-modal')?.addEventListener('click', () => {
            if (createForm) createForm.reset();
            state.selectedCreateFiles.clear();
            renderCreateSelectedFiles();
            openModal('rag-create-kb-modal');
        });

        document.getElementById('rag-create-from-unmapped')?.addEventListener('click', () => {
            if (!createForm) return;
            createForm.reset();
            const categoryRadio = createForm.querySelector('input[name="kb_mode"][value="category"]');
            if (categoryRadio) categoryRadio.checked = true;
            const select = document.getElementById('rag-create-categories');
            if (select) {
                const preselect = new Set(state.unmapped.slice(0, 6).map((x) => x.name));
                Array.from(select.options).forEach((opt) => {
                    opt.selected = preselect.has(opt.value);
                });
            }
            openModal('rag-create-kb-modal');
        });

        document.getElementById('rag-dismiss-unmapped')?.addEventListener('click', () => {
            localStorage.setItem('rag_unmapped_dismissed', '1');
            document.getElementById('rag-unmapped-alert').style.display = 'none';
        });

        async function submitCreate(createAndIndex) {
            if (!createForm) return;
            const formData = new FormData(createForm);
            const mode = formData.get('kb_mode');
            const payload = {
                kb_id: formData.get('kb_id'),
                name: formData.get('name'),
                description: formData.get('description'),
                kb_mode: mode,
                embedding_model: formData.get('embedding_model'),
                chunk_size: Number(formData.get('chunk_size') || 800),
                chunk_overlap: Number(formData.get('chunk_overlap') || 100),
            };
            if (mode === 'category') {
                payload.categories = Array.from(document.getElementById('rag-create-categories').selectedOptions).map((o) => o.value);
            } else {
                payload.file_urls = Array.from(state.selectedCreateFiles.keys());
            }
            try {
                const created = await apiPost('/api/rag/knowledge-bases', payload, true);
                closeModal('rag-create-kb-modal');
                notify('Knowledge base created', 'success');
                if (createAndIndex) {
                    await triggerIndex(created.data?.kb_id || payload.kb_id, false);
                }
                if (context.page === 'list') {
                    await refreshListPage();
                } else if (created.data?.kb_id) {
                    window.location.href = `/rag/${encodeURIComponent(created.data.kb_id)}`;
                }
            } catch (err) {
                notify(`Create failed: ${err.message}`, 'error');
            }
        }

        createForm?.addEventListener('submit', async (e) => {
            e.preventDefault();
            await submitCreate(false);
        });
        document.getElementById('rag-create-and-index-btn')?.addEventListener('click', async () => {
            await submitCreate(true);
        });

        editForm?.addEventListener('submit', async (e) => {
            e.preventDefault();
            try {
                await apiPut(`/api/rag/knowledge-bases/${encodeURIComponent(editForm.kb_id.value)}`, {
                    name: editForm.name.value,
                    description: editForm.description.value,
                });
                closeModal('rag-edit-kb-modal');
                notify('Knowledge base updated', 'success');
                if (context.page === 'list') await refreshListPage();
                if (context.page === 'detail') await refreshDetailPage();
            } catch (err) {
                notify(`Update failed: ${err.message}`, 'error');
            }
        });
    }

    async function refreshListPage() {
        await Promise.all([loadKbs(), loadCategories(), loadUnmappedCategories()]);
        await loadKbCategoryMappings();
        renderCategorySidebar();
        renderKbTable();
    }

    async function loadDetailHeader() {
        const payload = await apiGet(`/api/rag/knowledge-bases/${encodeURIComponent(context.kbId)}`);
        const kb = payload.data || {};
        document.getElementById('rag-detail-title').textContent = kb.name || kb.kb_id || 'Knowledge Base';
        document.getElementById('rag-detail-description').textContent = kb.description || '';
        document.getElementById('rag-meta-kb-id').textContent = kb.kb_id || '-';
        document.getElementById('rag-meta-mode').textContent = getKbModeBadge(kb.kb_mode);
        document.getElementById('rag-meta-embedding').textContent = kb.embedding_model || '-';
        document.getElementById('rag-meta-chunk-size').textContent = kb.chunk_size || '-';
        document.getElementById('rag-meta-chunk-overlap').textContent = kb.chunk_overlap || '-';
        document.getElementById('rag-meta-updated').textContent = formatDate(kb.updated_at);

        const stats = kb.stats || {};
        document.getElementById('rag-stat-total-files').textContent = stats.total_files ?? kb.file_count ?? 0;
        document.getElementById('rag-stat-indexed-files').textContent = stats.indexed_files ?? 0;
        document.getElementById('rag-stat-pending-files').textContent = stats.pending_files ?? 0;
        document.getElementById('rag-stat-total-chunks').textContent = stats.total_chunks ?? kb.chunk_count ?? 0;
    }

    async function loadDetailFiles() {
        const payload = await apiGet(`/api/rag/knowledge-bases/${encodeURIComponent(context.kbId)}/files`);
        const rows = payload.data?.files || [];
        const search = (document.getElementById('rag-detail-file-search')?.value || '').toLowerCase();
        const filtered = rows.filter((f) => !search || (f.title || f.file_url || '').toLowerCase().includes(search));
        const body = document.getElementById('rag-detail-files-body');
        if (!filtered.length) {
            body.innerHTML = '<tr><td colspan="6">No files found.</td></tr>';
            return;
        }
        body.innerHTML = filtered
            .map(
                (f) => `
                <tr>
                    <td>${esc(f.title || f.file_url)}</td>
                    <td>${esc(f.category || '-')}</td>
                    <td><span class="rag-status ${esc(f.status || 'pending')}">${esc(f.status || 'pending')}</span></td>
                    <td>${f.chunk_count || 0}</td>
                    <td>${esc(formatDate(f.indexed_at))}</td>
                    <td><button class="btn btn-secondary btn-sm" data-remove-detail-file="${esc(f.file_url)}">Remove</button></td>
                </tr>
            `
            )
            .join('');
        body.querySelectorAll('[data-remove-detail-file]').forEach((btn) => {
            btn.addEventListener('click', async () => {
                try {
                    await apiDelete(`/api/rag/knowledge-bases/${encodeURIComponent(context.kbId)}/files/${encodeURIComponent(btn.getAttribute('data-remove-detail-file'))}`);
                    await loadDetailFiles();
                    await loadDetailHeader();
                } catch (err) {
                    notify(`Remove failed: ${err.message}`, 'error');
                }
            });
        });
    }

    async function loadDetailCategories() {
        const payload = await apiGet(`/api/rag/knowledge-bases/${encodeURIComponent(context.kbId)}/categories`);
        const categories = payload.data?.categories || [];
        const list = document.getElementById('rag-detail-categories-list');
        list.innerHTML = categories.length ? categories.map((c) => `<li>${esc(c)}</li>`).join('') : '<li>No linked categories</li>';
    }

    async function loadDetailTasks() {
        const payload = await apiGet(`/api/rag/knowledge-bases/${encodeURIComponent(context.kbId)}/tasks?limit=30`);
        const active = payload.data?.active || [];
        const history = payload.data?.history || [];
        const activeBox = document.getElementById('rag-detail-active-tasks');
        activeBox.innerHTML = active.map((t) => `<div class="rag-active-task">${esc(t.name || t.id)} - ${esc(t.status || 'pending')} (${t.progress || 0}%)</div>`).join('');
        const body = document.getElementById('rag-detail-tasks-body');
        if (!history.length) {
            body.innerHTML = '<tr><td colspan="5">No task history.</td></tr>';
            return;
        }
        body.innerHTML = history
            .map((t) => `<tr><td>${esc(t.name || t.id)}</td><td>${esc(t.status || '-')}</td><td>${esc(formatDate(t.started_at))}</td><td>${t.items_processed || 0}</td><td>${t.rag_total_chunks || 0}</td></tr>`)
            .join('');
    }

    async function refreshDetailPage() {
        await Promise.all([loadDetailHeader(), loadDetailFiles(), loadDetailCategories(), loadDetailTasks(), loadCategories()]);
    }

    function bindDetailEvents() {
        document.getElementById('rag-detail-refresh')?.addEventListener('click', () => refreshDetailPage());
        document.getElementById('rag-detail-edit')?.addEventListener('click', () => openEditModal(context.kbId));
        document.getElementById('rag-detail-reindex')?.addEventListener('click', () => triggerIndex(context.kbId, true));
        document.getElementById('rag-detail-delete')?.addEventListener('click', () => deleteKb(context.kbId));
        document.getElementById('rag-detail-add-files')?.addEventListener('click', () => openFileSelector('detail'));
        document.getElementById('rag-detail-file-search')?.addEventListener('input', () => loadDetailFiles());
        document.getElementById('rag-detail-link-category')?.addEventListener('click', async () => {
            const sel = document.getElementById('rag-detail-add-category-select');
            if (!sel || !sel.value) {
                notify('Select a category', 'warning');
                return;
            }
            try {
                await apiPost(`/api/rag/knowledge-bases/${encodeURIComponent(context.kbId)}/categories`, { categories: [sel.value] }, true);
                await loadDetailCategories();
                await loadDetailHeader();
            } catch (err) {
                notify(`Link failed: ${err.message}`, 'error');
            }
        });

        document.querySelectorAll('.rag-tab-btn').forEach((btn) => {
            btn.addEventListener('click', () => {
                const tab = btn.getAttribute('data-tab');
                document.querySelectorAll('.rag-tab-btn').forEach((x) => x.classList.remove('active'));
                document.querySelectorAll('.rag-tab-content').forEach((x) => x.classList.remove('active'));
                btn.classList.add('active');
                document.getElementById(`rag-tab-${tab}`)?.classList.add('active');
            });
        });
    }

    async function initListPage() {
        bindCreateEditForms();
        bindFileSelector();
        document.getElementById('rag-refresh-list')?.addEventListener('click', () => refreshListPage());
        document.getElementById('rag-kb-search')?.addEventListener('input', () => renderKbTable());
        document.getElementById('rag-kb-mode-filter')?.addEventListener('change', () => renderKbTable());
        document.getElementById('rag-clear-category-filter')?.addEventListener('click', () => {
            state.currentCategory = '';
            renderCategorySidebar();
            renderKbTable();
        });
        await refreshListPage();
    }

    async function initDetailPage() {
        bindCreateEditForms();
        bindFileSelector();
        bindDetailEvents();
        await refreshDetailPage();
        window.setInterval(() => loadDetailTasks(), 4000);
    }

    bindModalCloseButtons();
    if (context.page === 'list') initListPage();
    if (context.page === 'detail') initDetailPage();
})();
