# UI Improvements - Code Examples
**具体代码实现示例**

## 1. Color System & Dark Mode - 色彩系统与暗色模式

### Current Implementation (当前实现)
```css
:root {
    --primary-color: #2563eb;
    --primary-hover: #1d4ed8;
    --secondary-color: #64748b;
    --success-color: #10b981;
}
```

### Improved Implementation (改进实现)
```css
:root {
    /* Primary Palette - 主色调色板 */
    --primary-50: #eff6ff;
    --primary-100: #dbeafe;
    --primary-200: #bfdbfe;
    --primary-300: #93c5fd;
    --primary-400: #60a5fa;
    --primary-500: #3b82f6;
    --primary-600: #2563eb;
    --primary-700: #1d4ed8;
    --primary-800: #1e40af;
    --primary-900: #1e3a8a;
    
    /* Semantic Colors with shades */
    --success-500: #10b981;
    --success-600: #059669;
    --warning-500: #f59e0b;
    --error-500: #ef4444;
    
    /* Neutral Grays */
    --gray-50: #f9fafb;
    --gray-100: #f3f4f6;
    --gray-200: #e5e7eb;
    --gray-300: #d1d5db;
    --gray-400: #9ca3af;
    --gray-500: #6b7280;
    --gray-600: #4b5563;
    --gray-700: #374151;
    --gray-800: #1f2937;
    --gray-900: #111827;
    
    /* Theme Variables */
    --background: var(--gray-50);
    --card-bg: #ffffff;
    --text-primary: var(--gray-900);
    --text-secondary: var(--gray-600);
    --border-color: var(--gray-200);
}

/* Dark Mode */
[data-theme="dark"] {
    --background: var(--gray-900);
    --card-bg: var(--gray-800);
    --text-primary: var(--gray-50);
    --text-secondary: var(--gray-400);
    --border-color: var(--gray-700);
}
```

### Dark Mode Toggle Component
```html
<!-- Add to navbar -->
<div class="theme-toggle">
    <button id="theme-toggle-btn" class="btn-icon" aria-label="Toggle dark mode">
        <svg class="sun-icon" width="20" height="20">
            <use xlink:href="#icon-sun"></use>
        </svg>
        <svg class="moon-icon" width="20" height="20" style="display: none;">
            <use xlink:href="#icon-moon"></use>
        </svg>
    </button>
</div>
```

```javascript
// Theme toggle functionality
const themeToggle = document.getElementById('theme-toggle-btn');
const sunIcon = document.querySelector('.sun-icon');
const moonIcon = document.querySelector('.moon-icon');

// Load saved theme
const savedTheme = localStorage.getItem('theme') || 'light';
document.documentElement.setAttribute('data-theme', savedTheme);
updateThemeIcon(savedTheme);

themeToggle.addEventListener('click', () => {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcon(newTheme);
});

function updateThemeIcon(theme) {
    if (theme === 'dark') {
        sunIcon.style.display = 'none';
        moonIcon.style.display = 'block';
    } else {
        sunIcon.style.display = 'block';
        moonIcon.style.display = 'none';
    }
}
```

---

## 2. Professional Icons - 专业图标系统

### Current (Emoji) - 当前（表情符号）
```html
<div class="stat-icon">📄</div>
<div class="stat-icon">📊</div>
<div class="stat-icon">🏢</div>
<div class="stat-icon">🔄</div>
```

### Improved (SVG Icons) - 改进（SVG图标）

**Add icon sprite to base.html:**
```html
<svg style="display: none;">
    <symbol id="icon-document" viewBox="0 0 24 24">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
        <polyline points="14 2 14 8 20 8"></polyline>
    </symbol>
    
    <symbol id="icon-chart" viewBox="0 0 24 24">
        <path d="M3 3v18h18"></path>
        <path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"></path>
    </symbol>
    
    <symbol id="icon-building" viewBox="0 0 24 24">
        <rect x="4" y="2" width="16" height="20" rx="2" ry="2"></rect>
        <path d="M9 22v-4h6v4"></path>
        <path d="M8 6h.01"></path>
        <path d="M16 6h.01"></path>
        <path d="M12 6h.01"></path>
    </symbol>
    
    <symbol id="icon-refresh" viewBox="0 0 24 24">
        <polyline points="23 4 23 10 17 10"></polyline>
        <polyline points="1 20 1 14 7 14"></polyline>
        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
    </symbol>
</svg>
```

