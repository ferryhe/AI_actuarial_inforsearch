"""StorageV2 RAG extension - Chunk profiles, KB management, and index operations.

This module provides RAG-related storage operations using SQLAlchemy,
compatible with the API from storage.py.
"""

from __future__ import annotations

import json
import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Iterable, Optional

from sqlalchemy import func, or_, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .db_models import (
    ChunkProfile, FileChunkSet, GlobalChunk, ChunkEmbedding,
    KBChunkBinding, KBIndexVersion, KBIndexItem
)
from .db_backend import DatabaseBackend


class StorageV2RAGMixin:
    """Mixin providing RAG-related storage operations."""
    
    def __init__(self, db_config: dict[str, Any]) -> None:
        """Initialize storage with database configuration."""
        # This will be set by the parent class
        self.backend: DatabaseBackend = None
        self.db_path = db_config.get("path") if db_config.get("type") == "sqlite" else None
    
    @property
    def _session(self):
        """Get current database session."""
        return self.backend.get_session()
    
    @property
    def _conn(self):
        """Get raw database connection for compatibility."""
        return self._session.connection()
    
    def _utcnow_iso(self) -> str:
        """Get current UTC time as ISO string."""
        return datetime.now(timezone.utc).isoformat()
    
    def _parse_iso_to_utc(self, value: str | None) -> datetime | None:
        """Parse ISO timestamp string to UTC datetime."""
        raw = str(value or "").strip()
        if not raw:
            return None
        text = raw.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except Exception:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    
    def create_chunk_profile(
        self,
        *,
        name: str,
        chunk_size: int,
        chunk_overlap: int,
        splitter: str = "semantic",
        tokenizer: str = "cl100k_base",
        version: str = "v1",
        metadata: dict[str, Any] | None = None,
        upsert: bool = True,
    ) -> dict[str, Any]:
        """Create (or reuse) a chunk profile."""
        normalized_name = str(name or "").strip()
        payload = {
            "chunk_size": int(chunk_size),
            "chunk_overlap": int(chunk_overlap),
            "splitter": str(splitter or "semantic"),
            "tokenizer": str(tokenizer or "cl100k_base"),
            "version": str(version or "v1"),
            "metadata": metadata or {},
        }
        config_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        config_hash = hashlib.sha256(config_json.encode("utf-8")).hexdigest()

        # Check for existing profile with same name (case-insensitive)
        if normalized_name:
            existing = self._session.query(ChunkProfile).filter(
                func.lower(ChunkProfile.name) == normalized_name.lower()
            ).first()
            if existing:
                if existing.config_hash != config_hash:
                    raise ValueError(f"chunk profile name already exists: {normalized_name}")
                return {
                    "profile_id": existing.profile_id,
                    "name": existing.name,
                    "chunk_size": existing.chunk_size,
                    "chunk_overlap": existing.chunk_overlap,
                    "splitter": existing.splitter,
                    "tokenizer": existing.tokenizer,
                    "version": existing.version,
                    "config_hash": existing.config_hash,
                    "config_json": existing.config_json,
                    "created_at": existing.created_at,
                    "updated_at": existing.updated_at,
                }

        # Check for existing profile with same config hash
        existing = self._session.query(ChunkProfile).filter(
            ChunkProfile.config_hash == config_hash
        ).first()
        if existing:
            return {
                "profile_id": existing.profile_id,
                "name": existing.name,
                "chunk_size": existing.chunk_size,
                "chunk_overlap": existing.chunk_overlap,
                "splitter": existing.splitter,
                "tokenizer": existing.tokenizer,
                "version": existing.version,
                "config_hash": existing.config_hash,
                "config_json": existing.config_json,
                "created_at": existing.created_at,
                "updated_at": existing.updated_at,
            }

        # Create new profile
        profile_id = f"cp_{uuid.uuid4().hex}"
        now = self._utcnow_iso()
        profile = ChunkProfile(
            profile_id=profile_id,
            name=normalized_name or profile_id,
            config_hash=config_hash,
            config_json=config_json,
            chunk_size=payload["chunk_size"],
            chunk_overlap=payload["chunk_overlap"],
            splitter=payload["splitter"],
            tokenizer=payload["tokenizer"],
            version=payload["version"],
            created_at=now,
            updated_at=now,
        )
        self._session.add(profile)
        self.backend._maybe_commit()
        
        return {
            "profile_id": profile_id,
            "name": normalized_name or profile_id,
            "chunk_size": payload["chunk_size"],
            "chunk_overlap": payload["chunk_overlap"],
            "splitter": payload["splitter"],
            "tokenizer": payload["tokenizer"],
            "version": payload["version"],
            "config_hash": config_hash,
            "config_json": config_json,
            "created_at": now,
            "updated_at": now,
        }

    def list_chunk_profiles(self) -> list[dict[str, Any]]:
        """List all chunk profiles."""
        profiles = self._session.query(ChunkProfile).order_by(
            ChunkProfile.updated_at.desc(), ChunkProfile.created_at.desc()
        ).all()
        
        return [
            {
                "profile_id": p.profile_id,
                "name": p.name,
                "chunk_size": p.chunk_size,
                "chunk_overlap": p.chunk_overlap,
                "splitter": p.splitter,
                "tokenizer": p.tokenizer,
                "version": p.version,
                "config_hash": p.config_hash,
                "config_json": p.config_json,
                "created_at": p.created_at,
                "updated_at": p.updated_at,
            }
            for p in profiles
        ]

    def get_chunk_profile(self, profile_id: str) -> dict[str, Any] | None:
        """Get a chunk profile by ID."""
        profile = self._session.query(ChunkProfile).filter(
            ChunkProfile.profile_id == profile_id
        ).first()
        
        if not profile:
            return None
        
        return {
            "profile_id": profile.profile_id,
            "name": profile.name,
            "chunk_size": profile.chunk_size,
            "chunk_overlap": profile.chunk_overlap,
            "splitter": profile.splitter,
            "tokenizer": profile.tokenizer,
            "version": profile.version,
            "config_hash": profile.config_hash,
            "config_json": profile.config_json,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        }

    def get_or_create_file_chunk_set(
        self,
        *,
        file_url: str,
        profile_id: str,
        markdown_hash: str,
        status: str = "ready",
    ) -> dict[str, Any]:
        """Get or create a file chunk set."""
        existing = self._session.query(FileChunkSet).filter(
            and_(
                FileChunkSet.file_url == file_url,
                FileChunkSet.profile_id == profile_id,
                FileChunkSet.markdown_hash == markdown_hash
            )
        ).first()
        
        if existing:
            return {
                "chunk_set_id": existing.chunk_set_id,
                "file_url": existing.file_url,
                "profile_id": existing.profile_id,
                "markdown_hash": existing.markdown_hash,
                "status": existing.status,
                "chunk_count": existing.chunk_count,
                "created_at": existing.created_at,
                "updated_at": existing.updated_at,
                "created": False,
            }

        now = self._utcnow_iso()
        chunk_set_id = f"cs_{uuid.uuid4().hex}"
        chunk_set = FileChunkSet(
            chunk_set_id=chunk_set_id,
            file_url=file_url,
            profile_id=profile_id,
            markdown_hash=markdown_hash,
            status=status,
            chunk_count=0,
            created_at=now,
            updated_at=now,
        )
        self._session.add(chunk_set)
        self.backend._maybe_commit()
        
        return {
            "chunk_set_id": chunk_set_id,
            "file_url": file_url,
            "profile_id": profile_id,
            "markdown_hash": markdown_hash,
            "status": status,
            "chunk_count": 0,
            "created_at": now,
            "updated_at": now,
            "created": True,
        }

    def replace_global_chunks(
        self,
        *,
        chunk_set_id: str,
        chunks: list[dict[str, Any]],
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Insert chunks for one chunk set."""
        current_n = self._session.query(func.count(GlobalChunk.chunk_id)).filter(
            GlobalChunk.chunk_set_id == chunk_set_id
        ).scalar() or 0
        
        if current_n > 0 and not overwrite:
            return {"chunk_set_id": chunk_set_id, "chunk_count": current_n, "replaced": False, "inserted": 0}

        with self.backend.transaction():
            if current_n > 0:
                self._session.query(GlobalChunk).filter(
                    GlobalChunk.chunk_set_id == chunk_set_id
                ).delete()

            now = self._utcnow_iso()
            inserted = 0
            for idx, chunk in enumerate(chunks):
                content = str((chunk or {}).get("content") or "")
                token_count = int((chunk or {}).get("token_count") or 0)
                section_hierarchy = (chunk or {}).get("section_hierarchy")
                chunk_index = int((chunk or {}).get("chunk_index") if (chunk or {}).get("chunk_index") is not None else idx)
                chunk_id = f"{chunk_set_id}:{chunk_index}"
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                
                global_chunk = GlobalChunk(
                    chunk_id=chunk_id,
                    chunk_set_id=chunk_set_id,
                    chunk_index=chunk_index,
                    content=content,
                    token_count=token_count,
                    section_hierarchy=section_hierarchy,
                    content_hash=content_hash,
                    created_at=now,
                )
                self._session.add(global_chunk)
                inserted += 1

            self._session.query(FileChunkSet).filter(
                FileChunkSet.chunk_set_id == chunk_set_id
            ).update({
                "chunk_count": inserted,
                "status": "ready",
                "updated_at": now
            })

        return {
            "chunk_set_id": chunk_set_id,
            "chunk_count": inserted,
            "replaced": current_n > 0,
            "inserted": inserted,
        }

    def list_file_chunk_sets(self, file_url: str) -> list[dict[str, Any]]:
        """List chunk sets for a file."""
        from .db_models import ChunkProfile
        
        results = (
            self._session.query(FileChunkSet, ChunkProfile)
            .join(ChunkProfile, ChunkProfile.profile_id == FileChunkSet.profile_id)
            .filter(FileChunkSet.file_url == file_url)
            .order_by(FileChunkSet.updated_at.desc(), FileChunkSet.created_at.desc())
            .all()
        )
        
        from sqlalchemy import func
        out = []
        for chunk_set, profile in results:
            # Count KB bindings
            kb_count = self._session.query(func.count(KBChunkBinding.chunk_set_id)).filter(
                KBChunkBinding.chunk_set_id == chunk_set.chunk_set_id
            ).scalar() or 0
            
            out.append({
                "chunk_set_id": chunk_set.chunk_set_id,
                "file_url": chunk_set.file_url,
                "profile_id": chunk_set.profile_id,
                "profile_name": profile.name,
                "chunk_size": profile.chunk_size,
                "chunk_overlap": profile.chunk_overlap,
                "splitter": profile.splitter,
                "tokenizer": profile.tokenizer,
                "version": profile.version,
                "markdown_hash": chunk_set.markdown_hash,
                "status": chunk_set.status,
                "chunk_count": chunk_set.chunk_count,
                "created_at": chunk_set.created_at,
                "updated_at": chunk_set.updated_at,
                "bound_kb_count": kb_count,
            })
        return out

    def bind_chunk_set_to_kb(
        self,
        *,
        kb_id: str,
        file_url: str,
        chunk_set_id: str,
        bound_by: str = "system",
        binding_mode: str = "pin",
    ) -> dict[str, Any]:
        """Bind one chunk set to one KB."""
        mode = str(binding_mode or "pin").strip().lower()
        if mode not in {"pin", "follow_latest"}:
            raise ValueError("binding_mode must be 'pin' or 'follow_latest'")
        
        now = self._utcnow_iso()
        
        # Validate chunk_set belongs to this file
        chunk_set = self._session.query(FileChunkSet).filter(
            FileChunkSet.chunk_set_id == chunk_set_id
        ).first()
        if not chunk_set:
            raise ValueError("chunk_set_id not found")
        if chunk_set.file_url != file_url:
            raise ValueError("chunk_set_id does not belong to the specified file_url")
        
        target_profile_id = chunk_set.profile_id if mode == "follow_latest" else None

        with self.backend.transaction():
            # For follow_latest mode, clean up old bindings
            if mode == "follow_latest":
                self._session.query(KBChunkBinding).filter(
                    and_(
                        KBChunkBinding.kb_id == kb_id,
                        KBChunkBinding.file_url == file_url,
                        KBChunkBinding.binding_mode == "follow_latest",
                        KBChunkBinding.chunk_set_id != chunk_set_id
                    )
                ).filter(
                    or_(
                        KBChunkBinding.target_profile_id == target_profile_id,
                        and_(KBChunkBinding.target_profile_id.is_(None), target_profile_id == "")
                    )
                ).delete(synchronize_session=False)

            # Check if binding exists
            existing = self._session.query(KBChunkBinding).filter(
                and_(
                    KBChunkBinding.kb_id == kb_id,
                    KBChunkBinding.file_url == file_url,
                    KBChunkBinding.chunk_set_id == chunk_set_id
                )
            ).first()
            
            if existing:
                if existing.binding_mode != mode or existing.target_profile_id != target_profile_id:
                    existing.bound_at = now
                    existing.bound_by = bound_by
                    existing.binding_mode = mode
                    existing.target_profile_id = target_profile_id
                return {
                    "kb_id": kb_id,
                    "file_url": file_url,
                    "chunk_set_id": chunk_set_id,
                    "binding_mode": mode,
                    "target_profile_id": target_profile_id or "",
                    "created": False,
                }

            # Create new binding
            binding = KBChunkBinding(
                kb_id=kb_id,
                file_url=file_url,
                chunk_set_id=chunk_set_id,
                bound_at=now,
                bound_by=bound_by,
                binding_mode=mode,
                target_profile_id=target_profile_id,
            )
            self._session.add(binding)
            
            return {
                "kb_id": kb_id,
                "file_url": file_url,
                "chunk_set_id": chunk_set_id,
                "binding_mode": mode,
                "target_profile_id": target_profile_id or "",
                "created": True,
            }

    def list_file_index_status(self, file_url: str) -> list[dict[str, Any]]:
        """List index status for a file across KBs."""
        from sqlalchemy import func
        
        results = (
            self._session.query(
                KBChunkBinding.kb_id,
                func.count(func.distinct(KBChunkBinding.chunk_set_id)).label("chunk_set_count")
            )
            .filter(KBChunkBinding.file_url == file_url)
            .group_by(KBChunkBinding.kb_id)
            .all()
        )
        
        out = []
        for kb_id, chunk_set_count in results:
            # Get latest index for this KB
            latest_idx = self._session.query(KBIndexVersion).filter(
                KBIndexVersion.kb_id == kb_id
            ).order_by(
                func.coalesce(KBIndexVersion.built_at, KBIndexVersion.created_at).desc()
            ).first()
            
            out.append({
                "kb_id": kb_id,
                "chunk_set_count": chunk_set_count or 0,
                "embedding_model": latest_idx.embedding_model if latest_idx else "",
                "indexed_at": (latest_idx.built_at or latest_idx.created_at) if latest_idx else None,
                "indexed_chunk_count": latest_idx.chunk_count if latest_idx else 0,
            })
        
        return out

    def get_kb_composition_status(self, kb_id: str) -> dict[str, Any]:
        """Get KB composition status."""
        from sqlalchemy import func, or_
        
        # Count unique files and chunk sets
        file_count = self._session.query(
            func.count(func.distinct(KBChunkBinding.file_url))
        ).filter(KBChunkBinding.kb_id == kb_id).scalar() or 0
        
        chunk_set_count = self._session.query(
            func.count(func.distinct(KBChunkBinding.chunk_set_id))
        ).filter(KBChunkBinding.kb_id == kb_id).scalar() or 0
        
        # Get latest index
        latest = self._session.query(KBIndexVersion).filter(
            KBIndexVersion.kb_id == kb_id
        ).order_by(
            func.coalesce(KBIndexVersion.built_at, KBIndexVersion.created_at).desc()
        ).first()
        
        # Get latest binding time
        latest_binding = self._session.query(
            func.max(KBChunkBinding.bound_at)
        ).filter(KBChunkBinding.kb_id == kb_id).scalar()
        
        # Count binding modes
        mode_counts = self._session.query(
            func.sum(func.cast(KBChunkBinding.binding_mode == "follow_latest", Integer)),
            func.sum(func.cast(
                or_(KBChunkBinding.binding_mode == "pin", KBChunkBinding.binding_mode.is_(None)), Integer
            ))
        ).filter(KBChunkBinding.kb_id == kb_id).first()
        
        follow_latest_count = mode_counts[0] or 0 if mode_counts else 0
        pin_count = mode_counts[1] or 0 if mode_counts else 0
        
        has_index = bool(latest)
        latest_index_time = (latest.built_at or latest.created_at) if latest else None
        needs_reindex = bool(
            file_count > 0 and (
                not has_index or 
                (latest_binding and latest_index_time and latest_binding > latest_index_time)
            )
        )
        
        return {
            "kb_id": kb_id,
            "file_count": file_count,
            "chunk_set_count": chunk_set_count,
            "has_index": has_index,
            "latest_binding_at": latest_binding,
            "binding_mode_counts": {
                "follow_latest": follow_latest_count,
                "pin": pin_count,
            },
            "outdated_binding_count": 0,
            "new_chunk_versions_available": False,
            "needs_reindex": needs_reindex,
            "latest_index": {
                "embedding_model": latest.embedding_model,
                "index_type": latest.index_type,
                "status": latest.status,
                "chunk_count": latest.chunk_count,
                "built_at": latest.built_at or latest.created_at,
            }
            if latest else None,
        }

    def list_kb_chunk_bindings(self, kb_id: str) -> list[dict[str, Any]]:
        """List all chunk bindings for a KB."""
        from .db_models import ChunkProfile
        
        results = (
            self._session.query(KBChunkBinding, FileChunkSet, ChunkProfile)
            .outerjoin(FileChunkSet, FileChunkSet.chunk_set_id == KBChunkBinding.chunk_set_id)
            .outerjoin(ChunkProfile, ChunkProfile.profile_id == FileChunkSet.profile_id)
            .filter(KBChunkBinding.kb_id == kb_id)
            .order_by(KBChunkBinding.bound_at.desc())
            .all()
        )
        
        out = []
        for binding, chunk_set, profile in results:
            # Find latest chunk set for this file/profile
            latest = None
            if profile and chunk_set:
                latest = self._session.query(FileChunkSet).filter(
                    and_(
                        FileChunkSet.file_url == binding.file_url,
                        FileChunkSet.profile_id == profile.profile_id
                    )
                ).order_by(FileChunkSet.updated_at.desc()).first()
            
            out.append({
                "kb_id": binding.kb_id,
                "file_url": binding.file_url,
                "chunk_set_id": binding.chunk_set_id,
                "bound_at": binding.bound_at,
                "bound_by": binding.bound_by,
                "binding_mode": binding.binding_mode or "pin",
                "target_profile_id": binding.target_profile_id or "",
                "profile_id": profile.profile_id if profile else None,
                "profile_name": profile.name if profile else "",
                "chunk_count": chunk_set.chunk_count if chunk_set else 0,
                "markdown_hash": chunk_set.markdown_hash if chunk_set else "",
                "chunk_set_updated_at": chunk_set.updated_at if chunk_set else None,
                "latest_chunk_set_id": latest.chunk_set_id if latest else "",
                "is_latest_for_profile": (latest.chunk_set_id if latest else "") == binding.chunk_set_id,
            })
        return out

    def create_kb_index_version(
        self,
        *,
        kb_id: str,
        embedding_model: str,
        index_type: str,
        chunk_count: int,
        status: str = "ready",
        artifact_path: str = "",
        chunk_ids: list[str] | None = None,
        built_at: str | None = None,
    ) -> dict[str, Any]:
        """Create a new KB index version."""
        now = self._utcnow_iso()
        index_version_id = f"idxv_{uuid.uuid4().hex}"
        built_time = built_at or now
        
        with self.backend.transaction():
            # Delete old index versions
            self._session.query(KBIndexItem).filter(
                KBIndexItem.index_version_id.in_(
                    self._session.query(KBIndexVersion.index_version_id).filter(
                        KBIndexVersion.kb_id == kb_id
                    ).subquery()
                )
            ).delete(synchronize_session=False)
            
            self._session.query(KBIndexVersion).filter(
                KBIndexVersion.kb_id == kb_id
            ).delete(synchronize_session=False)
            
            # Create new index version
            index_version = KBIndexVersion(
                index_version_id=index_version_id,
                kb_id=kb_id,
                embedding_model=embedding_model,
                index_type=index_type,
                status=status,
                artifact_path=artifact_path,
                chunk_count=int(chunk_count),
                built_at=built_time,
                created_at=now,
            )
            self._session.add(index_version)
            
            # Add chunk references
            if chunk_ids:
                for chunk_id in chunk_ids:
                    item = KBIndexItem(
                        index_version_id=index_version_id,
                        chunk_id=chunk_id,
                    )
                    self._session.add(item)
        
        return {
            "index_version_id": index_version_id,
            "kb_id": kb_id,
            "embedding_model": embedding_model,
            "index_type": index_type,
            "status": status,
            "artifact_path": artifact_path,
            "chunk_count": int(chunk_count),
            "built_at": built_time,
            "created_at": now,
        }

    def cleanup_orphan_chunk_sets(
        self,
        *,
        older_than_days: int = 30,
        limit: int = 5000,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Clean up orphan chunk sets not bound to any KB."""
        days = max(1, int(older_than_days))
        max_rows = max(1, min(int(limit), 20000))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Find orphan chunk sets
        subquery = self._session.query(KBChunkBinding.chunk_set_id).distinct()
        
        orphan_sets = (
            self._session.query(FileChunkSet)
            .filter(~FileChunkSet.chunk_set_id.in_(subquery))
            .filter(
                or_(
                    FileChunkSet.updated_at < cutoff.isoformat(),
                    FileChunkSet.created_at < cutoff.isoformat()
                )
            )
            .limit(max_rows)
            .all()
        )
        
        candidates = []
        for cs in orphan_sets:
            # Count chunks
            chunk_count = self._session.query(func.count(GlobalChunk.chunk_id)).filter(
                GlobalChunk.chunk_set_id == cs.chunk_set_id
            ).scalar() or 0
            
            candidates.append({
                "chunk_set_id": cs.chunk_set_id,
                "file_url": cs.file_url,
                "profile_id": cs.profile_id,
                "created_at": cs.created_at,
                "updated_at": cs.updated_at,
                "chunk_count": chunk_count,
            })
        
        total_chunks = sum(c.get("chunk_count", 0) for c in candidates)
        
        if dry_run or not candidates:
            return {
                "older_than_days": days,
                "dry_run": bool(dry_run),
                "deleted_chunk_sets": 0,
                "deleted_chunks": 0,
                "candidates": len(candidates),
                "candidate_chunk_sets": candidates,
            }
        
        with self.backend.transaction():
            for item in candidates:
                chunk_set_id = item["chunk_set_id"]
                
                # Delete embeddings
                self._session.query(ChunkEmbedding).filter(
                    ChunkEmbedding.chunk_id.like(f"{chunk_set_id}:%")
                ).delete(synchronize_session=False)
                
                # Delete chunks
                self._session.query(GlobalChunk).filter(
                    GlobalChunk.chunk_set_id == chunk_set_id
                ).delete(synchronize_session=False)
                
                # Delete chunk set
                self._session.query(FileChunkSet).filter(
                    FileChunkSet.chunk_set_id == chunk_set_id
                ).delete(synchronize_session=False)
        
        return {
            "older_than_days": days,
            "dry_run": False,
            "deleted_chunk_sets": len(candidates),
            "deleted_chunks": total_chunks,
            "candidates": len(candidates),
            "candidate_chunk_sets": candidates[:50],
        }
