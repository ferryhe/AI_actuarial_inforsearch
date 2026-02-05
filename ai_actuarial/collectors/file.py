"""File collection workflow - import files from local file system."""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path

from .base import BaseCollector, CollectionConfig, CollectionResult
from ..storage import Storage

logger = logging.getLogger(__name__)

# Constants
SHA256_CHUNK_SIZE = 128 * 1024  # 128KB chunks for hash calculation
MAX_FILENAME_RETRIES = 1000  # Maximum attempts to find unique filename


class FileCollector(BaseCollector):
    """Collector for local file system imports."""
    
    def __init__(self, storage: Storage, download_dir: str):
        """Initialize file collector.
        
        Args:
            storage: Storage instance for database operations
            download_dir: Base directory for storing files
        """
        self.storage = storage
        self.download_dir = Path(download_dir)
    
    def collect(self, config: CollectionConfig, progress_callback=None) -> CollectionResult:
        """Execute file-based collection from local paths.
        
        Args:
            config: Collection configuration with file_paths in metadata
            progress_callback: Optional callback for progress updates
            
        Returns:
            CollectionResult with statistics
        """
        logger.info("Starting file collection: %s", config.name)
        
        errors = []
        items_found = 0
        items_downloaded = 0
        items_skipped = 0
        
        try:
            file_paths = config.metadata.get("file_paths", [])
            total_files = len(file_paths)
            target_subdir = config.metadata.get("target_subdir", "imported")
            
            if progress_callback:
                progress_callback(0, total_files, "Starting file collection")
            
            for i, file_path in enumerate(file_paths):
                if progress_callback:
                    progress_callback(i, total_files, f"Processing: {Path(file_path).name}")
                
                try:
                    source_path = Path(file_path)
                    
                    if not source_path.exists():
                        error_msg = f"File not found: {file_path}"
                        logger.error(error_msg)
                        errors.append(error_msg)
                        continue
                    
                    if not source_path.is_file():
                        error_msg = f"Not a file: {file_path}"
                        logger.error(error_msg)
                        errors.append(error_msg)
                        continue
                    
                    items_found += 1
                    
                    # Calculate SHA256
                    sha256 = self._calculate_sha256(source_path)
                    
                    # Check if hash already exists in DB
                    if self.storage.file_exists_by_hash(sha256):
                        logger.info("Skipping already imported file (hash match): %s", file_path)
                        items_skipped += 1
                        continue

                    # Check if should import
                    if config.check_database and not self.should_download(str(source_path), sha256):
                        logger.info("Skipping already imported file: %s", file_path)
                        items_skipped += 1
                        continue
                    
                    # Exclude check based on filename
                    if config.exclude_keywords:
                        if any(k.lower() in source_path.name.lower() for k in config.exclude_keywords):
                            logger.info("Skipping file (matched exclude keywords): %s", file_path)
                            items_skipped += 1
                            continue
                            
                    # Copy file to download directory
                    target_dir = self.download_dir / target_subdir
                    target_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Handle filename conflicts
                    target_path = self._get_unique_path(target_dir, source_path.name)
                    shutil.copy2(source_path, target_path)
                    
                    # Add to database
                    file_size = target_path.stat().st_size
                    base_dir = self.download_dir.parent.resolve()
                    target_resolved = target_path.resolve()
                    try:
                        rel_path = str(target_resolved.relative_to(base_dir))
                    except ValueError:
                        # Fallback to absolute path if relative path cannot be determined
                        rel_path = str(target_resolved)
                    
                    self.storage.insert_file(
                        url=f"file://{source_path}",
                        sha256=sha256,
                        title=source_path.stem,
                        source_site=config.name,
                        source_page_url=f"file://{source_path.parent}",
                        original_filename=source_path.name,
                        local_path=rel_path,
                        bytes=file_size,
                        content_type=self._guess_content_type(source_path.suffix),
                    )
                    
                    items_downloaded += 1
                    logger.info("Imported file: %s -> %s", source_path, target_path)
                    
                except Exception as e:
                    error_msg = f"Error importing file {file_path}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            
            success = len(errors) == 0 or items_downloaded > 0
            
            return CollectionResult(
                success=success,
                items_found=items_found,
                items_downloaded=items_downloaded,
                items_skipped=items_skipped,
                errors=errors,
                metadata={
                    "source_type": "file",
                    "files_processed": len(file_paths),
                }
            )
            
        except Exception as e:
            logger.exception("File collection failed")
            return CollectionResult(
                success=False,
                items_found=0,
                items_downloaded=0,
                items_skipped=0,
                errors=[str(e)],
            )
    
    def should_download(self, url: str, sha256: str | None = None) -> bool:
        """Check if file should be imported.
        
        Args:
            url: File path (used as URL)
            sha256: SHA256 hash of the file
            
        Returns:
            True if file should be imported
        """
        # For files, primarily check by SHA256 to avoid duplicates
        if sha256:
            existing = self.storage.get_file_by_sha256(sha256)
            if existing:
                logger.debug("File already in database (by hash): %s", sha256)
                return False
        
        # Also check by URL
        existing = self.storage.get_file_by_url(url)
        if existing:
            logger.debug("File already in database (by path): %s", url)
            return False
        
        return True
    
    def _calculate_sha256(self, file_path: Path) -> str:
        """Calculate SHA256 hash of a file.
        
        Args:
            file_path: Path to file
            
        Returns:
            SHA256 hash as hex string
        """
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(SHA256_CHUNK_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def _get_unique_path(self, directory: Path, filename: str) -> Path:
        """Get unique file path, adding suffix if file exists.
        
        Args:
            directory: Target directory
            filename: Desired filename
            
        Returns:
            Unique file path
            
        Raises:
            RuntimeError: If max retries exceeded
        """
        target = directory / filename
        if not target.exists():
            return target
        
        # Add numeric suffix
        stem = target.stem
        suffix = target.suffix
        
        for counter in range(1, MAX_FILENAME_RETRIES + 1):
            new_name = f"{stem}_{counter}{suffix}"
            target = directory / new_name
            if not target.exists():
                return target
        
        # If we get here, we've exceeded max retries
        raise RuntimeError(
            f"Failed to find unique filename after {MAX_FILENAME_RETRIES} attempts "
            f"for {filename}"
        )
    
    def _guess_content_type(self, suffix: str) -> str:
        """Guess content type from file extension.
        
        Args:
            suffix: File extension (e.g., '.pdf')
            
        Returns:
            Content type string
        """
        suffix = suffix.lower()
        content_types = {
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xls": "application/vnd.ms-excel",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".ppt": "application/vnd.ms-powerpoint",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".txt": "text/plain",
            ".csv": "text/csv",
        }
        return content_types.get(suffix, "application/octet-stream")