**Update stat cards:**
```html
<div class="stat-card">
    <div class="stat-icon">
        <svg class="icon-lg" fill="none" stroke="currentColor" stroke-width="2">
            <use xlink:href="#icon-document"></use>
        </svg>
    </div>
    <div class="stat-content">
        <h3 id="total-files">-</h3>
        <p>Total Files</p>
    </div>
</div>
```

**Icon CSS:**
```css
.icon-lg {
    width: 48px;
    height: 48px;
    color: var(--primary-500);
}

.icon-md {
    width: 24px;
    height: 24px;
}

.icon-sm {
    width: 16px;
    height: 16px;
}

.stat-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 64px;
    height: 64px;
    background: linear-gradient(135deg, var(--primary-100), var(--primary-50));
    border-radius: 12px;
}
```

---

## 3. Loading Skeletons - 加载骨架屏

### Current (Plain text) - 当前（纯文本）
```html
<p class="loading">Loading...</p>
```

### Improved (Skeleton) - 改进（骨架屏）

**HTML Structure:**
```html
<div class="skeleton-loader">
    <div class="skeleton-table">
        <div class="skeleton-row">
            <div class="skeleton-cell skeleton-cell-lg"></div>
            <div class="skeleton-cell skeleton-cell-md"></div>
            <div class="skeleton-cell skeleton-cell-sm"></div>
            <div class="skeleton-cell skeleton-cell-xs"></div>
        </div>
        <div class="skeleton-row">
            <div class="skeleton-cell skeleton-cell-lg"></div>
            <div class="skeleton-cell skeleton-cell-md"></div>
            <div class="skeleton-cell skeleton-cell-sm"></div>
            <div class="skeleton-cell skeleton-cell-xs"></div>
        </div>
        <div class="skeleton-row">
            <div class="skeleton-cell skeleton-cell-lg"></div>
            <div class="skeleton-cell skeleton-cell-md"></div>
            <div class="skeleton-cell skeleton-cell-sm"></div>
            <div class="skeleton-cell skeleton-cell-xs"></div>
        </div>
    </div>
</div>
```

**CSS:**
```css
.skeleton-loader {
    width: 100%;
    animation: fadeIn 0.3s ease-in;
}

.skeleton-row {
    display: grid;
    grid-template-columns: 2fr 1fr 1fr 0.5fr;
    gap: 1rem;
    padding: 1rem;
    border-bottom: 1px solid var(--border-color);
}

.skeleton-cell {
    height: 20px;
    background: linear-gradient(
        90deg,
        var(--gray-200) 25%,
        var(--gray-100) 50%,
        var(--gray-200) 75%
    );
    background-size: 200% 100%;
    border-radius: 4px;
    animation: shimmer 1.5s infinite;
}

.skeleton-cell-lg { height: 24px; }
.skeleton-cell-md { height: 20px; }
.skeleton-cell-sm { height: 16px; }
.skeleton-cell-xs { height: 12px; }

@keyframes shimmer {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
}

@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}
```

**Usage in JavaScript:**
```javascript
function showSkeletonLoader(container) {
    container.innerHTML = `
        <div class="skeleton-loader">
            <!-- skeleton rows -->
        </div>
    `;
}

function hideSkeletonLoader(container, data) {
    container.innerHTML = renderData(data);
}

// Example
fetch('/api/files')
    .then(response => response.json())
    .then(data => {
        hideSkeletonLoader(container, data);
    });
```

---

## 4. Toast Notifications - 提示通知系统

### Current (Alert) - 当前（弹窗）
```javascript
alert('Collection completed!');
alert('Error: ' + error.message);
```

### Improved (Toast) - 改进（提示通知）

**HTML Structure:**
```html
<div id="toast-container" class="toast-container"></div>
```

