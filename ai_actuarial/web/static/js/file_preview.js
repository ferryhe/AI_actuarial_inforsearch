/**
 * File Preview Module
 * Handles displaying original files (PDF/DOCX) alongside their markdown and chunks
 */

window.FilePreview = (function() {
    'use strict';
    
    let currentFileUrl = null;
    let currentKbId = null;
    let previewData = null;
    
    /**
     * Initialize the preview with a file URL
     */
    function init(fileUrl, kbId) {
        currentFileUrl = fileUrl;
        currentKbId = kbId || null;
        
        console.log('Initializing file preview for:', fileUrl, 'KB:', kbId);
        
        // Load preview data from API
        loadPreviewData();
    }
    
    /**
     * Load preview data from the API
     */
    function loadPreviewData() {
        const params = new URLSearchParams({ file_url: currentFileUrl });
        if (currentKbId) {
            params.append('kb_id', currentKbId);
        }
        
        fetch(`/api/rag/files/preview?${params}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(result => {
                if (result.success && result.data) {
                    previewData = result.data;
                    renderPreview();
                } else {
                    showError('Failed to load preview data: ' + (result.error || 'Unknown error'));
                }
            })
            .catch(error => {
                console.error('Error loading preview:', error);
                showError('Error loading preview: ' + error.message);
            });
    }
    
    /**
     * Render the complete preview
     */
    function renderPreview() {
        if (!previewData) return;
        
        // Update header
        updateHeader();
        
        // Render original file
        renderOriginalFile();
        
        // Render markdown
        renderMarkdown();
        
        // Render chunks
        renderChunks();
    }
    
    /**
     * Update the header with file information
     */
    function updateHeader() {
        const fileInfo = previewData.file_info;
        document.getElementById('file-title').textContent = fileInfo.title || fileInfo.original_filename || 'Untitled';
        
        const infoText = [];
        if (fileInfo.content_type) {
            infoText.push(fileInfo.content_type);
        }
        if (fileInfo.bytes) {
            infoText.push(formatBytes(fileInfo.bytes));
        }
        if (fileInfo.last_modified) {
            infoText.push('Modified: ' + new Date(fileInfo.last_modified).toLocaleString());
        }
        
        document.getElementById('file-info').textContent = infoText.join(' • ');
    }
    
    /**
     * Render the original file (PDF viewer or download link)
     */
    function renderOriginalFile() {
        const fileInfo = previewData.file_info;
        const container = document.getElementById('original-viewer-container');
        
        // Check if file has a local path
        if (!fileInfo.local_path) {
            container.innerHTML = '<p>Original file not available locally</p>';
            return;
        }
        
        const contentType = fileInfo.content_type || '';
        
        // Handle PDF files with PDF.js
        if (contentType === 'application/pdf') {
            renderPDF(container, fileInfo.url);
        }
        // Handle other file types with iframe or download link
        else if (contentType.startsWith('image/')) {
            const downloadUrl = `/api/download?url=${encodeURIComponent(fileInfo.url)}`;
            container.innerHTML = `<img src="${downloadUrl}" alt="${fileInfo.title}" style="max-width: 100%; height: auto;" />`;
        }
        else {
            // For other file types, provide a download link
            const downloadUrl = `/api/download?url=${encodeURIComponent(fileInfo.url)}`;
            container.innerHTML = `
                <div style="text-align: center; padding: 2rem;">
                    <p>Preview not available for this file type.</p>
                    <p style="margin-top: 1rem;">
                        <a href="${downloadUrl}" class="btn btn-primary" download>
                            Download ${fileInfo.original_filename || 'File'}
                        </a>
                    </p>
                </div>
            `;
        }
    }
    
    /**
     * Render PDF using PDF.js
     */
    function renderPDF(container, fileUrl) {
        const downloadUrl = `/api/download?url=${encodeURIComponent(fileUrl)}`;
        
        // Create canvas for PDF rendering
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
        const ctx = canvas.getContext('2d');
        
        // Load PDF
        pdfjsLib.getDocument(downloadUrl).promise
            .then(pdf => {
                pdfDoc = pdf;
                document.getElementById('pdf-page-info').textContent = `Page 1 of ${pdf.numPages}`;
                renderPage(1);
                
                // Setup navigation
                document.getElementById('pdf-prev').addEventListener('click', () => {
                    if (currentPage > 1) {
                        currentPage--;
                        renderPage(currentPage);
                    }
                });
                
                document.getElementById('pdf-next').addEventListener('click', () => {
                    if (currentPage < pdf.numPages) {
                        currentPage++;
                        renderPage(currentPage);
                    }
                });
            })
            .catch(error => {
                console.error('Error loading PDF:', error);
                container.innerHTML = `<p>Error loading PDF: ${error.message}</p>`;
            });
        
        function renderPage(pageNum) {
            pdfDoc.getPage(pageNum).then(page => {
                const viewport = page.getViewport({ scale: 1.5 });
                canvas.height = viewport.height;
                canvas.width = viewport.width;
                
                const renderContext = {
                    canvasContext: ctx,
                    viewport: viewport
                };
                
                page.render(renderContext);
                document.getElementById('pdf-page-info').textContent = `Page ${pageNum} of ${pdfDoc.numPages}`;
            });
        }
    }
    
    /**
     * Render markdown content
     */
    function renderMarkdown() {
        const markdown = previewData.markdown;
        const container = document.getElementById('markdown-content-container');
        
        if (!markdown || !markdown.content) {
            container.innerHTML = '<p style="color: var(--text-secondary);">No markdown content available</p>';
            return;
        }
        
        // Configure marked options
        marked.setOptions({
            breaks: true,
            gfm: true
        });
        
        // Render markdown to HTML
        const htmlContent = marked.parse(markdown.content);
        
        container.innerHTML = `
            <div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 1rem;">
                Source: ${markdown.source || 'unknown'} 
                ${markdown.updated_at ? '• Updated: ' + new Date(markdown.updated_at).toLocaleString() : ''}
            </div>
            <div class="markdown-content">${htmlContent}</div>
        `;
    }
    
    /**
     * Render chunks
     */
    function renderChunks() {
        const chunks = previewData.chunks || [];
        const container = document.getElementById('chunks-list');
        
        if (chunks.length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary);">No chunks available. Select a knowledge base to view chunks.</p>';
            return;
        }
        
        const chunksHTML = chunks.map((chunk, index) => {
            return `
                <div class="chunk-item" id="chunk-${chunk.chunk_index}">
                    <div class="chunk-header">
                        <span><strong>Chunk #${chunk.chunk_index + 1}</strong></span>
                        <span>${chunk.token_count} tokens</span>
                    </div>
                    ${chunk.section_hierarchy ? `<div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.5rem;">${chunk.section_hierarchy}</div>` : ''}
                    <div class="chunk-content">${escapeHtml(chunk.content)}</div>
                </div>
            `;
        }).join('');
        
        container.innerHTML = chunksHTML;
    }
    
    /**
     * Show error message
     */
    function showError(message) {
        document.getElementById('original-viewer-container').innerHTML = `<p style="color: var(--error-color);">${escapeHtml(message)}</p>`;
        document.getElementById('markdown-content-container').innerHTML = `<p style="color: var(--error-color);">${escapeHtml(message)}</p>`;
        document.getElementById('chunks-list').innerHTML = `<p style="color: var(--error-color);">${escapeHtml(message)}</p>`;
    }
    
    /**
     * Format bytes to human readable format
     */
    function formatBytes(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
    }
    
    /**
     * Escape HTML to prevent XSS
     */
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // Public API
    return {
        init: init
    };
})();
