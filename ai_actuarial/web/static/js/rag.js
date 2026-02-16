(function () {
    'use strict';

    const context = window.RAG_PAGE_CONTEXT || {};
    if (!context.page) return;

    const state = {
        kbs: [],
        chunkProfiles: [],
        kbCategories: {},
        categories: [],
        unmapped: [],
        currentCategory: '',
        currentKb: null,
        detailFiles: [],
        detailComposition: null,
        detailPendingFiles: 0,
        detailProfileSummary: '-',
        detailFileSelection: new Set(),
        detailPage: 1,
        detailPageSize: 20,
        detailSortKey: 'index_time',
        detailSortDirection: 'desc',
        detailColumnResizeReady: false,
        selectedCreateFiles: new Map(),
        selectedDetailFiles: new Map(),
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

    function formatError(err) {
        const status = err && err.status;
        const msg = (err && err.message) || 'Unknown error';
        if (status === 403 || String(msg).toLowerCase().includes('forbidden')) {
            return 'Forbidden: please log in with operator/admin and provide CONFIG_WRITE_AUTH_TOKEN (X-Auth-Token).';
        }
        return msg;
    }

    function formatDate(dateStr) {
        if (window.formatDate) return window.formatDate(dateStr);
        return dateStr || '-';
    }

    function formatBytes(bytes) {
        if (window.formatBytes) return window.formatBytes(bytes);
        return bytes || 0;
    }

    function shortId(value, head = 12, tail = 8) {
        const text = String(value || '');
        if (!text) return '-';
        if (text.length <= head + tail + 3) return text;
        return `${text.slice(0, head)}...${text.slice(-tail)}`;
    }

    function parseTimestamp(value) {
        const text = String(value || '').trim();
        if (!text) return null;
        const ms = Date.parse(text);
        return Number.isFinite(ms) ? ms : null;
    }

    function compareMaybe(aVal, bVal, direction) {
        if (aVal == null && bVal == null) return 0;
        if (aVal == null) return 1;
        if (bVal == null) return -1;
        if (typeof aVal === 'number' && typeof bVal === 'number') {
            return direction === 'asc' ? aVal - bVal : bVal - aVal;
        }
        const left = String(aVal);
        const right = String(bVal);
        return direction === 'asc' ? left.localeCompare(right) : right.localeCompare(left);
    }

    function parseChunkProfileConfig(profile) {
        const raw = profile && profile.config_json ? profile.config_json : '';
        if (!raw) return {};
        try {
            const parsed = JSON.parse(raw);
            return parsed && typeof parsed === 'object' ? parsed : {};
        } catch (_err) {
            return {};
        }
    }

    function getChunkProfileModel(profile) {
        const cfg = parseChunkProfileConfig(profile);
        const metadata = cfg && typeof cfg.metadata === 'object' ? cfg.metadata : {};
        return metadata && metadata.chunk_model ? String(metadata.chunk_model) : 'gpt-4';
    }

    function formatChunkProfileSummary(profile) {
        if (!profile) return '';
        const model = getChunkProfileModel(profile);
        return `Profile: ${profile.name || profile.profile_id} | model=${model} | size=${profile.chunk_size} | overlap=${profile.chunk_overlap} | ${profile.splitter}/${profile.tokenizer}`;
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
            const err = new Error(msg);
            err.status = resp.status;
            err.payload = payload;
            throw err;
        }
        return payload || {};
    }

    async function apiGet(url) {
        return api(url);
    }

    async function apiPost(url, body, write) {
        const buildOptions = () => ({
            method: 'POST',
            headers: write ? getWriteHeaders() : { 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {}),
        });
        try {
            return await api(url, buildOptions());
        } catch (err) {
            if (write && err.status === 403 && (err.message || '').toLowerCase().includes('forbidden')) {
                const updated = await promptWriteTokenAndStore();
                if (updated) return api(url, buildOptions());
            }
            throw err;
        }
    }

    async function apiPut(url, body) {
        const buildOptions = () => ({
            method: 'PUT',
            headers: getWriteHeaders(),
            body: JSON.stringify(body || {}),
        });
        try {
            return await api(url, buildOptions());
        } catch (err) {
            if (err.status === 403 && (err.message || '').toLowerCase().includes('forbidden')) {
                const updated = await promptWriteTokenAndStore();
                if (updated) return api(url, buildOptions());
            }
            throw err;
        }
    }

    async function apiDelete(url) {
        const buildOptions = () => ({
            method: 'DELETE',
            headers: getWriteHeaders(),
        });
        try {
            return await api(url, buildOptions());
        } catch (err) {
            if (err.status === 403 && (err.message || '').toLowerCase().includes('forbidden')) {
                const updated = await promptWriteTokenAndStore();
                if (updated) return api(url, buildOptions());
            }
            throw err;
        }
    }

    async function promptWriteTokenAndStore() {
        const current =
            localStorage.getItem('config_write_token') ||
            sessionStorage.getItem('config_write_token') ||
            '';
        const promptText =
            'This action requires CONFIG_WRITE_AUTH_TOKEN (X-Auth-Token).\nEnter write token (saved in current session only):';
        const input = window.prompt(promptText, current);
        if (input === null) return false;
        const token = (input || '').trim();
        if (!token) return false;
        sessionStorage.setItem('config_write_token', token);
        return true;
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
                    if (modal.dataset.staticModal === 'true') return;
                    modal.style.display = 'none';
                    if (window.syncModalState) window.syncModalState();
                }
            });
        });
    }

    async function confirmDeleteWithText(title, message) {
        return new Promise((resolve) => {
            const modal = document.createElement('div');
            modal.className = 'modal';
            modal.style.display = 'flex';
            modal.innerHTML = `
                <div class="modal-content confirm-dialog">
                    <h3>${esc(title || 'Confirm Delete')}</h3>
                    <p>${esc(message || 'Type "confirm delete" to proceed.')}</p>
                    <p>Type <strong>confirm delete</strong> to proceed:</p>
                    <input type="text" id="rag-delete-confirm-input" class="form-control"
                        placeholder="confirm delete"
                        style="margin: 1rem 0; padding: 0.5rem; width: 100%; border: 1px solid var(--border-color); border-radius: 4px;">
                    <div class="confirm-buttons">
                        <button class="btn btn-secondary" id="rag-delete-cancel">Cancel</button>
                        <button class="btn btn-danger" id="rag-delete-confirm">Delete</button>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
            document.body.classList.add('modal-open');

            const input = modal.querySelector('#rag-delete-confirm-input');
            const confirmBtn = modal.querySelector('#rag-delete-confirm');
            const cancelBtn = modal.querySelector('#rag-delete-cancel');

            const cleanup = (result) => {
                modal.remove();
                document.body.classList.remove('modal-open');
                resolve(result);
            };

            setTimeout(() => input?.focus(), 50);

            confirmBtn?.addEventListener('click', () => {
                const value = (input?.value || '').trim().toLowerCase();
                if (value === 'confirm delete') {
                    cleanup(true);
                    return;
                }
                notify('Please type "confirm delete" exactly to proceed', 'error');
                input?.focus();
            });
            cancelBtn?.addEventListener('click', () => cleanup(false));
            input?.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') confirmBtn?.click();
            });
        });
    }

    function buildKbDatePrefix() {
        const now = new Date();
        const yyyy = String(now.getFullYear());
        const mm = String(now.getMonth() + 1).padStart(2, '0');
        const dd = String(now.getDate()).padStart(2, '0');
        return `KB_${yyyy}${mm}${dd}_`;
    }

    function generateNextKbId(_nameHint) {
        const existing = new Set(state.kbs.map((kb) => kb.kb_id));
        const prefix = buildKbDatePrefix();
        let index = 1;
        while (index < 10000) {
            const candidate = `${prefix}${String(index).padStart(4, '0')}`;
            if (!existing.has(candidate)) return candidate;
            index += 1;
        }
        return `${prefix}${Date.now()}`;
    }

    function syncCreateKbId() {
        const nameInput = document.querySelector('#rag-create-kb-form [name="name"]');
        const kbIdInput = document.getElementById('rag-create-kb-id-input');
        const kbIdPreview = document.getElementById('rag-create-kb-id-preview');
        if (!nameInput || !kbIdInput || !kbIdPreview) return;
        const nextKbId = generateNextKbId(nameInput.value || '');
        kbIdInput.value = nextKbId;
        kbIdPreview.textContent = nextKbId;
    }

    function getFileSelectionMap(target) {
        return target === 'detail' ? state.selectedDetailFiles : state.selectedCreateFiles;
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

    function renderCreateChunkProfileOptions() {
        const select = document.getElementById('rag-create-chunk-profile');
        if (!select) return;
        const oldValue = select.value;
        let html = '<option value="" selected disabled>Select existing chunk profile</option>';
        for (const profile of state.chunkProfiles) {
            html += `<option value="${esc(profile.profile_id)}">${esc(profile.name || profile.profile_id)} | ${esc(getChunkProfileModel(profile))} | size=${profile.chunk_size}, overlap=${profile.chunk_overlap}</option>`;
        }
        if (!state.chunkProfiles.length) {
            html += '<option value="" disabled>No chunk profiles found - create one in Chunk Profiles</option>';
        }
        select.innerHTML = html;
        if (oldValue && state.chunkProfiles.some((p) => p.profile_id === oldValue)) {
            select.value = oldValue;
        }
    }

    function syncCreateChunkProfileMode() {
        const select = document.getElementById('rag-create-chunk-profile');
        const summary = document.getElementById('rag-create-selected-profile-summary');
        if (!select || !summary) return;

        const profileId = String(select.value || '').trim();
        if (!profileId) {
            summary.style.display = 'none';
            summary.textContent = '';
            return;
        }

        const profile = state.chunkProfiles.find((p) => p.profile_id === profileId);
        if (!profile) {
            summary.style.display = 'none';
            summary.textContent = '';
            return;
        }

        summary.textContent = formatChunkProfileSummary(profile);
        summary.style.display = 'block';
    }

    function renderChunkProfileTable() {
        const body = document.getElementById('rag-chunk-profile-table-body');
        if (!body) return;
        if (!state.chunkProfiles.length) {
            body.innerHTML = '<tr><td colspan="7">No chunk profiles yet.</td></tr>';
            return;
        }
        body.innerHTML = state.chunkProfiles
            .map((profile) => {
                const model = getChunkProfileModel(profile);
                return `<tr>
                    <td>${esc(profile.name || profile.profile_id)}</td>
                    <td>${esc(model)}</td>
                    <td>${profile.chunk_size || 0}</td>
                    <td>${profile.chunk_overlap || 0}</td>
                    <td>${esc(profile.splitter || '-')}</td>
                    <td>${esc(profile.tokenizer || '-')}</td>
                    <td>${esc(formatDate(profile.updated_at || profile.created_at || '-'))}</td>
                </tr>`;
            })
            .join('');
    }

    async function loadChunkProfiles() {
        try {
            const payload = await apiGet('/api/chunk/profiles');
            const data = payload.data || {};
            state.chunkProfiles = Array.isArray(data.profiles) ? data.profiles : [];
        } catch (_err) {
            state.chunkProfiles = [];
        }
        renderCreateChunkProfileOptions();
        renderChunkProfileTable();
        syncCreateChunkProfileMode();
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
        document.querySelectorAll('[data-kb-row]').forEach((row) => {
            row.addEventListener('click', () => {
                const kbId = row.getAttribute('data-kb-row');
                if (!kbId) return;
                window.location.href = `/rag/${encodeURIComponent(kbId)}`;
            });
        });
    }

    function renderKbTable() {
        const body = document.getElementById('rag-kb-table-body');
        if (!body) return;
        const rows = getFilteredKbs();
        if (!rows.length) {
            body.innerHTML = '<tr><td colspan="5">No knowledge bases found.</td></tr>';
            return;
        }
        body.innerHTML = rows
            .map(
                (kb) => `
                <tr class="rag-kb-row" data-kb-row="${esc(kb.kb_id)}">
                    <td><strong>${esc(kb.name)}</strong><br><small>${esc(kb.kb_id)}</small></td>
                    <td>${esc(getKbModeBadge(kb.kb_mode))}</td>
                    <td>${kb.file_count || 0}</td>
                    <td>${kb.chunk_count || 0}</td>
                    <td>${esc(formatDate(kb.updated_at))}</td>
                </tr>
            `
            )
            .join('');
        bindKbRowActions();
    }

    async function triggerIndex(kbId, options = {}) {
        const opts = options || {};
        const fileUrls = Array.isArray(opts.fileUrls) ? opts.fileUrls : [];
        const reindexAll = !!opts.reindexAll;
        const confirmMessage = opts.confirmMessage || '';

        if (confirmMessage) {
            const ok = window.customConfirm
                ? await window.customConfirm(confirmMessage, 'Start Indexing')
                : window.confirm(confirmMessage);
            if (!ok) return null;
        }

        const payload = await apiPost(
            `/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/index`,
            {
                force_reindex: reindexAll,
                reindex_all: reindexAll,
                incremental: !reindexAll,
                ...(fileUrls.length ? { file_urls: fileUrls } : {}),
            },
            true
        );
        const data = payload.data || null;
        if (data && Number(data.skipped_no_markdown || 0) > 0) {
            notify(`Skipped ${data.skipped_no_markdown} file(s) without markdown`, 'warning');
        }
        return data;
    }

    async function deleteKb(kbId) {
        const ok = await confirmDeleteWithText(
            'Delete Knowledge Base',
            `You are deleting KB '${kbId}'. This cannot be undone.`
        );
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
            notify(`Delete failed: ${formatError(err)}`, 'error');
        }
    }

    function csvEscape(rawValue) {
        let str = String(rawValue == null ? '' : rawValue);
        if (/^\s*[=+\-@]/.test(str)) str = `'${str}`;
        const escaped = str.replace(/"/g, '""');
        return /[",\n]/.test(escaped) ? `"${escaped}"` : escaped;
    }

    async function exportKbFileList(kbId) {
        try {
            const payload = await apiGet(`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/files`);
            const files = payload.data?.files || [];
            const headers = [
                'file_url',
                'title',
                'category',
                'status',
                'chunk_count',
                'indexed_at',
                'markdown_updated_at',
            ];
            const rows = files.map((f) => [
                f.file_url || '',
                f.title || '',
                f.category || '',
                f.status || '',
                f.chunk_count || 0,
                f.indexed_at || '',
                f.markdown_updated_at || '',
            ]);
            const csv = [headers, ...rows]
                .map((row) => row.map((v) => csvEscape(v)).join(','))
                .join('\n');
            const ts = new Date().toISOString().slice(0, 19).replace(/:/g, '-');
            const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${kbId}_filelist_${ts}.csv`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            notify('KB file list exported', 'success');
        } catch (err) {
            notify(`Export failed: ${formatError(err)}`, 'error');
        }
    }

    async function loadFileSelectorPage() {
        const body = document.getElementById('rag-file-selector-body');
        if (!body) return;
        body.innerHTML = '<tr><td colspan="6">Loading...</td></tr>';
        const qp = new URLSearchParams({
            limit: String(state.fileSelector.pageSize),
            offset: String(state.fileSelector.offset),
            query: state.fileSelector.query || '',
            category: state.fileSelector.category || '',
        });
        if (state.fileSelector.target === 'detail' && context.kbId) {
            qp.set('kb_id', context.kbId);
        }
        try {
            const payload = await apiGet(`/api/rag/files/selectable?${qp.toString()}`);
            state.fileSelector.rows = payload.data?.files || [];
            state.fileSelector.total = payload.data?.total || 0;
            renderFileSelectorRows();
        } catch (err) {
            body.innerHTML = `<tr><td colspan="6">${esc(formatError(err))}</td></tr>`;
        }
    }

    function renderFileSelectorRows() {
        const body = document.getElementById('rag-file-selector-body');
        if (!body) return;
        const selectedMap = getFileSelectionMap(state.fileSelector.target);
        const checkAll = document.getElementById('rag-file-selector-check-all');
        if (!state.fileSelector.rows.length) {
            body.innerHTML = '<tr><td colspan="6">No selectable markdown files found.</td></tr>';
            if (checkAll) checkAll.checked = false;
            updateFileSelectorSummary();
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
                        <td>${esc(formatDate(row.markdown_updated_at || row.last_seen || row.crawl_time))}</td>
                    </tr>
                `;
            })
            .join('');
        body.querySelectorAll('[data-file-select]').forEach((cb) => {
            cb.addEventListener('change', () => {
                const url = cb.getAttribute('data-file-select');
                const row = state.fileSelector.rows.find((r) => r.url === url);
                if (cb.checked && row) selectedMap.set(url, row);
                if (!cb.checked) selectedMap.delete(url);
                if (state.fileSelector.target === 'create') renderCreateSelectedFiles();
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
        const count = getFileSelectionMap(state.fileSelector.target).size;
        summary.textContent = `${count} files selected`;
    }

    function openFileSelector(target) {
        state.fileSelector.target = target || 'create';
        state.fileSelector.offset = 0;
        if (state.fileSelector.target === 'detail') {
            state.selectedDetailFiles.clear();
        }
        updateFileSelectorSummary();
        openModal('rag-file-selector-modal');
        loadFileSelectorPage();
    }

    function bindFileSelector() {
        document.getElementById('rag-open-file-selector')?.addEventListener('click', () => openFileSelector('create'));
        document.getElementById('rag-file-selector-refresh')?.addEventListener('click', () => loadFileSelectorPage());
        document.getElementById('rag-file-selector-search')?.addEventListener('input', (e) => {
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
            getFileSelectionMap(state.fileSelector.target).clear();
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
            if (state.fileSelector.target === 'create') {
                closeModal('rag-file-selector-modal');
                return;
            }
            const selected = Array.from(state.selectedDetailFiles.keys());
            if (!selected.length) {
                notify('Select at least one file', 'warning');
                return;
            }
            try {
                const addResp = await apiPost(
                    `/api/rag/knowledge-bases/${encodeURIComponent(context.kbId)}/files`,
                    { file_urls: selected },
                    true
                );
                const addedCount = Number(addResp.data?.added_count || 0);
                if (addedCount <= 0) {
                    notify('No new files were added', 'warning');
                    closeModal('rag-file-selector-modal');
                    await refreshDetailPage();
                    return;
                }
                const indexResp = await triggerIndex(context.kbId, { fileUrls: selected });
                notify(`Added ${addedCount} file(s). Index task submitted: ${indexResp?.job_id || '-'}`, 'success');
                state.selectedDetailFiles.clear();
                closeModal('rag-file-selector-modal');
                await refreshDetailPage();
            } catch (err) {
                notify(`Add files failed: ${formatError(err)}`, 'error');
            }
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
            notify(`Failed to load KB: ${formatError(err)}`, 'error');
        }
    }

    function getSelectedCreateCategories() {
        const select = document.getElementById('rag-create-categories');
        if (!select) return [];
        return Array.from(select.selectedOptions).map((o) => o.value).filter(Boolean);
    }

    async function refreshCreateCategoryStats() {
        const statsEl = document.getElementById('rag-create-category-stats');
        const modeInput = document.querySelector('#rag-create-kb-form input[name="kb_mode"]:checked');
        if (!statsEl) return;
        if (!modeInput || modeInput.value !== 'category') {
            statsEl.textContent = 'Select categories to view unique file and markdown counts.';
            return;
        }
        const categories = getSelectedCreateCategories();
        if (!categories.length) {
            statsEl.textContent = 'Select categories to view unique file and markdown counts.';
            return;
        }
        statsEl.textContent = 'Loading category statistics...';
        try {
            const payload = { categories };
            if (context.page === 'detail' && context.kbId) payload.kb_id = context.kbId;
            const resp = await apiPost('/api/rag/categories/stats', payload, false);
            const stats = resp.data || {};
            statsEl.textContent =
                `Unique files: ${Number(stats.unique_files || 0)} | ` +
                `Unique markdown files: ${Number(stats.unique_markdown_files || 0)} | ` +
                `Already in this RAG: ${Number(stats.in_kb_markdown_files || 0)}`;
        } catch (err) {
            statsEl.textContent = `Failed to load stats: ${formatError(err)}`;
        }
    }

    function bindCreateEditForms() {
        const createForm = document.getElementById('rag-create-kb-form');
        const editForm = document.getElementById('rag-edit-kb-form');
        const modeInputs = createForm?.querySelectorAll('input[name="kb_mode"]') || [];
        const createNameInput = createForm?.querySelector('[name="name"]');
        const createCategories = document.getElementById('rag-create-categories');
        const createChunkProfileSelect = document.getElementById('rag-create-chunk-profile');

        const syncCreateMode = () => {
            if (!createForm) return;
            const mode = createForm.querySelector('input[name="kb_mode"]:checked')?.value || 'category';
            const isCategory = mode === 'category';
            const c = document.getElementById('rag-create-category-fields');
            const m = document.getElementById('rag-create-manual-fields');
            if (c) c.style.display = isCategory ? 'block' : 'none';
            if (m) m.style.display = isCategory ? 'none' : 'block';
            refreshCreateCategoryStats();
        };

        const resetCreateForm = () => {
            if (!createForm) return;
            createForm.reset();
            const categoryRadio = createForm.querySelector('input[name="kb_mode"][value="category"]');
            if (categoryRadio) categoryRadio.checked = true;
            state.selectedCreateFiles.clear();
            renderCreateSelectedFiles();
            syncCreateKbId();
            if (createChunkProfileSelect) createChunkProfileSelect.value = '';
            syncCreateChunkProfileMode();
            syncCreateMode();
        };

        const openCreateModal = async () => {
            resetCreateForm();
            await loadChunkProfiles();
            if (!state.chunkProfiles.length) {
                notify('No chunk profiles found. Create one from Chunk Profiles first.', 'warning');
            }
            openModal('rag-create-kb-modal');
        };

        modeInputs.forEach((input) => input.addEventListener('change', syncCreateMode));
        createNameInput?.addEventListener('input', () => syncCreateKbId());
        createCategories?.addEventListener('change', () => refreshCreateCategoryStats());
        createChunkProfileSelect?.addEventListener('change', () => syncCreateChunkProfileMode());

        document.getElementById('rag-open-create-modal')?.addEventListener('click', openCreateModal);

        document.getElementById('rag-create-from-unmapped')?.addEventListener('click', async () => {
            if (!createForm) return;
            resetCreateForm();
            const select = document.getElementById('rag-create-categories');
            if (select) {
                const preselect = new Set(state.unmapped.slice(0, 6).map((x) => x.name));
                Array.from(select.options).forEach((opt) => {
                    opt.selected = preselect.has(opt.value);
                });
            }
            refreshCreateCategoryStats();
            await loadChunkProfiles();
            if (!state.chunkProfiles.length) {
                notify('No chunk profiles found. Create one from Chunk Profiles first.', 'warning');
            }
            openModal('rag-create-kb-modal');
        });

        document.getElementById('rag-dismiss-unmapped')?.addEventListener('click', () => {
            localStorage.setItem('rag_unmapped_dismissed', '1');
            const alert = document.getElementById('rag-unmapped-alert');
            if (alert) alert.style.display = 'none';
        });

        document.getElementById('rag-open-profiles-modal')?.addEventListener('click', async () => {
            openModal('rag-chunk-profile-modal');
            await loadChunkProfiles();
        });

        document.getElementById('rag-create-chunk-profile-form')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            const form = e.currentTarget;
            const formData = new FormData(form);
            const body = {
                name: String(formData.get('name') || '').trim(),
                chunk_size: Number(formData.get('chunk_size') || 800),
                chunk_overlap: Number(formData.get('chunk_overlap') || 100),
                splitter: String(formData.get('splitter') || 'semantic').trim() || 'semantic',
                tokenizer: String(formData.get('tokenizer') || 'cl100k_base').trim() || 'cl100k_base',
                version: String(formData.get('version') || 'v1').trim() || 'v1',
                metadata: {
                    chunk_model: String(formData.get('chunk_model') || 'gpt-4').trim() || 'gpt-4',
                },
            };
            if (!body.name) {
                notify('Profile name is required', 'warning');
                return;
            }
            try {
                await apiPost('/api/chunk/profiles', body, true);
                notify('Chunk profile saved', 'success');
                await loadChunkProfiles();
            } catch (err) {
                notify(`Save profile failed: ${formatError(err)}`, 'error');
            }
        });

        async function submitCreate(createAndIndex) {
            if (!createForm) return;
            syncCreateKbId();
            const formData = new FormData(createForm);
            const mode = formData.get('kb_mode');
            const selectedChunkProfileId = String(formData.get('chunk_profile_id') || '').trim();
            const selectedChunkProfile =
                selectedChunkProfileId
                    ? state.chunkProfiles.find((p) => p.profile_id === selectedChunkProfileId)
                    : null;
            if (!selectedChunkProfile) {
                notify('Please select an existing chunk profile', 'warning');
                return;
            }
            const payload = {
                kb_id: String(formData.get('kb_id') || ''),
                name: String(formData.get('name') || '').trim(),
                description: String(formData.get('description') || ''),
                kb_mode: mode,
                embedding_model: formData.get('embedding_model'),
                chunk_size: Number(selectedChunkProfile.chunk_size || 800),
                chunk_overlap: Number(selectedChunkProfile.chunk_overlap || 100),
                chunk_profile_id: selectedChunkProfile.profile_id,
            };

            if (!payload.name) {
                notify('Name is required', 'warning');
                return;
            }

            if (mode === 'category') {
                payload.categories = getSelectedCreateCategories();
                if (!payload.categories.length) {
                    notify('Select at least one category', 'warning');
                    return;
                }
            } else {
                payload.file_urls = Array.from(state.selectedCreateFiles.keys());
                if (!payload.file_urls.length) {
                    notify('Manual mode requires at least one file', 'warning');
                    return;
                }
            }
            try {
                const created = await apiPost('/api/rag/knowledge-bases', payload, true);
                const createdKbId = created.data?.kb_id || payload.kb_id;
                closeModal('rag-create-kb-modal');
                notify('Knowledge base created', 'success');
                if (createAndIndex && createdKbId) {
                    const indexResp =
                        mode === 'manual'
                            ? await triggerIndex(createdKbId, { fileUrls: payload.file_urls || [] })
                            : await triggerIndex(createdKbId, { reindexAll: false });
                    if (indexResp?.job_id) {
                        notify(`Index task submitted: ${indexResp.job_id}`, 'success');
                    }
                }
                if (context.page === 'list') {
                    await refreshListPage();
                } else if (createdKbId) {
                    window.location.href = `/rag/${encodeURIComponent(createdKbId)}`;
                }
            } catch (err) {
                notify(`Create failed: ${formatError(err)}`, 'error');
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
                notify(`Update failed: ${formatError(err)}`, 'error');
            }
        });
    }

    async function refreshListPage() {
        await Promise.all([loadKbs(), loadCategories(), loadUnmappedCategories()]);
        await loadKbCategoryMappings();
        renderCategorySidebar();
        renderKbTable();
    }

    function updateDetailReindexButton() {
        const reindexBtn = document.getElementById('rag-detail-reindex');
        if (!reindexBtn) return;
        const pendingFiles = Number(state.detailPendingFiles || 0);
        const composition = state.detailComposition || {};
        const needsReindex = !!composition.needs_reindex;
        const outdatedBindingCount = Number(composition.outdated_binding_count || 0);
        const showBtn = pendingFiles > 0 || needsReindex;
        if (!showBtn) {
            reindexBtn.style.display = 'none';
            reindexBtn.removeAttribute('data-pending-files');
            reindexBtn.removeAttribute('data-needs-reindex');
            return;
        }
        reindexBtn.style.display = '';
        reindexBtn.setAttribute('data-pending-files', String(pendingFiles));
        reindexBtn.setAttribute('data-needs-reindex', needsReindex ? '1' : '0');
        if (pendingFiles > 0) {
            reindexBtn.textContent = `Reindex (${pendingFiles})`;
        } else if (outdatedBindingCount > 0) {
            reindexBtn.textContent = `Rebuild Index (${outdatedBindingCount} outdated binding${outdatedBindingCount > 1 ? 's' : ''})`;
        } else {
            reindexBtn.textContent = 'Rebuild Index';
        }
    }

    function renderDetailComposition() {
        const composition = state.detailComposition || {};
        const syncSummaryEl = document.getElementById('rag-sync-status-summary');
        const profileEl = document.getElementById('rag-meta-chunk-profile');
        if (!syncSummaryEl) return;

        const modeCounts = composition.binding_mode_counts || {};
        const followLatest = Number(modeCounts.follow_latest || 0);
        const pin = Number(modeCounts.pin || 0);
        const outdated = Number(composition.outdated_binding_count || 0);
        const needsReindex = !!composition.needs_reindex;
        const hasIndex = !!composition.has_index;
        const latestIndex = composition.latest_index || null;
        const latestIndexBuiltAt = latestIndex ? formatDate(latestIndex.built_at || latestIndex.created_at || '') : '-';

        syncSummaryEl.textContent =
            `Index: ${hasIndex ? 'Available' : 'Missing'} | Latest Built: ${latestIndexBuiltAt} | ` +
            `Needs Reindex: ${needsReindex ? 'Yes' : 'No'} | Follow Latest: ${followLatest} | Pin: ${pin} | Outdated: ${outdated}`;

        if (profileEl) {
            const bindings = Array.isArray(composition.bindings) ? composition.bindings : [];
            const names = new Set();
            bindings.forEach((b) => {
                const name = String(b.profile_name || b.profile_id || '').trim();
                if (name) names.add(name);
            });
            if (!names.size) {
                profileEl.textContent = state.detailProfileSummary || '-';
            } else if (names.size === 1) {
                profileEl.textContent = Array.from(names)[0];
            } else {
                profileEl.textContent = `Mixed (${names.size})`;
            }
        }
    }

    async function loadDetailComposition() {
        try {
            const payload = await apiGet(`/api/rag/knowledge-bases/${encodeURIComponent(context.kbId)}/composition/status?limit=300`);
            state.detailComposition = payload.data || {};
        } catch (err) {
            state.detailComposition = null;
            const syncSummaryEl = document.getElementById('rag-sync-status-summary');
            if (syncSummaryEl) syncSummaryEl.textContent = 'Unable to determine sync status.';
            updateDetailReindexButton();
            return;
        }
        renderDetailComposition();
        updateDetailReindexButton();
    }

    async function loadDetailHeader() {
        const payload = await apiGet(`/api/rag/knowledge-bases/${encodeURIComponent(context.kbId)}`);
        const kb = payload.data || {};
        state.currentKb = kb;
        document.getElementById('rag-detail-title').textContent = kb.name || kb.kb_id || 'Knowledge Base';
        document.getElementById('rag-detail-description').textContent = kb.description || '';
        document.getElementById('rag-meta-kb-id').textContent = kb.kb_id || '-';
        document.getElementById('rag-meta-mode').textContent = getKbModeBadge(kb.kb_mode);
        document.getElementById('rag-meta-embedding').textContent = kb.embedding_model || '-';
        document.getElementById('rag-meta-chunk-profile').textContent = state.detailProfileSummary || '-';
        document.getElementById('rag-meta-chunk-size').textContent = kb.chunk_size || '-';
        document.getElementById('rag-meta-chunk-overlap').textContent = kb.chunk_overlap || '-';
        document.getElementById('rag-meta-updated').textContent = formatDate(kb.updated_at);

        const stats = kb.stats || {};
        const pendingFiles = Number(stats.pending_files ?? 0);
        state.detailPendingFiles = pendingFiles;
        document.getElementById('rag-stat-total-files').textContent = stats.total_files ?? kb.file_count ?? 0;
        document.getElementById('rag-stat-indexed-files').textContent = stats.indexed_files ?? 0;
        document.getElementById('rag-stat-pending-files').textContent = pendingFiles;
        document.getElementById('rag-stat-total-chunks').textContent = stats.total_chunks ?? kb.chunk_count ?? 0;
        updateDetailReindexButton();
    }

    function getDetailSortValue(fileRow, sortKey) {
        const row = fileRow || {};
        switch (sortKey) {
            case 'filename':
                return String(row.title || row.file_url || '');
            case 'chunks':
                return Number(row.chunk_count || 0);
            case 'no_versions':
                return Number(row.chunk_version_count || 0);
            case 'chunk_time':
                return parseTimestamp(row.chunk_set_updated_at || row.bound_at || '');
            case 'markdown_time':
                return parseTimestamp(row.markdown_updated_at || '');
            case 'index_status': {
                const status = String(row.status || 'pending').toLowerCase();
                if (status === 'indexed') return 2;
                if (status === 'stale') return 1;
                return 0;
            }
            case 'index_time':
                return parseTimestamp(row.indexed_at || '');
            default:
                return null;
        }
    }

    function renderDetailSortIndicators() {
        const headers = document.querySelectorAll('#rag-tab-files th.sortable[data-sort-key]');
        headers.forEach((th) => {
            const key = th.getAttribute('data-sort-key');
            th.classList.remove('sort-asc', 'sort-desc');
            if (key !== state.detailSortKey) return;
            th.classList.add(state.detailSortDirection === 'asc' ? 'sort-asc' : 'sort-desc');
        });
    }

    function enableDetailFilesColumnResize() {
        if (state.detailColumnResizeReady) return;
        const table = document.getElementById('rag-detail-files-table');
        if (!table) return;
        const headers = table.querySelectorAll('thead th');
        headers.forEach((th, idx) => {
            if (idx === 0 || idx === headers.length - 1) return;
            if (th.querySelector('.col-resizer')) return;
            const resizer = document.createElement('div');
            resizer.className = 'col-resizer';
            resizer.addEventListener('mousedown', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const startX = e.clientX;
                const startWidth = th.getBoundingClientRect().width;
                const onMove = (moveEvent) => {
                    const delta = moveEvent.clientX - startX;
                    const nextWidth = Math.max(60, Math.round(startWidth + delta));
                    th.style.width = `${nextWidth}px`;
                    th.style.maxWidth = `${nextWidth}px`;
                };
                const onUp = () => {
                    document.removeEventListener('mousemove', onMove);
                    document.removeEventListener('mouseup', onUp);
                };
                document.addEventListener('mousemove', onMove);
                document.addEventListener('mouseup', onUp);
            });
            th.appendChild(resizer);
        });
        state.detailColumnResizeReady = true;
    }

    async function loadDetailFiles() {
        const payload = await apiGet(`/api/rag/knowledge-bases/${encodeURIComponent(context.kbId)}/files`);
        const rows = payload.data?.files || [];
        state.detailProfileSummary = payload.data?.profile_summary || '-';
        const profileEl = document.getElementById('rag-meta-chunk-profile');
        if (profileEl) profileEl.textContent = state.detailProfileSummary;
        state.detailFiles = rows;
        const search = (document.getElementById('rag-detail-file-search')?.value || '').toLowerCase();
        const filtered = rows.filter((f) => !search || (f.title || f.file_url || '').toLowerCase().includes(search));
        const filteredUrls = new Set(filtered.map((f) => String(f.file_url || '')));
        state.detailFileSelection = new Set(
            Array.from(state.detailFileSelection).filter((url) => filteredUrls.has(url))
        );
        const sorted = filtered.slice().sort((a, b) => {
            const left = getDetailSortValue(a, state.detailSortKey);
            const right = getDetailSortValue(b, state.detailSortKey);
            const primary = compareMaybe(left, right, state.detailSortDirection);
            if (primary !== 0) return primary;
            const tieLeft = String(a.title || a.file_url || '');
            const tieRight = String(b.title || b.file_url || '');
            return tieLeft.localeCompare(tieRight);
        });

        const totalPages = Math.max(1, Math.ceil(sorted.length / state.detailPageSize));
        if (state.detailPage > totalPages) state.detailPage = totalPages;
        const start = (state.detailPage - 1) * state.detailPageSize;
        const paged = sorted.slice(start, start + state.detailPageSize);

        const body = document.getElementById('rag-detail-files-body');
        if (!paged.length) {
            body.innerHTML = '<tr><td colspan="10">No files found.</td></tr>';
            renderDetailFilesPagination(sorted.length, totalPages);
            renderDetailSortIndicators();
            updateDetailBulkRemoveButton();
            return;
        }

        body.innerHTML = paged
            .map((f, idx) => {
                const fileUrl = String(f.file_url || '');
                const rowNo = start + idx + 1;
                const checked = state.detailFileSelection.has(fileUrl);
                const returnToUrl = `/rag/${encodeURIComponent(context.kbId)}`;
                const fileDetailUrl = `/file/${encodeURIComponent(fileUrl)}?return_to=${encodeURIComponent(returnToUrl)}`;
                return `
                <tr>
                    <td class="row-select">
                        <input type="checkbox" data-detail-file-check="${esc(fileUrl)}" ${checked ? 'checked' : ''}>
                    </td>
                    <td>${rowNo}</td>
                    <td title="${esc(fileUrl)}">
                        <a href="${esc(fileDetailUrl)}" style="color: var(--primary-500); text-decoration: none;">
                            ${esc(f.title || f.file_url)}
                        </a>
                    </td>
                    <td>${f.chunk_count || 0}</td>
                    <td>${Number(f.chunk_version_count || 0)}</td>
                    <td>${esc(formatDate(f.chunk_set_updated_at || f.bound_at || ''))}</td>
                    <td>${esc(formatDate(f.markdown_updated_at || ''))}</td>
                    <td><span class="rag-status ${esc(f.status || 'pending')}">${esc(f.status || 'pending')}</span></td>
                    <td>${esc(formatDate(f.indexed_at))}</td>
                    <td>
                        <div class="rag-actions">
                            <button class="btn btn-secondary btn-sm" data-remove-detail-file="${esc(fileUrl)}">Delete</button>
                        </div>
                    </td>
                </tr>
            `
            })
            .join('');

        const checkAll = document.getElementById('rag-detail-files-check-all');
        if (checkAll) {
            checkAll.checked = paged.length > 0 && paged.every((f) => state.detailFileSelection.has(String(f.file_url || '')));
        }

        body.querySelectorAll('[data-detail-file-check]').forEach((cb) => {
            cb.addEventListener('change', () => {
                const fileUrl = String(cb.getAttribute('data-detail-file-check') || '');
                if (!fileUrl) return;
                if (cb.checked) state.detailFileSelection.add(fileUrl);
                else state.detailFileSelection.delete(fileUrl);
                if (checkAll) {
                    checkAll.checked = paged.length > 0 && paged.every((f) => state.detailFileSelection.has(String(f.file_url || '')));
                }
                updateDetailBulkRemoveButton();
            });
        });

        body.querySelectorAll('[data-remove-detail-file]').forEach((btn) => {
            btn.addEventListener('click', async () => {
                const fileUrl = btn.getAttribute('data-remove-detail-file');
                const ok = await confirmDeleteWithText(
                    'Remove File From KB',
                    'This will remove the file from this knowledge base.'
                );
                if (!ok) return;
                try {
                    await apiDelete(`/api/rag/knowledge-bases/${encodeURIComponent(context.kbId)}/files/${encodeURIComponent(fileUrl)}`);
                    await refreshDetailPage();
                    notify('File removed from KB', 'success');
                } catch (err) {
                    notify(`Remove failed: ${formatError(err)}`, 'error');
                }
            });
        });

        renderDetailFilesPagination(sorted.length, totalPages);
        renderDetailSortIndicators();
        updateDetailBulkRemoveButton();
    }

    function renderDetailFilesPagination(totalItems, totalPages) {
        const wrap = document.getElementById('rag-detail-files-pagination');
        if (!wrap) return;
        const page = state.detailPage;
        if (totalItems <= state.detailPageSize) {
            wrap.innerHTML = `<span class="text-muted">${totalItems} files</span>`;
            return;
        }
        wrap.innerHTML = `
            <div class="text-muted">${totalItems} files</div>
            <div class="rag-pagination-actions">
                <button type="button" class="btn btn-secondary btn-sm" id="rag-detail-files-prev" ${page <= 1 ? 'disabled' : ''}>Prev</button>
                <span class="text-muted">Page ${page} / ${totalPages}</span>
                <button type="button" class="btn btn-secondary btn-sm" id="rag-detail-files-next" ${page >= totalPages ? 'disabled' : ''}>Next</button>
            </div>
        `;
        document.getElementById('rag-detail-files-prev')?.addEventListener('click', () => {
            state.detailPage = Math.max(1, state.detailPage - 1);
            loadDetailFiles();
        });
        document.getElementById('rag-detail-files-next')?.addEventListener('click', () => {
            state.detailPage = Math.min(totalPages, state.detailPage + 1);
            loadDetailFiles();
        });
    }

    function updateDetailBulkRemoveButton() {
        const btn = document.getElementById('rag-detail-bulk-remove');
        if (!btn) return;
        const count = state.detailFileSelection.size;
        btn.textContent = `Bulk Remove (${count})`;
        btn.disabled = count <= 0;
    }

    async function loadDetailCategories() {
        const payload = await apiGet(`/api/rag/knowledge-bases/${encodeURIComponent(context.kbId)}/categories`);
        const categories = payload.data?.categories || [];
        const list = document.getElementById('rag-detail-categories-list');
        list.innerHTML = categories.length ? categories.map((c) => `<li>${esc(c)}</li>`).join('') : '<li>No linked categories</li>';
    }

    async function loadDetailTasks() {
        const activeBox = document.getElementById('rag-detail-active-tasks');
        const body = document.getElementById('rag-detail-tasks-body');
        if (!activeBox || !body) {
            return;
        }

        try {
            const payload = await apiGet(`/api/rag/knowledge-bases/${encodeURIComponent(context.kbId)}/tasks?limit=30`);
            const active = payload.data?.active || [];
            const history = payload.data?.history || [];

            activeBox.innerHTML = active
                .map((t) => `<div class="rag-active-task">${esc(t.name || t.id)} - ${esc(t.status || 'pending')} (${t.progress || 0}%)</div>`)
                .join('');

            if (!history.length) {
                body.innerHTML = '<tr><td colspan="5">No task history.</td></tr>';
                return;
            }

            body.innerHTML = history
                .map((t) => `<tr><td>${esc(t.name || t.id)}</td><td>${esc(t.status || '-')}</td><td>${esc(formatDate(t.started_at))}</td><td>${t.items_processed || 0}</td><td>${t.rag_total_chunks || 0}</td></tr>`)
                .join('');
        } catch (err) {
            // Handle authorization failures and other errors without rejecting
            let message = 'Unable to load tasks.';
            const status = (err && (err.status || (err.response && err.response.status))) || null;
            if (status === 403) {
                message = 'You do not have permission to view task history.';
            }
            activeBox.innerHTML = '';
            body.innerHTML = `<tr><td colspan="5" class="text-muted">${esc(message)}</td></tr>`;
        }
    }

    async function refreshDetailPage() {
        await Promise.all([
            loadDetailHeader(),
            loadDetailComposition(),
            loadDetailFiles(),
            loadDetailCategories(),
            loadDetailTasks(),
            loadCategories(),
        ]);
    }

    async function runChunkCleanup(dryRun) {
        const days = 30;
        if (!dryRun) {
            const ok = window.customConfirm
                ? await window.customConfirm(
                    `Delete unbound chunk sets older than ${days} days? This action cannot be undone.`,
                    'Cleanup Chunks'
                )
                : window.confirm(`Delete unbound chunk sets older than ${days} days?`);
            if (!ok) return;
        }
        try {
            const payload = await apiPost(
                '/api/chunk-sets/cleanup',
                { older_than_days: days, dry_run: !!dryRun },
                true
            );
            const data = payload.data || {};
            if (dryRun) {
                notify(
                    `Cleanup preview: candidates=${data.candidates || 0}, chunks=${data.deleted_chunks || 0}`,
                    'info'
                );
            } else {
                notify(
                    `Cleanup done: deleted_chunk_sets=${data.deleted_chunk_sets || 0}, deleted_chunks=${data.deleted_chunks || 0}`,
                    'success'
                );
                await loadDetailComposition();
            }
        } catch (err) {
            notify(`Chunk cleanup failed: ${formatError(err)}`, 'error');
        }
    }

    function bindDetailEvents() {
        document.getElementById('rag-detail-refresh')?.addEventListener('click', () => refreshDetailPage());
        document.getElementById('rag-detail-edit')?.addEventListener('click', () => openEditModal(context.kbId));
        document.getElementById('rag-detail-export')?.addEventListener('click', () => exportKbFileList(context.kbId));
        document.getElementById('rag-detail-reindex')?.addEventListener('click', async (e) => {
            const btn = e.currentTarget;
            const pending = Number(btn.getAttribute('data-pending-files') || 0);
            const needsReindex = btn.getAttribute('data-needs-reindex') === '1';
            if (pending <= 0 && !needsReindex) return;
            try {
                const reindexAll = pending <= 0 && needsReindex;
                const msg = pending > 0
                    ? `Start indexing ${pending} pending file(s) for this KB?`
                    : 'Chunk bindings changed. Rebuild full KB index now?';
                const resp = await triggerIndex(context.kbId, {
                    reindexAll,
                    confirmMessage: msg,
                });
                if (!resp) return;
                notify(`Index task created: ${resp.job_id || '-'}`, 'success');
                await Promise.all([loadDetailTasks(), loadDetailComposition(), loadDetailHeader()]);
            } catch (err) {
                notify(`Failed to start indexing: ${formatError(err)}`, 'error');
            }
        });
        document.getElementById('rag-detail-cleanup-chunks')?.addEventListener('click', async () => {
            await runChunkCleanup(false);
        });
        document.getElementById('rag-detail-cleanup-chunks-dry-run')?.addEventListener('click', async () => {
            await runChunkCleanup(true);
        });
        document.getElementById('rag-detail-delete')?.addEventListener('click', () => deleteKb(context.kbId));
        document.getElementById('rag-detail-add-files')?.addEventListener('click', () => openFileSelector('detail'));
        document.getElementById('rag-detail-file-search')?.addEventListener('input', () => {
            state.detailPage = 1;
            loadDetailFiles();
        });
        document.querySelectorAll('#rag-tab-files th.sortable[data-sort-key]').forEach((th) => {
            th.addEventListener('click', () => {
                const sortKey = String(th.getAttribute('data-sort-key') || '').trim();
                if (!sortKey) return;
                if (state.detailSortKey === sortKey) {
                    state.detailSortDirection = state.detailSortDirection === 'asc' ? 'desc' : 'asc';
                } else {
                    state.detailSortKey = sortKey;
                    state.detailSortDirection = ['index_time', 'chunk_time', 'markdown_time', 'chunks', 'no_versions'].includes(sortKey) ? 'desc' : 'asc';
                }
                state.detailPage = 1;
                loadDetailFiles();
            });
        });
        document.getElementById('rag-detail-files-check-all')?.addEventListener('change', (e) => {
            const checked = !!e.target.checked;
            document.querySelectorAll('[data-detail-file-check]').forEach((cb) => {
                if (cb.checked === checked) return;
                cb.checked = checked;
                cb.dispatchEvent(new Event('change'));
            });
        });
        document.getElementById('rag-detail-bulk-remove')?.addEventListener('click', async () => {
            const selected = Array.from(state.detailFileSelection);
            if (!selected.length) return;
            const ok = await confirmDeleteWithText(
                'Bulk Remove Files',
                `You are removing ${selected.length} file(s) from this KB.`
            );
            if (!ok) return;
            let removed = 0;
            for (const fileUrl of selected) {
                try {
                    await apiDelete(`/api/rag/knowledge-bases/${encodeURIComponent(context.kbId)}/files/${encodeURIComponent(fileUrl)}`);
                    removed += 1;
                } catch (_err) {
                    // Continue removing remaining selections.
                }
            }
            state.detailFileSelection.clear();
            notify(`Removed ${removed}/${selected.length} files`, removed > 0 ? 'success' : 'warning');
            await refreshDetailPage();
        });
        document.getElementById('rag-detail-link-category')?.addEventListener('click', async () => {
            const sel = document.getElementById('rag-detail-add-category-select');
            if (!sel || !sel.value) {
                notify('Select a category', 'warning');
                return;
            }
            try {
                const statsResp = await apiPost(
                    '/api/rag/categories/stats',
                    { categories: [sel.value], kb_id: context.kbId },
                    false
                );
                const stats = statsResp.data || {};
                const addable = Math.max(
                    0,
                    Number(stats.unique_markdown_files || 0) - Number(stats.in_kb_markdown_files || 0)
                );
                if (addable <= 0) {
                    notify('No new markdown files to add for this category', 'info');
                    return;
                }
                const ok = window.customConfirm
                    ? await window.customConfirm(
                        `Category "${sel.value}" will add ${addable} markdown file(s) to this KB. Continue?`,
                        'Link Category'
                    )
                    : window.confirm(`Add ${addable} markdown file(s) from category "${sel.value}" to this KB?`);
                if (!ok) return;
                await apiPost(`/api/rag/knowledge-bases/${encodeURIComponent(context.kbId)}/categories`, { categories: [sel.value] }, true);
                await refreshDetailPage();
            } catch (err) {
                notify(`Link failed: ${formatError(err)}`, 'error');
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
        await loadChunkProfiles();
        syncCreateKbId();
        refreshCreateCategoryStats();
        renderCreateSelectedFiles();

        const params = new URLSearchParams(window.location.search);
        if (params.get('open') === 'create') {
            document.getElementById('rag-open-create-modal')?.click();
            params.delete('open');
            const query = params.toString();
            const nextUrl = query ? `${window.location.pathname}?${query}` : window.location.pathname;
            window.history.replaceState({}, '', nextUrl);
        }
    }

    async function initDetailPage() {
        bindCreateEditForms();
        bindFileSelector();
        bindDetailEvents();
        enableDetailFilesColumnResize();
        await refreshDetailPage();
        await loadChunkProfiles();
        syncCreateKbId();
        refreshCreateCategoryStats();
        renderCreateSelectedFiles();
        window.setInterval(() => loadDetailTasks(), 4000);
    }

    bindModalCloseButtons();
    if (context.page === 'list') initListPage();
    if (context.page === 'detail') initDetailPage();
})();