**CSS:**
```css
.toast-container {
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 9999;
    display: flex;
    flex-direction: column;
    gap: 10px;
    max-width: 400px;
}

.toast {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 16px;
    background: white;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    transform: translateX(400px);
    opacity: 0;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.toast.show {
    transform: translateX(0);
    opacity: 1;
}

.toast.hide {
    transform: translateX(400px);
    opacity: 0;
}

.toast-success {
    border-left: 4px solid var(--success-500);
}

.toast-error {
    border-left: 4px solid var(--error-500);
}

.toast-warning {
    border-left: 4px solid var(--warning-500);
}

.toast-info {
    border-left: 4px solid var(--primary-500);
}

.toast-icon {
    flex-shrink: 0;
    width: 24px;
    height: 24px;
}

.toast-content {
    flex: 1;
}

.toast-title {
    font-weight: 600;
    margin-bottom: 4px;
    color: var(--text-primary);
}

.toast-message {
    font-size: 0.875rem;
    color: var(--text-secondary);
}

.toast-close {
    flex-shrink: 0;
    background: none;
    border: none;
    font-size: 20px;
    color: var(--gray-400);
    cursor: pointer;
    padding: 0;
    width: 20px;
    height: 20px;
    line-height: 1;
}

.toast-close:hover {
    color: var(--gray-600);
}
```

**JavaScript:**
```javascript
class Toast {
    static container = null;
    
    static init() {
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.id = 'toast-container';
            this.container.className = 'toast-container';
            document.body.appendChild(this.container);
        }
    }
    
    static show(message, type = 'info', duration = 5000) {
        this.init();
        
        const icons = {
            success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>',
            error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>',
            warning: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>',
            info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>'
        };
        
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <div class="toast-icon">${icons[type]}</div>
            <div class="toast-content">
                <div class="toast-message">${message}</div>
            </div>
            <button class="toast-close" aria-label="Close">&times;</button>
        `;
        
        const closeBtn = toast.querySelector('.toast-close');
        closeBtn.addEventListener('click', () => this.hide(toast));
        
        this.container.appendChild(toast);
        
        // Trigger animation
        setTimeout(() => toast.classList.add('show'), 10);
        
        // Auto dismiss
        if (duration > 0) {
            setTimeout(() => this.hide(toast), duration);
        }
        
        return toast;
    }
    
    static hide(toast) {
        toast.classList.remove('show');
        toast.classList.add('hide');
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

// Usage Examples:
Toast.success('Collection completed successfully!');
Toast.error('Failed to load data. Please try again.');
Toast.warning('Some files could not be downloaded.');
Toast.info('Task started. Check the Tasks page for progress.');
```

---

## 5. Enhanced Buttons - 增强按钮

### Current - 当前
```css
.btn-primary {
    background-color: var(--primary-color);
    color: white;
    padding: 0.5rem 1rem;
    border-radius: 6px;
}
```

### Improved - 改进

**CSS:**
```css
/* Base Button */
.btn {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 10px 20px;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    line-height: 1.5;
    cursor: pointer;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    outline: none;
    user-select: none;
}

/* Primary Button */
.btn-primary {
    background: linear-gradient(135deg, var(--primary-600), var(--primary-500));
    color: white;
    box-shadow: 0 2px 4px rgba(37, 99, 235, 0.2);
}

.btn-primary:hover {
    background: linear-gradient(135deg, var(--primary-700), var(--primary-600));
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
    transform: translateY(-1px);
}

.btn-primary:active {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(37, 99, 235, 0.2);
}

.btn-primary:focus-visible {
    outline: 2px solid var(--primary-500);
    outline-offset: 2px;
}

/* Secondary Button */
.btn-secondary {
    background: var(--gray-100);
    color: var(--gray-700);
    border: 1px solid var(--gray-300);
}

.btn-secondary:hover {
    background: var(--gray-200);
    border-color: var(--gray-400);
    transform: translateY(-1px);
}

/* Icon Button */
.btn-icon {
    padding: 8px;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: transparent;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.2s;
}

.btn-icon:hover {
    background: var(--gray-100);
    color: var(--text-primary);
}

/* Loading State */
.btn.loading {
    pointer-events: none;
    opacity: 0.7;
}

.btn.loading::after {
    content: '';
    position: absolute;
    width: 16px;
    height: 16px;
    border: 2px solid transparent;
    border-top-color: currentColor;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

/* Size Variants */
.btn-sm {
    padding: 6px 12px;
    font-size: 12px;
}

.btn-lg {
    padding: 14px 28px;
    font-size: 16px;
}

/* Disabled State */
.btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    pointer-events: none;
}
```

**Usage:**
```html
<!-- Primary Button -->
<button class="btn btn-primary">
    <svg class="icon-sm"><use xlink:href="#icon-plus"></use></svg>
    Add New
</button>

<!-- Secondary Button -->
<button class="btn btn-secondary">Cancel</button>

<!-- Loading Button -->
<button class="btn btn-primary loading">Processing...</button>

<!-- Icon Button -->
<button class="btn-icon" aria-label="Settings">
    <svg class="icon-md"><use xlink:href="#icon-settings"></use></svg>
</button>

<!-- Small Button -->
<button class="btn btn-primary btn-sm">Save</button>
```

---

## 6. Advanced Table Features - 高级表格功能

### Current - 当前
```html
<table>
    <thead>
        <tr>
            <th>Title</th>
            <th>Source</th>
            <th>Date</th>
        </tr>
    </thead>
    <tbody>
        <!-- rows -->
    </tbody>
</table>
```

### Improved - 改进

**HTML:**
```html
<div class="table-container">
    <div class="table-toolbar">
        <div class="table-actions">
            <button class="btn btn-secondary btn-sm" onclick="exportTable()">
                <svg class="icon-sm"><use xlink:href="#icon-download"></use></svg>
                Export CSV
            </button>
        </div>
        <div class="table-search">
            <input type="text" placeholder="Search in table..." id="table-search">
        </div>
    </div>
    
    <table class="data-table">
        <thead>
            <tr>
                <th>
                    <input type="checkbox" id="select-all" aria-label="Select all">
                </th>
                <th class="sortable" data-sort="title">
                    Title
                    <span class="sort-icon">
                        <svg class="icon-sm"><use xlink:href="#icon-chevron-up-down"></use></svg>
                    </span>
                </th>
                <th class="sortable" data-sort="source">
                    Source
                    <span class="sort-icon">
                        <svg class="icon-sm"><use xlink:href="#icon-chevron-up-down"></use></svg>
                    </span>
                </th>
                <th class="sortable" data-sort="date">
                    Date
                    <span class="sort-icon">
                        <svg class="icon-sm"><use xlink:href="#icon-chevron-up-down"></use></svg>
                    </span>
                </th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            <!-- rows with checkboxes -->
        </tbody>
    </table>
    
    <div class="table-footer">
        <div class="selected-count">0 selected</div>
        <div class="pagination">
            <!-- pagination controls -->
        </div>
    </div>
</div>
```

**CSS:**
```css
.table-container {
    background: var(--card-bg);
    border-radius: 8px;
    box-shadow: var(--shadow);
    overflow: hidden;
}

.table-toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px;
    border-bottom: 1px solid var(--border-color);
}

