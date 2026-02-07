# Phase 3: Component Upgrades - Quick Start Guide

**Status:** ✅ Complete and Production Ready  
**Date:** 2026-02-07

## What's New in Phase 3?

Phase 3 introduces three powerful components that significantly enhance the user interface:

1. **DataTable** - Advanced sortable tables with export
2. **ModalManager** - Enhanced modal system
3. **SearchAutocomplete** - Smart search with history

---

## Quick Start

### 1. DataTable - Sortable Tables with Export

Create interactive tables with sorting, selection, and CSV export:

```javascript
// Basic usage
new DataTable('#my-container', {
    data: [
        { name: 'File1.pdf', size: 1024, date: '2024-01-01' },
        { name: 'File2.pdf', size: 2048, date: '2024-01-02' }
    ],
    columns: [
        { key: 'name', label: 'Filename', sortable: true },
        { key: 'size', label: 'Size', sortable: true, render: formatBytes },
        { key: 'date', label: 'Date', sortable: true }
    ],
    sortable: true,
    selectable: true,
    exportable: true,
    exportFilename: 'my_files'
});
```

**Features:**
- ✅ Click column headers to sort
- ✅ Select rows with checkboxes
- ✅ Export to CSV (selected or all)
- ✅ Sticky headers for scrolling
- ✅ Dark mode support

### 2. ModalManager - Enhanced Modals

Open modals with custom sizes and better UX:

```javascript
// Open modal with size
ModalManager.open('edit-modal', { size: 'lg' });

// Close modal
ModalManager.close('edit-modal');
```

**HTML Structure:**
```html
<div id="edit-modal" class="modal">
    <div class="modal-content">
        <div class="modal-header">
            <h3>Edit Item</h3>
            <span class="close" onclick="ModalManager.close('edit-modal')">&times;</span>
        </div>
        <div class="modal-body">
            <!-- Your content here -->
        </div>
        <div class="modal-footer">
            <button class="btn btn-secondary">Cancel</button>
            <button class="btn btn-primary">Save</button>
        </div>
    </div>
</div>
```

**Size Options:**
- `sm` - Small (400px)
- `md` - Medium (600px)
- `lg` - Large (900px)
- `xl` - Extra Large (1200px)
- `fullscreen` - Full Screen (95vw x 95vh)

**Features:**
- ✅ Backdrop blur effect
- ✅ Focus trap (keyboard accessible)
- ✅ ESC key to close
- ✅ Smooth animations

### 3. SearchAutocomplete - Smart Search

Add autocomplete to any search input:

```javascript
new SearchAutocomplete('#search-input', {
    onSearch: (query) => {
        // Perform search
        performSearch(query);
    },
    onSelect: (value) => {
        // Handle selection
        console.log('Selected:', value);
    },
    getSuggestions: async (query) => {
        // Fetch suggestions
        const response = await fetch(`/api/suggestions?q=${query}`);
        const data = await response.json();
        return data.suggestions;
    },
    minLength: 2,           // Start suggesting after 2 characters
    debounceDelay: 300,     // Wait 300ms after typing
    showHistory: true,      // Show recent searches
    maxHistory: 5           // Keep 5 recent searches
});
```

**Features:**
- ✅ Autocomplete dropdown
- ✅ Recent search history (localStorage)
- ✅ Keyboard navigation (↑↓ Enter ESC)
- ✅ Clear button
- ✅ Debounced search

**Keyboard Shortcuts:**
- `↑` / `↓` - Navigate suggestions
- `Enter` - Select highlighted item
- `ESC` - Close dropdown

---

## Integration Example

See how Phase 3 components are used in the database page:

```javascript
// In database.html
function displayResults(data) {
    // Create advanced table
    new DataTable(container, {
        data: data.files,
        columns: [
            {
                key: 'title',
                label: 'Title',
                sortable: true,
                render: (value, row) => {
                    return `<div>${escapeHtml(value)}</div>`;
                }
            },
            // ... more columns
        ],
        exportFilename: 'database_files',
        onRowClick: (row) => viewFile(row.url)
    });
}

// Initialize search autocomplete
new SearchAutocomplete('#search-query', {
    onSearch: searchFiles,
    getSuggestions: async (query) => {
        // Return suggestions
        return commonTerms.filter(term => 
            term.toLowerCase().includes(query.toLowerCase())
        );
    }
});
```

---

## Styling

All components are fully styled and support dark mode. No additional CSS required!

### Dark Mode
Components automatically adapt to the current theme:

```javascript
// Components respect [data-theme="dark"]
document.documentElement.setAttribute('data-theme', 'dark');
```

### Custom Styling
You can override styles using CSS:

```css
/* Custom table styling */
.data-table th {
    background-color: var(--my-color);
}

/* Custom modal styling */
.modal-content.my-modal {
    border-radius: 16px;
}
```

