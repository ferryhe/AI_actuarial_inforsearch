// Main JavaScript for AI Actuarial Info Search

// Theme toggle functionality
document.addEventListener('DOMContentLoaded', () => {
    const themeToggle = document.getElementById('theme-toggle-btn');
    
    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
        });
    }
});

// Utility function to escape HTML
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Format date
function formatDate(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    if (isNaN(date.getTime())) return dateStr;
    return date.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Format bytes
function formatBytes(bytes) {
    if (bytes == null || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// ===================================
// PHASE 2: Toast Notification System
// ===================================

// Create toast container if it doesn't exist
function getToastContainer() {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    return container;
}

// Toast notification class
class Toast {
    static show(message, type = 'info', duration = 5000) {
        const container = getToastContainer();
        
        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        // Icon based on type
        const icons = {
            success: '✓',
            error: '✕',
            warning: '⚠',
            info: 'ℹ'
        };
        
        toast.innerHTML = `
            <div class="toast-icon">${icons[type] || icons.info}</div>
            <div class="toast-message">${escapeHtml(message)}</div>
            <button class="toast-close" aria-label="Close">&times;</button>
        `;
        
        container.appendChild(toast);
        
        // Show toast with animation
        setTimeout(() => toast.classList.add('show'), 10);
        
        // Close button handler
        const closeBtn = toast.querySelector('.toast-close');
        closeBtn.addEventListener('click', () => this.hide(toast));
        
        // Auto-hide after duration
        if (duration > 0) {
            setTimeout(() => this.hide(toast), duration);
        }
        
        return toast;
    }
    
    static hide(toast) {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }
    
    static success(message, duration) {
        return this.show(message, 'success', duration);
    }
    
    static error(message, duration) {
        return this.show(message, 'error', duration);
    }
    
    static warning(message, duration) {
        return this.show(message, 'warning', duration);
    }
    
    static info(message, duration) {
        return this.show(message, 'info', duration);
    }
}

// Backward compatibility - keep old showNotification function
function showNotification(message, type = 'info') {
    Toast.show(message, type);
}

// ===================================
// PHASE 2: Loading Skeleton System
// ===================================

// Show loading skeleton for a container
function showSkeleton(container, type = 'table') {
    if (!container) return;
    
    const skeletons = {
        table: `
            <div class="skeleton-table">
                ${Array(5).fill().map(() => `
                    <div class="skeleton-row">
                        <div class="skeleton-cell"></div>
                        <div class="skeleton-cell"></div>
                        <div class="skeleton-cell"></div>
                        <div class="skeleton-cell"></div>
                    </div>
                `).join('')}
            </div>
        `,
        card: `
            <div class="skeleton-card">
                <div class="skeleton skeleton-title"></div>
                <div class="skeleton skeleton-text"></div>
                <div class="skeleton skeleton-text"></div>
                <div class="skeleton skeleton-text"></div>
            </div>
        `,
        text: `<div class="skeleton skeleton-text"></div>`
    };
    
    container.innerHTML = skeletons[type] || skeletons.text;
}

// Hide skeleton and show content
function hideSkeleton(container, content) {
    if (!container) return;
    container.innerHTML = content;
}

// Highlight active nav link
document.addEventListener('DOMContentLoaded', () => {
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.nav-link');
    
    navLinks.forEach(link => {
        if (link.getAttribute('href') === currentPath) {
            link.style.color = 'var(--primary-color)';
            link.style.fontWeight = '600';
        }
    });
});

// API helper functions
const API = {
    async get(url) {
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json();
    },
    
    async post(url, data) {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json();
    }
};

// Export for use in templates
window.escapeHtml = escapeHtml;
window.formatDate = formatDate;
window.formatBytes = formatBytes;
window.showNotification = showNotification;
window.Toast = Toast;
window.showSkeleton = showSkeleton;
window.hideSkeleton = hideSkeleton;
window.API = API;

// Modal state helper (locks background scroll when any modal is open)
function syncModalState() {
    const modals = document.querySelectorAll('.modal');
    const anyOpen = Array.from(modals).some((modal) => {
        return getComputedStyle(modal).display !== 'none';
    });
    document.body.classList.toggle('modal-open', anyOpen);
}

window.syncModalState = syncModalState;

// Custom confirm dialog
function customConfirm(message, title = 'Confirm Action') {
    return new Promise((resolve) => {
        const modal = document.getElementById('confirm-modal');
        const titleEl = document.getElementById('confirm-title');
        const messageEl = document.getElementById('confirm-message');
        const okBtn = document.getElementById('confirm-ok');
        const cancelBtn = document.getElementById('confirm-cancel');
        
        titleEl.textContent = title;
        messageEl.textContent = message;
        modal.style.display = 'flex';
        syncModalState();
        
        const handleOk = () => {
            modal.style.display = 'none';
            syncModalState();
            cleanup();
            resolve(true);
        };
        
        const handleCancel = () => {
            modal.style.display = 'none';
            syncModalState();
            cleanup();
            resolve(false);
        };
        
        const cleanup = () => {
            okBtn.removeEventListener('click', handleOk);
            cancelBtn.removeEventListener('click', handleCancel);
        };
        
        okBtn.addEventListener('click', handleOk);
        cancelBtn.addEventListener('click', handleCancel);
    });
}

window.customConfirm = customConfirm;

// ===================================
// PHASE 3: Component Upgrades
// ===================================

// 3.1 Advanced DataTable Class
class DataTable {
    constructor(container, options = {}) {
        this.container = typeof container === 'string' ? document.querySelector(container) : container;
        this.options = {
            data: options.data || [],
            columns: options.columns || [],
            sortable: options.sortable !== false,
            selectable: options.selectable || false,
            resizable: options.resizable || false,
            exportable: options.exportable !== false,
            exportFilename: options.exportFilename || 'data_export',
            onRowClick: options.onRowClick || null,
            onSelectionChange: options.onSelectionChange || null
        };
        
        this.sortColumn = null;
        this.sortDirection = 'asc';
        this.selectedRows = new Set();
        
        this.render();
    }
    
    render() {
        if (!this.container) return;
        
        const wrapper = document.createElement('div');
        wrapper.className = 'data-table-wrapper';
        
        // Add toolbar
        if (this.options.selectable || this.options.exportable) {
            wrapper.appendChild(this.createToolbar());
        }
        
        // Add table
        const table = document.createElement('table');
        table.className = 'data-table';
        
        // Add header
        table.appendChild(this.createHeader());
        
        // Add body
        table.appendChild(this.createBody());
        
        wrapper.appendChild(table);
        this.container.innerHTML = '';
        this.container.appendChild(wrapper);
    }
    
    createToolbar() {
        const toolbar = document.createElement('div');
        toolbar.className = 'table-toolbar';
        
        const left = document.createElement('div');
        left.className = 'table-toolbar-left';
        
        if (this.options.selectable) {
            const selectedCount = document.createElement('span');
            selectedCount.className = 'selected-count';
            selectedCount.textContent = `${this.selectedRows.size} selected`;
            left.appendChild(selectedCount);
        }
        
        const right = document.createElement('div');
        right.className = 'table-toolbar-right';
        
        if (this.options.exportable) {
            const exportBtn = document.createElement('button');
            exportBtn.className = 'btn-export';
            exportBtn.innerHTML = `
                <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="7 10 12 15 17 10"></polyline>
                    <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
                Export CSV
            `;
            exportBtn.addEventListener('click', () => this.exportToCSV(this.options.exportFilename));
            right.appendChild(exportBtn);
        }
        
        toolbar.appendChild(left);
        toolbar.appendChild(right);
        
        return toolbar;
    }
    
    createHeader() {
        const thead = document.createElement('thead');
        const tr = document.createElement('tr');
        
        // Add selection column
        if (this.options.selectable) {
            const th = document.createElement('th');
            th.className = 'row-select';
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.addEventListener('change', (e) => this.selectAll(e.target.checked));
            th.appendChild(checkbox);
            tr.appendChild(th);
        }
        
        // Add data columns
        this.options.columns.forEach(column => {
            const th = document.createElement('th');
            if (this.options.sortable && column.sortable !== false) {
                th.className = 'sortable';
                th.addEventListener('click', () => this.sort(column.key));
            }
            th.textContent = column.label || column.key;
            tr.appendChild(th);
        });
        
        thead.appendChild(tr);
        return thead;
    }
    
    createBody() {
        const tbody = document.createElement('tbody');
        
        this.options.data.forEach((row, index) => {
            const tr = document.createElement('tr');
            tr.dataset.index = index;
            
            if (this.selectedRows.has(index)) {
                tr.classList.add('selected');
            }
            
            // Add selection column
            if (this.options.selectable) {
                const td = document.createElement('td');
                td.className = 'row-select';
                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.checked = this.selectedRows.has(index);
                checkbox.addEventListener('change', (e) => {
                    e.stopPropagation();
                    this.toggleRow(index);
                });
                td.appendChild(checkbox);
                tr.appendChild(td);
            }
            
            // Add data columns
            this.options.columns.forEach(column => {
                const td = document.createElement('td');
                const value = row[column.key];
                
                if (column.render) {
                    td.innerHTML = column.render(value, row);
                } else {
                    td.textContent = value;
                }
                
                tr.appendChild(td);
            });
            
            // Add click handler
            if (this.options.onRowClick) {
                tr.style.cursor = 'pointer';
                tr.addEventListener('click', () => this.options.onRowClick(row, index));
            }
            
            tbody.appendChild(tr);
        });
        
        return tbody;
    }
    
    sort(columnKey) {
        // Toggle direction if same column, otherwise default to asc
        if (this.sortColumn === columnKey) {
            this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            this.sortColumn = columnKey;
            this.sortDirection = 'asc';
        }
        
        // Sort data
        this.options.data.sort((a, b) => {
            let aVal = a[columnKey];
            let bVal = b[columnKey];
            
            // Handle null/undefined
            if (aVal == null) return 1;
            if (bVal == null) return -1;
            
            // Numeric comparison
            if (typeof aVal === 'number' && typeof bVal === 'number') {
                return this.sortDirection === 'asc' ? aVal - bVal : bVal - aVal;
            }
            
            // String comparison
            aVal = String(aVal).toLowerCase();
            bVal = String(bVal).toLowerCase();
            
            if (this.sortDirection === 'asc') {
                return aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
            } else {
                return aVal > bVal ? -1 : aVal < bVal ? 1 : 0;
            }
        });
        
        // Update sort indicators
        const ths = this.container.querySelectorAll('th.sortable');
        ths.forEach(th => {
            th.classList.remove('sort-asc', 'sort-desc');
        });
        
        // Re-render
        this.render();
        
        // Apply sort class to active column
        const colIndex = this.options.columns.findIndex(col => col.key === columnKey);
        if (colIndex >= 0) {
            const offset = this.options.selectable ? 1 : 0;
            const th = this.container.querySelectorAll('th')[colIndex + offset];
            if (th) {
                th.classList.add(`sort-${this.sortDirection}`);
            }
        }
    }
    
    toggleRow(index) {
        if (this.selectedRows.has(index)) {
            this.selectedRows.delete(index);
        } else {
            this.selectedRows.add(index);
        }
        
        this.updateSelection();
        
        if (this.options.onSelectionChange) {
            const selectedData = Array.from(this.selectedRows).map(i => this.options.data[i]);
            this.options.onSelectionChange(selectedData);
        }
    }
    
    selectAll(checked) {
        this.selectedRows.clear();
        
        if (checked) {
            this.options.data.forEach((_, index) => {
                this.selectedRows.add(index);
            });
        }
        
        this.updateSelection();
        
        if (this.options.onSelectionChange) {
            const selectedData = Array.from(this.selectedRows).map(i => this.options.data[i]);
            this.options.onSelectionChange(selectedData);
        }
    }
    
    updateSelection() {
        const rows = this.container.querySelectorAll('tbody tr');
        rows.forEach((row, index) => {
            const checkbox = row.querySelector('input[type="checkbox"]');
            if (checkbox) {
                checkbox.checked = this.selectedRows.has(index);
            }
            row.classList.toggle('selected', this.selectedRows.has(index));
        });
        
        // Update header checkbox
        const headerCheckbox = this.container.querySelector('thead input[type="checkbox"]');
        if (headerCheckbox) {
            headerCheckbox.checked = this.selectedRows.size === this.options.data.length;
            headerCheckbox.indeterminate = this.selectedRows.size > 0 && this.selectedRows.size < this.options.data.length;
        }
        
        // Update selected count
        const selectedCount = this.container.querySelector('.selected-count');
        if (selectedCount) {
            selectedCount.textContent = `${this.selectedRows.size} selected`;
        }
    }
    
    exportToCSV(filename = 'data_export') {
        if (!this.options.data.length) {
            Toast.warning('No data to export');
            return;
        }
        
        // Get data to export (selected or all)
        const dataToExport = this.selectedRows.size > 0
            ? Array.from(this.selectedRows).map(i => this.options.data[i])
            : this.options.data;
        
        // Create CSV content
        const headers = this.options.columns.map(col => col.label || col.key);
        const rows = dataToExport.map(row => 
            this.options.columns.map(col => {
                const value = row[col.key];
                // Escape quotes and wrap in quotes if contains comma or quote
                const str = String(value == null ? '' : value);
                return str.includes(',') || str.includes('"') 
                    ? `"${str.replace(/"/g, '""')}"` 
                    : str;
            })
        );
        
        const csv = [headers, ...rows].map(row => row.join(',')).join('\n');
        
        // Download CSV with descriptive filename
        const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-');
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        link.setAttribute('href', url);
        link.setAttribute('download', `${filename}_${timestamp}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        Toast.success('Data exported successfully');
    }
}

// 3.2 Enhanced Modal System
class ModalManager {
    static currentModal = null;
    
    static open(modalId, options = {}) {
        const modal = document.getElementById(modalId);
        if (!modal) return;
        
        // Apply size class if specified
        if (options.size) {
            const content = modal.querySelector('.modal-content');
            if (content) {
                content.classList.add(`modal-${options.size}`);
            }
        }
        
        modal.style.display = 'flex';
        this.currentModal = modal;
        syncModalState();
        
        // Focus trap
        this.setupFocusTrap(modal);
        
        // ESC key handler
        const escHandler = (e) => {
            if (e.key === 'Escape') {
                this.close(modalId);
                document.removeEventListener('keydown', escHandler);
            }
        };
        document.addEventListener('keydown', escHandler);
    }
    
    static close(modalId) {
        const modal = document.getElementById(modalId);
        if (!modal) return;
        
        modal.style.display = 'none';
        this.currentModal = null;
        syncModalState();
    }
    
    static setupFocusTrap(modal) {
        const focusableElements = modal.querySelectorAll(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        
        if (focusableElements.length === 0) return;
        
        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];
        
        const trapFocus = (e) => {
            if (e.key !== 'Tab') return;
            
            if (e.shiftKey) {
                if (document.activeElement === firstElement) {
                    e.preventDefault();
                    lastElement.focus();
                }
            } else {
                if (document.activeElement === lastElement) {
                    e.preventDefault();
                    firstElement.focus();
                }
            }
        };
        
        modal.addEventListener('keydown', trapFocus);
        firstElement.focus();
    }
}

// 3.3 Advanced Search with Autocomplete
class SearchAutocomplete {
    constructor(inputElement, options = {}) {
        this.input = typeof inputElement === 'string' ? document.querySelector(inputElement) : inputElement;
        this.options = {
            onSearch: options.onSearch || (() => {}),
            onSelect: options.onSelect || (() => {}),
            getSuggestions: options.getSuggestions || (() => []),
            minLength: options.minLength || 2,
            debounceDelay: options.debounceDelay || 300,
            showHistory: options.showHistory !== false,
            maxHistory: options.maxHistory || 5
        };
        
        this.dropdown = null;
        this.activeIndex = -1;
        this.suggestions = [];
        this.history = this.loadHistory();
        this.debounceTimer = null;
        
        this.init();
    }
    
    init() {
        if (!this.input) return;
        
        // Wrap input in autocomplete container
        const wrapper = document.createElement('div');
        wrapper.className = 'search-autocomplete';
        this.input.parentNode.insertBefore(wrapper, this.input);
        wrapper.appendChild(this.input);
        
        // Add clear button
        const clearBtn = document.createElement('button');
        clearBtn.className = 'search-clear';
        clearBtn.innerHTML = '&times;';
        clearBtn.style.display = 'none';
        clearBtn.addEventListener('click', () => this.clear());
        wrapper.appendChild(clearBtn);
        this.clearBtn = clearBtn;
        
        // Create dropdown
        this.dropdown = document.createElement('div');
        this.dropdown.className = 'autocomplete-dropdown';
        wrapper.appendChild(this.dropdown);
        
        // Event listeners
        this.input.addEventListener('input', () => this.handleInput());
        this.input.addEventListener('focus', () => this.handleFocus());
        this.input.addEventListener('keydown', (e) => this.handleKeydown(e));
        
        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (!wrapper.contains(e.target)) {
                this.hideDropdown();
            }
        });
    }
    
    handleInput() {
        const query = this.input.value.trim();
        
        // Show/hide clear button
        this.clearBtn.style.display = query ? 'block' : 'none';
        
        // Clear existing timer
        clearTimeout(this.debounceTimer);
        
        if (query.length < this.options.minLength) {
            this.hideDropdown();
            return;
        }
        
        // Debounce the search
        this.debounceTimer = setTimeout(() => {
            this.search(query);
        }, this.options.debounceDelay);
    }
    
    handleFocus() {
        const query = this.input.value.trim();
        if (query.length >= this.options.minLength) {
            this.search(query);
        } else if (this.options.showHistory && this.history.length > 0) {
            this.showHistory();
        }
    }
    
    handleKeydown(e) {
        if (!this.dropdown.classList.contains('show')) return;
        
        const items = this.dropdown.querySelectorAll('.autocomplete-item');
        
        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                this.activeIndex = Math.min(this.activeIndex + 1, items.length - 1);
                this.updateActiveItem(items);
                break;
                
            case 'ArrowUp':
                e.preventDefault();
                this.activeIndex = Math.max(this.activeIndex - 1, -1);
                this.updateActiveItem(items);
                break;
                
            case 'Enter':
                e.preventDefault();
                if (this.activeIndex >= 0 && items[this.activeIndex]) {
                    items[this.activeIndex].click();
                } else {
                    this.select(this.input.value);
                }
                break;
                
            case 'Escape':
                e.preventDefault();
                this.hideDropdown();
                break;
        }
    }
    
    async search(query) {
        try {
            this.suggestions = await this.options.getSuggestions(query);
            this.showSuggestions(query);
        } catch (error) {
            console.error('Search error for query "' + query + '":', error);
            Toast.error('Failed to load search suggestions');
        }
    }
    
    showSuggestions(query) {
        if (!this.suggestions || this.suggestions.length === 0) {
            this.hideDropdown();
            return;
        }
        
        this.dropdown.innerHTML = '';
        this.activeIndex = -1;
        
        this.suggestions.forEach((suggestion, index) => {
            const item = this.createSuggestionItem(suggestion, index);
            this.dropdown.appendChild(item);
        });
        
        // Add keyboard hint
        const hint = document.createElement('div');
        hint.className = 'keyboard-hint';
        hint.innerHTML = `
            <span>Use</span>
            <kbd>↑</kbd>
            <kbd>↓</kbd>
            <span>to navigate,</span>
            <kbd>Enter</kbd>
            <span>to select</span>
        `;
        this.dropdown.appendChild(hint);
        
        this.showDropdown();
    }
    
    showHistory() {
        if (this.history.length === 0) return;
        
        this.dropdown.innerHTML = '';
        
        // History header
        const header = document.createElement('div');
        header.className = 'search-history';
        header.innerHTML = `
            <div class="search-history-header">
                <span class="search-history-title">Recent Searches</span>
                <button class="search-history-clear">Clear</button>
            </div>
        `;
        header.querySelector('.search-history-clear').addEventListener('click', () => {
            this.clearHistory();
        });
        this.dropdown.appendChild(header);
        
        // History items
        this.history.forEach((term, index) => {
            const item = this.createHistoryItem(term, index);
            this.dropdown.appendChild(item);
        });
        
        this.showDropdown();
    }
    
    createSuggestionItem(suggestion, index) {
        const item = document.createElement('div');
        item.className = 'autocomplete-item';
        item.dataset.index = index;
        
        item.innerHTML = `
            <svg class="autocomplete-icon" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <circle cx="11" cy="11" r="8"></circle>
                <path d="m21 21-4.35-4.35"></path>
            </svg>
            <div class="autocomplete-text">
                <div class="autocomplete-main">${escapeHtml(suggestion.text || suggestion)}</div>
                ${suggestion.subtitle ? `<div class="autocomplete-sub">${escapeHtml(suggestion.subtitle)}</div>` : ''}
            </div>
        `;
        
        item.addEventListener('click', () => {
            this.select(suggestion.text || suggestion);
        });
        
        return item;
    }
    
    createHistoryItem(term, index) {
        const item = document.createElement('div');
        item.className = 'autocomplete-item';
        item.dataset.index = index;
        
        item.innerHTML = `
            <svg class="autocomplete-icon" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="10"></circle>
                <polyline points="12 6 12 12 16 14"></polyline>
            </svg>
            <div class="autocomplete-text">
                <div class="autocomplete-main">${escapeHtml(term)}</div>
            </div>
        `;
        
        item.addEventListener('click', () => {
            this.select(term);
        });
        
        return item;
    }
    
    updateActiveItem(items) {
        items.forEach((item, index) => {
            item.classList.toggle('active', index === this.activeIndex);
            if (index === this.activeIndex) {
                item.scrollIntoView({ block: 'nearest' });
            }
        });
    }
    
    select(value) {
        this.input.value = value;
        this.addToHistory(value);
        this.hideDropdown();
        this.options.onSelect(value);
        this.options.onSearch(value);
    }
    
    clear() {
        this.input.value = '';
        this.clearBtn.style.display = 'none';
        this.hideDropdown();
        this.input.focus();
    }
    
    showDropdown() {
        this.dropdown.classList.add('show');
    }
    
    hideDropdown() {
        this.dropdown.classList.remove('show');
        this.activeIndex = -1;
    }
    
    addToHistory(term) {
        if (!this.options.showHistory) return;
        
        // Remove if already exists
        this.history = this.history.filter(t => t !== term);
        
        // Add to beginning
        this.history.unshift(term);
        
        // Limit size
        if (this.history.length > this.options.maxHistory) {
            this.history = this.history.slice(0, this.options.maxHistory);
        }
        
        this.saveHistory();
    }
    
    clearHistory() {
        this.history = [];
        this.saveHistory();
        this.hideDropdown();
        Toast.info('Search history cleared');
    }
    
    loadHistory() {
        try {
            const saved = localStorage.getItem('search_history');
            return saved ? JSON.parse(saved) : [];
        } catch (e) {
            return [];
        }
    }
    
    saveHistory() {
        try {
            localStorage.setItem('search_history', JSON.stringify(this.history));
        } catch (e) {
            console.error('Failed to save search history:', e);
        }
    }
}

// Export Phase 3 classes
window.DataTable = DataTable;
window.ModalManager = ModalManager;
window.SearchAutocomplete = SearchAutocomplete;