.table-search input {
    padding: 8px 12px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    width: 250px;
}

.data-table {
    width: 100%;
    border-collapse: collapse;
}

.data-table thead {
    background: var(--gray-50);
    position: sticky;
    top: 0;
    z-index: 10;
}

.data-table th {
    padding: 12px 16px;
    text-align: left;
    font-weight: 600;
    color: var(--text-primary);
    border-bottom: 1px solid var(--border-color);
}

.data-table th.sortable {
    cursor: pointer;
    user-select: none;
}

.data-table th.sortable:hover {
    background: var(--gray-100);
}

.data-table th.sortable.sorted-asc .sort-icon {
    transform: rotate(180deg);
}

.data-table th.sortable.sorted-desc .sort-icon {
    transform: rotate(0deg);
}

.sort-icon {
    display: inline-block;
    margin-left: 4px;
    transition: transform 0.2s;
}

.data-table tbody tr {
    border-bottom: 1px solid var(--border-color);
    transition: background 0.15s;
}

.data-table tbody tr:hover {
    background: var(--gray-50);
}

.data-table tbody tr.selected {
    background: var(--primary-50);
}

.data-table td {
    padding: 12px 16px;
}

.table-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px;
    border-top: 1px solid var(--border-color);
}

.selected-count {
    font-size: 14px;
    color: var(--text-secondary);
}
```

**JavaScript:**
```javascript
class DataTable {
    constructor(tableElement) {
        this.table = tableElement;
        this.selectedRows = new Set();
        this.sortColumn = null;
        this.sortDirection = 'asc';
        
        this.init();
    }
    
    init() {
        // Select all checkbox
        const selectAll = this.table.querySelector('#select-all');
        selectAll?.addEventListener('change', (e) => {
            this.toggleSelectAll(e.target.checked);
        });
        
        // Row checkboxes
        this.table.querySelectorAll('tbody input[type="checkbox"]').forEach(cb => {
            cb.addEventListener('change', (e) => {
                this.toggleRow(e.target.closest('tr'), e.target.checked);
            });
        });
        
        // Sortable columns
        this.table.querySelectorAll('th.sortable').forEach(th => {
            th.addEventListener('click', () => {
                this.sortBy(th.dataset.sort);
            });
        });
    }
    