---

## Advanced Usage

### DataTable: Custom Rendering

```javascript
new DataTable('#table', {
    columns: [
        {
            key: 'status',
            label: 'Status',
            render: (value) => {
                const color = value === 'active' ? 'green' : 'gray';
                return `<span style="color: ${color}">${value}</span>`;
            }
        }
    ]
});
```

### SearchAutocomplete: Rich Suggestions

```javascript
new SearchAutocomplete('#search', {
    getSuggestions: async (query) => {
        return [
            {
                text: 'Main suggestion',
                subtitle: 'Optional description'
            },
            'Simple text suggestion'
        ];
    }
});
```

### ModalManager: Programmatic Control

```javascript
// Open with options
ModalManager.open('modal-id', { 
    size: 'xl',
    onOpen: () => console.log('Modal opened'),
    onClose: () => console.log('Modal closed')
});

// Close programmatically
ModalManager.close('modal-id');
```

---

## Documentation

### Full Documentation
- **PHASE3_IMPLEMENTATION.md** - Complete technical guide
- **PHASE3_COMPLETE_SUMMARY.md** - Executive summary
- **SECURITY_SUMMARY_PHASE3.md** - Security analysis

### API Reference

#### DataTable Options
```javascript
{
    data: Array,              // Array of objects
    columns: Array,           // Column definitions
    sortable: Boolean,        // Enable sorting (default: true)
    selectable: Boolean,      // Enable row selection (default: false)
    exportable: Boolean,      // Enable CSV export (default: true)
    exportFilename: String,   // Export filename (default: 'data_export')
    onRowClick: Function,     // Row click handler
    onSelectionChange: Function // Selection change handler
}
```

#### ModalManager Methods
```javascript
ModalManager.open(modalId, options)   // Open modal
ModalManager.close(modalId)           // Close modal
```

#### SearchAutocomplete Options
```javascript
{
    onSearch: Function,       // Called when search is performed
    onSelect: Function,       // Called when suggestion is selected
    getSuggestions: Function, // Async function returning suggestions
    minLength: Number,        // Min chars before suggestions (default: 2)
    debounceDelay: Number,    // Debounce delay in ms (default: 300)
    showHistory: Boolean,     // Show search history (default: true)
    maxHistory: Number        // Max history items (default: 5)
}
```

---

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

---

## Security

All components follow security best practices:
- ✅ XSS Prevention (HTML escaping)
- ✅ CSV Injection Prevention
- ✅ Safe DOM manipulation
- ✅ No eval() usage
- ✅ 0 CodeQL vulnerabilities

---

## Performance

Components are optimized for performance:
- Efficient DOM updates
- Debounced search
- LocalStorage caching
- GPU-accelerated animations

---

## Troubleshooting

### DataTable not showing
```javascript
// Make sure container exists
const container = document.getElementById('my-container');
if (!container) console.error('Container not found');
```

### Search autocomplete not working
```javascript
// Check if SearchAutocomplete is defined
if (typeof SearchAutocomplete === 'undefined') {
    console.error('SearchAutocomplete not loaded');
}
```

### Modal not opening
```javascript
// Check if ModalManager exists and modal ID is correct
ModalManager.open('correct-modal-id', { size: 'lg' });
```

---

## Examples

### Complete Example: File Manager

```javascript
// Initialize table
const table = new DataTable('#files', {
    data: files,
    columns: [
        { key: 'name', label: 'Name', sortable: true },
        { key: 'size', label: 'Size', sortable: true, render: formatBytes },
        { key: 'modified', label: 'Modified', sortable: true, render: formatDate }
    ],
    selectable: true,
    exportable: true,
    exportFilename: 'my_files',
    onRowClick: (file) => {
        ModalManager.open('file-details', { size: 'lg' });
        showFileDetails(file);
    },
    onSelectionChange: (selectedFiles) => {
        updateToolbar(selectedFiles.length);
    }
});

// Initialize search
new SearchAutocomplete('#file-search', {
    onSearch: (query) => {
        const filtered = files.filter(f => 
            f.name.toLowerCase().includes(query.toLowerCase())
        );
        table.options.data = filtered;
        table.render();
    },
    getSuggestions: async (query) => {
        return files
            .filter(f => f.name.includes(query))
            .map(f => ({ text: f.name, subtitle: formatBytes(f.size) }))
            .slice(0, 5);
    }
});
```

---

## Support

For issues or questions:
1. Check the documentation
2. Review code examples
3. Check browser console for errors
4. Review security best practices

---

## What's Next?

Phase 3 is complete! Optional future enhancements could include:
- Advanced table filtering
- Column resizing
- Inline editing
- Draggable modals
- Voice search

---

**Happy coding! 🚀**

*Phase 3 - AI Actuarial Info Search*  
*2026-02-07*
