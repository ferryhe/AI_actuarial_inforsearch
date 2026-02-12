# File Preview Interface

## Overview

The file preview interface provides a side-by-side view of original files and their markdown representations, similar to RAGFlow. This feature allows users to:

- Preview original files (PDF, images, documents)
- View markdown content alongside the original
- See chunks generated for RAG indexing
- Navigate between chunks with metadata

## Architecture

### Backend Components

1. **API Endpoint** (`/api/rag/files/preview`)
   - Returns file metadata, markdown content, and chunks
   - Supports optional KB filtering for chunks
   - Returns JSON with structured data

2. **Page Route** (`/file_preview`)
   - Renders the preview template
   - Accepts `file_url` and optional `kb_id` query parameters

3. **File Download** (`/api/download`)
   - Existing endpoint used to serve original files
   - Supports secure file path resolution

### Frontend Components

1. **Template** (`file_preview.html`)
   - Split-pane layout (50/50)
   - Left: Original file viewer
   - Right: Markdown content + chunks
   - Responsive design

2. **JavaScript** (`file_preview.js`)
   - PDF.js integration for PDF rendering
   - Marked.js for markdown rendering
   - Chunk display with metadata
   - Image preview support

3. **Integration Points**
   - RAG detail page: Preview button in file actions
   - Database page: Preview button in actions column

## Usage

### From RAG Detail Page

1. Navigate to a knowledge base detail page (`/rag/<kb_id>`)
2. Click the "Preview" button next to any file
3. Opens in new tab with file and chunks from that KB

### From Database Page

1. Navigate to database management (`/database`)
2. Click the "Preview" button in the actions column
3. Opens in new tab with file and markdown (no KB context)

### Direct URL

Access preview directly:
```
/file_preview?file_url=<encoded_url>&kb_id=<optional_kb_id>
```

## Features

### Supported File Types

- **PDF**: Rendered with PDF.js
  - Page navigation
  - Canvas rendering
  - Zoom support

- **Images**: Direct display
  - Inline rendering
  - Full width support

- **Other Files**: Download link
  - Fallback for unsupported types

### Markdown Display

- Rendered with Marked.js
- Supports GitHub Flavored Markdown
- Shows metadata:
  - Source (manual/converted/original)
  - Last updated timestamp

### Chunk Display

Shows chunks when KB is specified:
- Chunk index number
- Token count
- Section hierarchy (if available)
- Full chunk content
- Formatted for readability

## Implementation Details

### API Response Format

```json
{
  "success": true,
  "data": {
    "file_info": {
      "url": "...",
      "title": "...",
      "original_filename": "...",
      "local_path": "...",
      "content_type": "...",
      "bytes": 1024,
      "sha256": "...",
      "last_modified": "..."
    },
    "markdown": {
      "content": "# Document\n\nContent...",
      "source": "converted",
      "updated_at": "2024-01-01T00:00:00Z"
    },
    "chunks": [
      {
        "chunk_id": "...",
        "chunk_index": 0,
        "content": "...",
        "token_count": 150,
        "section_hierarchy": "Introduction > Overview",
        "created_at": "2024-01-01T00:00:00Z"
      }
    ]
  }
}
```

### Database Schema

Chunks are stored in `rag_chunks` table:
```sql
CREATE TABLE rag_chunks (
    chunk_id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL,
    file_url TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    section_hierarchy TEXT,
    embedding_hash TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (kb_id) REFERENCES rag_knowledge_bases(kb_id) ON DELETE CASCADE,
    FOREIGN KEY (file_url) REFERENCES files(url) ON DELETE CASCADE
)
```

### Permissions

- Preview page: `files.read`
- Preview API: `files.read`
- File download: `files.download`

Public access when `REQUIRE_AUTH=false`:
- Preview is accessible (uses `files.read` which is in public allowlist)
- Download requires token

## Security Considerations

1. **Path Validation**: File paths are validated to prevent directory traversal
2. **Permission Checks**: All endpoints require appropriate permissions
3. **URL Encoding**: All URLs are properly encoded to prevent XSS
4. **Content Sanitization**: Markdown is sanitized before rendering

## Testing

Unit tests in `tests/test_file_preview.py`:
- Route accessibility
- API endpoint functionality
- Error handling
- Permission enforcement

To run tests:
```bash
python -m unittest tests.test_file_preview -v
```

## Future Enhancements

1. **Scroll Synchronization**: Sync scroll between original and markdown
2. **Chunk Highlighting**: Highlight chunks in markdown content
3. **PDF Annotation**: Allow highlighting text in PDF
4. **Search in Preview**: Search within document
5. **Compare Versions**: Side-by-side comparison of document versions
6. **Export Annotations**: Save highlights and notes

## Reference

This implementation is inspired by RAGFlow's document preview interface:
- GitHub: https://github.com/infiniflow/ragflow
- Features: Side-by-side document viewing, chunk visualization