    toggleSelectAll(checked) {
        this.table.querySelectorAll('tbody input[type="checkbox"]').forEach(cb => {
            cb.checked = checked;
            this.toggleRow(cb.closest('tr'), checked);
        });
    }
    
    toggleRow(row, selected) {
        if (selected) {
            this.selectedRows.add(row);
            row.classList.add('selected');
        } else {
            this.selectedRows.delete(row);
            row.classList.remove('selected');
        }
        this.updateSelectedCount();
    }
    
    updateSelectedCount() {
        const count = this.selectedRows.size;
        const countElement = document.querySelector('.selected-count');
        if (countElement) {
            countElement.textContent = `${count} selected`;
        }
    }
    
    sortBy(column) {
        const th = this.table.querySelector(`th[data-sort="${column}"]`);
        
        // Toggle direction if same column
        if (this.sortColumn === column) {
            this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            this.sortColumn = column;
            this.sortDirection = 'asc';
        }
        
        // Update UI
        this.table.querySelectorAll('th.sortable').forEach(h => {
            h.classList.remove('sorted-asc', 'sorted-desc');
        });
        th.classList.add(`sorted-${this.sortDirection}`);
        
        // Perform sort (you would typically refetch from API with sort params)
        this.performSort(column, this.sortDirection);
    }
    
    performSort(column, direction) {
        // Trigger data refetch with sort parameters
        searchFiles(1); // Your existing function
    }
    
    exportToCSV() {
        const rows = Array.from(this.table.querySelectorAll('tbody tr'));
        const headers = Array.from(this.table.querySelectorAll('thead th'))
            .map(th => th.textContent.trim())
            .filter(h => h && h !== ''); // Remove checkbox column
        
        let csv = headers.join(',') + '\n';
        
        rows.forEach(row => {
            const cells = Array.from(row.querySelectorAll('td'))
                .slice(1) // Skip checkbox
                .map(td => `"${td.textContent.trim()}"`);
            csv += cells.join(',') + '\n';
        });
        
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'export.csv';
        a.click();
    }
}

// Initialize
const dataTable = new DataTable(document.querySelector('.data-table'));
```

---

## 7. Modal Improvements - 模态框改进

### Enhanced Modal CSS
```css
.modal {
    display: none;
    position: fixed;
    inset: 0;
    z-index: 1000;
    background: rgba(0, 0, 0, 0.5);
    backdrop-filter: blur(4px);
    animation: fadeIn 0.3s ease-out;
}

.modal.show {
    display: flex;
    align-items: center;
    justify-content: center;
}

.modal-content {
    background: var(--card-bg);
    border-radius: 12px;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1),
                0 10px 10px -5px rgba(0, 0, 0, 0.04);
    max-width: 500px;
    width: 90%;
    max-height: 90vh;
    overflow-y: auto;
    animation: modalSlideIn 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}

@keyframes modalSlideIn {
    from {
        opacity: 0;
        transform: translateY(-20px) scale(0.95);
    }
    to {
        opacity: 1;
        transform: translateY(0) scale(1);
    }
}

.modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 20px 24px;
    border-bottom: 1px solid var(--border-color);
}

.modal-header h3 {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
}

.modal-body {
    padding: 24px;
}

.modal-footer {
    display: flex;
    gap: 12px;
    justify-content: flex-end;
    padding: 20px 24px;
    border-top: 1px solid var(--border-color);
}

.modal-close {
    background: none;
    border: none;
    color: var(--text-secondary);
    font-size: 24px;
    cursor: pointer;
    padding: 0;
    width: 32px;
    height: 32px;
    border-radius: 4px;
    transition: all 0.2s;
}

.modal-close:hover {
    background: var(--gray-100);
    color: var(--text-primary);
}
```

**JavaScript:**
```javascript
class Modal {
    constructor(id) {
        this.modal = document.getElementById(id);
        this.init();
    }
    
