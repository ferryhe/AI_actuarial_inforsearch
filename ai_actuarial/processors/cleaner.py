"""Document cleaner for filtering and validating collected files."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class DocumentCleaner:
    """Cleans and validates collected documents."""
    
    def __init__(self, ai_filter_keywords: list[str] | None = None):
        """Initialize document cleaner.
        
        Args:
            ai_filter_keywords: Keywords to identify AI-related content
        """
        self.ai_filter_keywords = ai_filter_keywords or []
    
    def is_ai_related(self, text: str, title: str = "", filename: str = "") -> bool:
        """Check if document is AI-related.
        
        Args:
            text: Document text content
            title: Document title
            filename: Document filename
            
        Returns:
            True if document appears to be AI-related
        """
        if not self.ai_filter_keywords:
            return True
        
        # Combine all searchable text
        searchable = f"{title} {filename} {text}".lower()
        
        # Check if any AI keyword is present
        for keyword in self.ai_filter_keywords:
            if keyword.lower() in searchable:
                return True
        
        return False
    
    def should_keep(
        self,
        file_path: str,
        title: str = "",
        source_site: str = "",
        ai_only: bool = False,
    ) -> tuple[bool, str]:
        """Determine if a file should be kept.
        
        Args:
            file_path: Path to the file
            title: Document title
            source_site: Source site name
            ai_only: Whether to filter for AI-related content only
            
        Returns:
            Tuple of (should_keep, reason)
        """
        path = Path(file_path)
        
        # Check if file exists
        if not path.exists():
            return False, "File not found"
        
        # Check file size
        size = path.stat().st_size
        if size == 0:
            return False, "Empty file"
        
        if size > 500 * 1024 * 1024:  # 500 MB
            return False, "File too large"
        
        # Check file extension
        ext = path.suffix.lower()
        valid_exts = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt"}
        if ext not in valid_exts:
            return False, f"Unsupported file type: {ext}"
        
        # If AI-only filtering is enabled, check content
        if ai_only:
            try:
                # Quick check using title and filename first
                if self.is_ai_related("", title, path.name):
                    return True, "AI-related (by metadata)"
                
                # For now, accept all files if metadata check passes
                # Full content checking would require reading the file
                return True, "Accepted (requires content check)"
            except Exception as e:
                logger.warning("Error checking AI relevance for %s: %s", file_path, e)
                return True, "Accepted (check failed)"
        
        return True, "Accepted"
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize text content.
        
        Args:
            text: Raw text
            
        Returns:
            Cleaned text
        """
        if not text:
            return ""
        
        # Remove excessive whitespace
        text = " ".join(text.split())
        
        # Remove common PDF artifacts
        text = text.replace("\x00", "")
        text = text.replace("\ufffd", "")
        
        return text.strip()
