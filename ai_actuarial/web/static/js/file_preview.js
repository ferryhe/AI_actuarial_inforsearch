/**
 * File Preview Module
 * Handles displaying original files (PDF/DOCX) alongside their markdown and chunks.
 */

window.FilePreview = (function() {
    'use strict';

    let currentFileUrl = null;
    let currentKbId = null;
    let previewData = null;

    function loadScript(src) {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = src;
            script.async = true;
            script.onload = () => resolve(true);
            script.onerror = () => reject(new Error(`Failed to load script: ${src}`));
            document.head.appendChild(script);
        });
    }

    async function ensurePdfJsLoaded() {
        if (window.pdfjsLib) {
            return window.pdfjsLib;
        }
        const fallbackSrc = window.__PDFJS_FALLBACK_SRC || '';
        if (fallbackSrc) {
            await loadScript(fallbackSrc);
        }
        if (window.pdfjsLib && window.pdfjsLib.GlobalWorkerOptions) {
            window.pdfjsLib.GlobalWorkerOptions.workerSrc =
                window.__PDFJS_PRIMARY_WORKER || window.__PDFJS_FALLBACK_WORKER || '';
            return window.pdfjsLib;
        }
        throw new Error('PDF preview engine is unavailable (pdfjsLib not loaded)');
    }

    async function ensureMarkedLoaded() {
        if (window.marked) {
            return window.marked;
        }
        const fallbackSrc = window.__MARKED_FALLBACK_SRC || '';
        if (fallbackSrc) {
            await loadScript(fallbackSrc);
        }
        if (window.marked) {
            return window.marked;
        }
        throw new Error('Markdown renderer is unavailable (marked not loaded)');
    }

    function init(fileUrl, kbId) {
        currentFileUrl = fileUrl;
        currentKbId = kbId || null;
        loadPreviewData();
    }

    function loadPreviewData() {
        const params = new URLSearchParams({ file_url: currentFileUrl });
        if (currentKbId) {
            params.append('kb_id', currentKbId);
        }

        fetch(`/api/rag/files/preview?${params}`)
            .then((response) => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then((result) => {
                if (result.success && result.data) {
                    previewData = result.data;
                    renderPreview();
                } else {
                    showError('Failed to load preview data: ' + (result.error || 'Unknown error'));
                }
            })
            .catch((error) => {
                console.error('Error loading preview:', error);
                showError('Error loading preview: ' + error.message);
            });
    }

    function renderPreview() {
        if (!previewData) return;

        updateHeader();
        renderOriginalFile();
        void renderMarkdown();
        renderChunks();
    }

    function updateHeader() {
        const fileInfo = previewData.file_info;
        document.getElementById('file-title').textContent =
            fileInfo.title || fileInfo.original_filename || 'Untitled';

        const infoText = [];
        if (fileInfo.content_type) infoText.push(fileInfo.content_type);
        if (fileInfo.bytes) infoText.push(formatBytes(fileInfo.bytes));
        if (fileInfo.last_modified) {
            infoText.push('Modified: ' + new Date(fileInfo.last_modified).toLocaleString());
        }

        document.getElementById('file-info').textContent = infoText.join(' | ');
    }

    function renderOriginalFile() {
        const fileInfo = previewData.file_info;
        const container = document.getElementById('original-viewer-container');

        if (!fileInfo.local_path) {
            container.innerHTML = '<p>Original file not available locally</p>';
            return;
        }

        const contentType = fileInfo.content_type || '';
        if (contentType === 'application/pdf') {
            renderPDF(container, fileInfo.url);
            return;
        }
        if (contentType.startsWith('image/')) {
            const downloadUrl = `/api/download?url=${encodeURIComponent(fileInfo.url)}`;
            container.innerHTML =
                `<img src="${downloadUrl}" alt="${escapeHtml(fileInfo.title || '')}" style="max-width: 100%; height: auto;" />`;
            return;
        }

        const downloadUrl = `/api/download?url=${encodeURIComponent(fileInfo.url)}`;
        container.innerHTML = `
            <div style="text-align: center; padding: 2rem;">
                <p>Preview not available for this file type.</p>
                <p style="margin-top: 1rem;">
                    <a href="${downloadUrl}" class="btn btn-primary" download>
                        Download ${escapeHtml(fileInfo.original_filename || 'File')}
                    </a>
                </p>
            </div>
        `;
    }

    function renderPDF(container, fileUrl) {
        const downloadUrl = `/api/download?url=${encodeURIComponent(fileUrl)}`;

        container.innerHTML = `
            <div id="pdf-container" style="text-align: center;">
                <div style="margin-bottom: 1rem;">
                    <button id="pdf-prev" class="btn btn-small">Previous</button>
                    <span id="pdf-page-info" style="margin: 0 1rem;">Page 1 of 1</span>
                    <button id="pdf-next" class="btn btn-small">Next</button>
                </div>
                <canvas id="pdf-canvas" style="border: 1px solid var(--border-color); max-width: 100%;"></canvas>
            </div>
        `;

        let pdfDoc = null;
        let currentPage = 1;
        const canvas = document.getElementById('pdf-canvas');
        const ctx = canvas ? canvas.getContext('2d') : null;

        ensurePdfJsLoaded()
            .then((pdfjs) => {
                if (pdfjs && pdfjs.GlobalWorkerOptions) {
                    pdfjs.GlobalWorkerOptions.workerSrc =
                        window.__PDFJS_PRIMARY_WORKER || window.__PDFJS_FALLBACK_WORKER || '';
                }
                return pdfjs.getDocument(downloadUrl).promise;
            })
            .then((pdf) => {
                pdfDoc = pdf;
                const pageInfoEl = document.getElementById('pdf-page-info');
                if (pageInfoEl) {
                    pageInfoEl.textContent = `Page 1 of ${pdf.numPages}`;
                }
                renderPage(1);

                document.getElementById('pdf-prev')?.addEventListener('click', () => {
                    if (currentPage > 1) {
                        currentPage -= 1;
                        renderPage(currentPage);
                    }
                });

                document.getElementById('pdf-next')?.addEventListener('click', () => {
                    if (currentPage < pdf.numPages) {
                        currentPage += 1;
                        renderPage(currentPage);
                    }
                });
            })
            .catch((error) => {
                console.error('Error loading PDF:', error);
                container.innerHTML = `<p>Error loading PDF: ${escapeHtml(error.message)}</p>`;
            });

        function renderPage(pageNum) {
            if (!pdfDoc || !canvas || !ctx) return;
            pdfDoc.getPage(pageNum).then((page) => {
                const viewport = page.getViewport({ scale: 1.5 });
                canvas.height = viewport.height;
                canvas.width = viewport.width;

                const renderContext = {
                    canvasContext: ctx,
                    viewport,
                };

                page.render(renderContext);
                const pageInfoEl = document.getElementById('pdf-page-info');
                if (pageInfoEl) {
                    pageInfoEl.textContent = `Page ${pageNum} of ${pdfDoc.numPages}`;
                }
            });
        }
    }

    async function renderMarkdown() {
        const markdown = previewData.markdown;
        const container = document.getElementById('markdown-content-container');

        if (!markdown || !markdown.content) {
            container.innerHTML = '<p style="color: var(--text-secondary);">No markdown content available</p>';
            return;
        }

        try {
            const markedLib = await ensureMarkedLoaded();
            markedLib.setOptions({ breaks: true, gfm: true });
            const htmlContent = markedLib.parse(markdown.content);
            container.innerHTML = `
                <div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 1rem;">
                    Source: ${escapeHtml(markdown.source || 'unknown')}
                    ${markdown.updated_at ? '| Updated: ' + new Date(markdown.updated_at).toLocaleString() : ''}
                </div>
                <div class="markdown-content">${htmlContent}</div>
            `;
        } catch (error) {
            console.error('Error rendering markdown:', error);
            container.innerHTML = `
                <div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 1rem;">
                    Source: ${escapeHtml(markdown.source || 'unknown')}
                    ${markdown.updated_at ? '| Updated: ' + new Date(markdown.updated_at).toLocaleString() : ''}
                </div>
                <pre class="markdown-content">${escapeHtml(markdown.content)}</pre>
            `;
        }
    }

    function renderChunks() {
        const chunks = previewData.chunks || [];
        const container = document.getElementById('chunks-list');

        if (chunks.length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary);">No chunks available. Select a knowledge base to view chunks.</p>';
            return;
        }

        const chunksHTML = chunks
            .map((chunk) => `
                <div class="chunk-item" id="chunk-${chunk.chunk_index}">
                    <div class="chunk-header">
                        <span><strong>Chunk #${chunk.chunk_index + 1}</strong></span>
                        <span>${chunk.token_count} tokens</span>
                    </div>
                    ${chunk.section_hierarchy ? `<div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.5rem;">${escapeHtml(chunk.section_hierarchy)}</div>` : ''}
                    <div class="chunk-content">${escapeHtml(chunk.content)}</div>
                </div>
            `)
            .join('');

        container.innerHTML = chunksHTML;
    }

    function showError(message) {
        const msg = escapeHtml(message);
        document.getElementById('original-viewer-container').innerHTML = `<p style="color: var(--error-color);">${msg}</p>`;
        document.getElementById('markdown-content-container').innerHTML = `<p style="color: var(--error-color);">${msg}</p>`;
        document.getElementById('chunks-list').innerHTML = `<p style="color: var(--error-color);">${msg}</p>`;
    }

    function formatBytes(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    return {
        init,
    };
})();