    init() {
        // Close on backdrop click
        this.modal.addEventListener('click', (e) => {
            if (e.target === this.modal) {
                this.hide();
            }
        });
        
        // Close on ESC key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isVisible()) {
                this.hide();
            }
        });
        
        // Close button
        const closeBtn = this.modal.querySelector('.modal-close');
        closeBtn?.addEventListener('click', () => this.hide());
    }
    
    show() {
        this.modal.classList.add('show');
        document.body.style.overflow = 'hidden';
        
        // Focus first input
        const firstInput = this.modal.querySelector('input, textarea, select');
        firstInput?.focus();
    }
    
    hide() {
        this.modal.classList.remove('show');
        document.body.style.overflow = '';
    }
    
    isVisible() {
        return this.modal.classList.contains('show');
    }
}

// Usage
const siteModal = new Modal('site-modal');
```

---

## 8. Form Enhancements - 表单增强

**Improved Input with Validation:**
```html
<div class="form-group">
    <label for="site-url">
        Site URL
        <span class="required">*</span>
    </label>
    <input 
        type="url" 
        id="site-url" 
        class="form-input"
        placeholder="https://example.com"
        required
        aria-describedby="site-url-help site-url-error"
    >
    <p id="site-url-help" class="form-help">
        Enter the full URL including https://
    </p>
    <p id="site-url-error" class="form-error" style="display: none;">
        Please enter a valid URL
    </p>
</div>
```

**CSS:**
```css
.form-group {
    margin-bottom: 20px;
}

.form-group label {
    display: block;
    margin-bottom: 8px;
    font-weight: 500;
    color: var(--text-primary);
}

.required {
    color: var(--error-500);
}

.form-input,
.form-textarea,
.form-select {
    width: 100%;
    padding: 10px 12px;
    border: 2px solid var(--border-color);
    border-radius: 6px;
    font-size: 14px;
    transition: all 0.2s;
    background: var(--card-bg);
    color: var(--text-primary);
}

.form-input:focus,
.form-textarea:focus,
.form-select:focus {
    outline: none;
    border-color: var(--primary-500);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.form-input.error {
    border-color: var(--error-500);
}

.form-input.error:focus {
    box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1);
}

.form-help {
    margin-top: 4px;
    font-size: 12px;
    color: var(--text-secondary);
}

.form-error {
    margin-top: 4px;
    font-size: 12px;
    color: var(--error-500);
}

.form-input:focus + .form-help {
    color: var(--primary-500);
}
```

**JavaScript Validation:**
```javascript
class FormValidator {
    constructor(formElement) {
        this.form = formElement;
        this.init();
    }
    
    init() {
        // Real-time validation
        this.form.querySelectorAll('input, textarea, select').forEach(input => {
            input.addEventListener('blur', () => this.validateField(input));
            input.addEventListener('input', () => {
                if (input.classList.contains('error')) {
                    this.validateField(input);
                }
            });
        });
        
        // Form submission
        this.form.addEventListener('submit', (e) => {
            if (!this.validateAll()) {
                e.preventDefault();
            }
        });
    }
    
    validateField(input) {
        const errorElement = document.getElementById(`${input.id}-error`);
        let isValid = true;
        let errorMessage = '';
        
        // Required validation
        if (input.hasAttribute('required') && !input.value.trim()) {
            isValid = false;
            errorMessage = 'This field is required';
        }
        
        // URL validation
        if (input.type === 'url' && input.value) {
            try {
                new URL(input.value);
            } catch {
                isValid = false;
                errorMessage = 'Please enter a valid URL';
            }
        }
        
        // Email validation
        if (input.type === 'email' && input.value) {
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (!emailRegex.test(input.value)) {
                isValid = false;
                errorMessage = 'Please enter a valid email';
            }
        }
        
        // Update UI
        if (isValid) {
            input.classList.remove('error');
            if (errorElement) {
                errorElement.style.display = 'none';
            }
        } else {
            input.classList.add('error');
            if (errorElement) {
                errorElement.textContent = errorMessage;
                errorElement.style.display = 'block';
            }
        }
        
        return isValid;
    }
    
    validateAll() {
        let isValid = true;
        this.form.querySelectorAll('input, textarea, select').forEach(input => {
            if (!this.validateField(input)) {
                isValid = false;
            }
        });
        return isValid;
    }
}

// Usage
const validator = new FormValidator(document.getElementById('site-form'));
```

---

This document provides specific, implementable code examples for the major UI improvements. Each section can be implemented independently without affecting backend functionality.
