"""Immutable skill packages and PostgreSQL publication pointers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import ValidationError

from ai_actuarial.postgres import PostgresConnection

from .registry import Registry, Skill, Tool, _guidance_dependencies, _SkillManifest

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_GIT_SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_KEY = re.compile(r"[a-zA-Z0-9_.-]+\Z")
_QUALIFIED_TOOL_ID = re.compile(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+")
_NAMED_TOOL = re.compile(
    r"(?<!`)`([A-Za-z0-9_-]+)`\s+tool\s+from\s+the\s+`([A-Za-z0-9_-]+)`\s+skill\b"
)
_POSSESSIVE_TOOL = re.compile(
    r"(?<!`)`([A-Za-z0-9_-]+)`\s+skill['’]s\s+`([A-Za-z0-9_-]+)`\s+tool(?![\w-])"
)


class ArtifactError(ValueError):
    """A candidate or published artifact cannot be used safely."""


class RevisionConflict(ArtifactError):
    """A slot changed since its caller read it."""


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class ArtifactStore:
    def __init__(
        self,
        database_url: str,
        data_dir: Path,
        *,
        executors: frozenset[str],
        argument_models: dict,
        registered_tools: tuple[Tool, ...],
    ):
        self.database_url = database_url
        self.root = Path(data_dir).resolve() / "agent_artifacts"
        self.executors = executors
        self.argument_models = argument_models
        self.registered_tools = {tool.tool_id: tool for tool in registered_tools}

    def _file(self, digest: str) -> Path:
        if not _DIGEST.fullmatch(digest):
            raise ArtifactError("Invalid artifact digest")
        return self.root / "sha256" / digest

    def _persist(self, content: bytes, digest: str) -> None:
        destination = self._file(digest)
        staging = self.root / "staging"
        staging.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=staging, delete=False) as handle:
            temporary = Path(handle.name)
            try:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
        try:
            if _digest(temporary.read_bytes()) != digest:
                raise ArtifactError("Staged artifact checksum mismatch")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if _digest(destination.read_bytes()) != digest:
                    raise ArtifactError("Existing artifact checksum mismatch")
            else:
                temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)

    def _skill(
        self, manifest: dict, artifacts: list[dict], contents: dict[str, bytes] | None = None
    ) -> Skill:
        try:
            parsed = _SkillManifest.model_validate(manifest)
            if not _KEY.fullmatch(parsed.skill_id) or not re.fullmatch(
                r"1\.[0-9]+(?:\.[0-9]+)?", parsed.version
            ):
                raise ArtifactError("Unknown skill or ABI version")
            for raw_item, item in zip(manifest["tools"], parsed.tools):
                registered = self.registered_tools.get(item.tool_id)
                if (
                    registered is None
                    or item.executor != registered.executor
                    or ("result_kind" in raw_item and item.result_kind != registered.result_kind)
                    or self.argument_models[item.arguments_model] is not registered.arguments
                ):
                    raise ArtifactError(
                        f"Unknown executor or incompatible tool contract: {item.tool_id}"
                    )
                if not registered.required_scopes <= frozenset(item.required_scopes):
                    raise ArtifactError(
                        f"Tool scope is weaker than registered contract: {item.tool_id}"
                    )
            # Older published manifests inherit the registered result contract.
            tools = tuple(
                Tool(
                    item.tool_id,
                    item.description,
                    item.executor,
                    self.argument_models[item.arguments_model],
                    frozenset(item.required_scopes),
                    self.registered_tools[item.tool_id].result_kind,
                    standalone_description=self.registered_tools[
                        item.tool_id
                    ].standalone_description,
                )
                for item in parsed.tools
            )
            if any(tool.executor not in self.executors for tool in tools):
                raise ArtifactError("Unknown executor")
            content = {}
            for item in artifacts:
                data = (
                    contents[item["artifact_id"]]
                    if contents and item["artifact_id"] in contents
                    else self._read_spec(item)
                )
                if _digest(data) != item["sha256"] or len(data) != item["size"]:
                    raise ArtifactError(f"Artifact checksum mismatch: {item['artifact_id']}")
                content[item["artifact_id"]] = data
            if "instructions" not in content:
                raise ArtifactError("Missing instructions artifact")
            instruction_text = content["instructions"].decode("utf-8").strip()
            if not instruction_text:
                raise ArtifactError("Empty skill instructions")
            description = parsed.description + "\n" + instruction_text
            references = set()
            for text in (
                parsed.description,
                instruction_text,
                *(tool.description for tool in tools),
            ):
                references.update(_QUALIFIED_TOOL_ID.findall(text))
                references.update(f"{owner}.{tool}" for tool, owner in _NAMED_TOOL.findall(text))
                references.update(
                    f"{owner}.{tool}" for owner, tool in _POSSESSIVE_TOOL.findall(text)
                )
            references = {
                token
                for token in references.intersection(self.registered_tools)
                if not token.startswith(parsed.skill_id + ".")
            }
            skill = Skill(
                parsed.skill_id,
                parsed.version,
                description,
                tools,
                parsed.enabled,
                expected_tool_ids=frozenset(
                    tool_id
                    for tool_id in self.registered_tools
                    if tool_id.startswith(parsed.skill_id + ".")
                ),
                guidance_dependencies=(
                    _guidance_dependencies(parsed.skill_id, published=True) | references
                ),
            )
            Registry((skill,), self.executors)
            return skill
        except (KeyError, UnicodeDecodeError, ValidationError) as exc:
            raise ArtifactError(f"Invalid skill manifest: {exc}") from exc

    def _read_spec(self, item: dict) -> bytes:
        digest = item["sha256"]
        if "inline_text" in item:
            content = item["inline_text"].encode("utf-8")
        else:
            try:
                content = self._file(digest).read_bytes()
            except FileNotFoundError as exc:
                raise ArtifactError(f"Missing artifact file: {item['artifact_id']}") from exc
        if _digest(content) != digest or len(content) != item["size"]:
            raise ArtifactError(f"Artifact checksum mismatch: {item['artifact_id']}")
        return content

    @staticmethod
    def _validated_receipt(
        manifest: dict,
        artifacts: list[dict],
        uat: dict,
        *,
        code_sha: str,
        data_version: str,
        model: str,
    ) -> dict:
        required = {
            "result",
            "evidence",
            "skill_id",
            "version",
            "artifact_digests",
            "code_sha",
            "data_version",
            "model",
        }
        expected = {
            "skill_id": manifest.get("skill_id"),
            "version": manifest.get("version"),
            "artifact_digests": {item["artifact_id"]: item["sha256"] for item in artifacts},
            "code_sha": code_sha,
            "data_version": data_version,
            "model": model,
        }
        if (
            not isinstance(uat, dict)
            or set(uat) not in (required, required | {"approval"})
            or uat.get("result") != "PASS"
            or not isinstance(uat.get("evidence"), str)
            or not uat["evidence"].strip()
            or ("approval" in uat and uat["approval"] != "APPROVED")
            or any(uat[key] != value for key, value in expected.items())
        ):
            raise ArtifactError("UAT receipt does not match this release")
        return {
            "uat": uat,
            "code_sha": code_sha,
            "data_version": data_version,
            "model": model,
            "artifact_digests": [a["sha256"] for a in artifacts],
        }

    def import_source(
        self,
        source: Path,
        *,
        feature_key: str,
        source_ref: str,
        uat: dict | None,
        code_sha: str,
        data_version: str,
        model: str,
        draft: bool = False,
    ) -> str:
        """Validate a Git package and receipt before inserting a candidate release."""
        source = Path(source).resolve()
        manifest = json.loads((source / "skill.json").read_text("utf-8"))
        raw_artifacts = manifest.pop("artifacts", [])
        if not raw_artifacts:
            raw_artifacts = [
                {
                    "artifact_id": "instructions",
                    "kind": "instructions",
                    "path": "SKILL.md",
                    "media_type": "text/markdown",
                }
            ]
        if not isinstance(raw_artifacts, list) or not _KEY.fullmatch(feature_key):
            raise ArtifactError("Invalid feature or artifact list")
        artifacts = []
        pending = []
        source_content = {}
        seen = set()
        for item in raw_artifacts:
            if not isinstance(item, dict) or set(item) - {
                "artifact_id",
                "kind",
                "path",
                "inline_text",
                "sha256",
                "media_type",
            }:
                raise ArtifactError("Invalid artifact declaration")
            artifact_id = item.get("artifact_id")
            if (
                not isinstance(artifact_id, str)
                or not _KEY.fullmatch(artifact_id)
                or artifact_id in seen
            ):
                raise ArtifactError("Duplicate or invalid artifact ID")
            if not isinstance(item.get("kind"), str) or not _KEY.fullmatch(item["kind"]):
                raise ArtifactError("Invalid artifact kind")
            seen.add(artifact_id)
            if ("path" in item) == ("inline_text" in item):
                raise ArtifactError("Artifact needs exactly one content source")
            if "path" in item:
                path = (source / item["path"]).resolve()
                if not path.is_relative_to(source) or not path.is_file():
                    raise ArtifactError("Artifact path escapes package or is missing")
                content = path.read_bytes()
            else:
                if not isinstance(item["inline_text"], str):
                    raise ArtifactError("Invalid inline artifact")
                content = item["inline_text"].encode("utf-8")
            digest = _digest(content)
            source_content[artifact_id] = content
            if "sha256" in item and item["sha256"] != digest:
                raise ArtifactError(f"Source artifact checksum mismatch: {artifact_id}")
            spec = {
                "artifact_id": artifact_id,
                "kind": item["kind"],
                "version": manifest.get("version"),
                "media_type": item.get("media_type", "application/octet-stream"),
                "sha256": digest,
                "size": len(content),
            }
            if "inline_text" in item:
                spec["inline_text"] = item["inline_text"]
            else:
                spec["storage_key"] = f"sha256/{digest}"
                pending.append((content, digest))
            artifacts.append(spec)
        if not _GIT_SHA.fullmatch(code_sha) or not all((source_ref, data_version, model)):
            raise ArtifactError("Incomplete source or UAT provenance")
        receipt = (
            {"code_sha": code_sha, "data_version": data_version, "model": model}
            if draft
            else self._validated_receipt(
                manifest,
                artifacts,
                uat,
                code_sha=code_sha,
                data_version=data_version,
                model=model,
            )
        )
        # Validate against registered code before placing any bytes on the durable volume.
        self._skill(manifest, artifacts, source_content)
        digest = _digest(_json({"manifest": manifest, "artifacts": artifacts}).encode())
        release_id = str(uuid4())
        db = PostgresConnection(self.database_url)
        try:
            existing = db.execute(
                "SELECT release_id,content_digest,status,source_ref,validation_jsonb "
                "FROM agent_skill_releases WHERE feature_key=? AND skill_key=? AND version=?",
                (feature_key, manifest["skill_id"], manifest["version"]),
            ).fetchone()
            if existing:
                return self._reuse_existing(
                    existing,
                    digest=digest,
                    source_ref=source_ref,
                    receipt=receipt,
                    draft=draft,
                )
            for content, artifact_digest in pending:
                self._persist(content, artifact_digest)
            inserted = db.execute(
                "INSERT INTO agent_skill_releases (release_id,feature_key,skill_key,version,executor_id,runtime_contract_version,manifest_jsonb,artifacts_jsonb,content_digest,source_ref,validation_jsonb,status,validated_at) VALUES (?,?,?,?,?,1,?::jsonb,?::jsonb,?,?,?::jsonb,?,CASE WHEN ? THEN NULL ELSE now() END) ON CONFLICT (feature_key,skill_key,version) DO NOTHING RETURNING release_id",
                (
                    release_id,
                    feature_key,
                    manifest["skill_id"],
                    manifest["version"],
                    "registry.v1",
                    _json(manifest),
                    _json(artifacts),
                    digest,
                    source_ref,
                    _json(receipt),
                    "draft" if draft else "validated",
                    draft,
                ),
            ).fetchone()
            if inserted:
                return str(inserted[0])
            existing = db.execute(
                "SELECT release_id,content_digest,status,source_ref,validation_jsonb "
                "FROM agent_skill_releases WHERE feature_key=? AND skill_key=? AND version=?",
                (feature_key, manifest["skill_id"], manifest["version"]),
            ).fetchone()
            if not existing:
                raise ArtifactError("Release version collision")
            return self._reuse_existing(
                existing,
                digest=digest,
                source_ref=source_ref,
                receipt=receipt,
                draft=draft,
            )
        finally:
            db.close()

    @staticmethod
    def _reuse_existing(row, *, digest: str, source_ref: str, receipt: dict, draft: bool) -> str:
        if row[1] != digest:
            raise ArtifactError("Immutable skill version collision")
        if row[2] != ("draft" if draft else "validated") and not (
            not draft and row[2] == "published"
        ):
            raise ArtifactError("Existing skill release is not reusable")
        if draft and (
            row[3] != source_ref or any(row[4].get(key) != value for key, value in receipt.items())
        ):
            raise ArtifactError("Existing skill release provenance mismatch")
        return str(row[0])

    def validate_draft(self, release_id: str, *, uat: dict) -> None:
        db = PostgresConnection(self.database_url, autocommit=False)
        try:
            row = db.execute(
                "SELECT manifest_jsonb,artifacts_jsonb,content_digest,validation_jsonb,status "
                "FROM agent_skill_releases WHERE release_id=? FOR UPDATE",
                (release_id,),
            ).fetchone()
            if not row or row[4] != "draft":
                raise ArtifactError("Unknown or non-draft release")
            manifest, artifacts, digest, provenance = row[:4]
            if _digest(_json({"manifest": manifest, "artifacts": artifacts}).encode()) != digest:
                raise ArtifactError("Release content digest mismatch")
            self._skill(manifest, artifacts)
            receipt = self._validated_receipt(manifest, artifacts, uat, **provenance)
            db.execute(
                "UPDATE agent_skill_releases SET validation_jsonb=?::jsonb,status='validated',"
                "validated_at=now() WHERE release_id=?",
                (_json(receipt), release_id),
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def retire(self, release_id: str) -> None:
        db = PostgresConnection(self.database_url, autocommit=False)
        try:
            row = db.execute(
                "SELECT status FROM agent_skill_releases WHERE release_id=? FOR UPDATE",
                (release_id,),
            ).fetchone()
            if not row or row[0] != "published":
                raise ArtifactError("Only a published release can be retired")
            if db.execute(
                "SELECT 1 FROM agent_skill_slots WHERE active_release_id=? OR previous_release_id=? LIMIT 1",
                (release_id, release_id),
            ).fetchone():
                raise ArtifactError("Active or previous release cannot be retired")
            db.execute(
                "UPDATE agent_skill_releases SET status='retired' WHERE release_id=?", (release_id,)
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def read(self, release_id: str, artifact_id: str) -> bytes:
        UUID(release_id)
        db = PostgresConnection(self.database_url, read_only=True)
        try:
            row = db.execute(
                "SELECT artifacts_jsonb,status FROM agent_skill_releases WHERE release_id=?",
                (release_id,),
            ).fetchone()
            if not row or row[1] != "published":
                raise ArtifactError("Unknown or unpublished release")
            items = row[0]
            item = next((entry for entry in items if entry["artifact_id"] == artifact_id), None)
            if item is None:
                raise ArtifactError(f"Unknown artifact: {artifact_id}")
            return self._read_spec(item)
        finally:
            db.close()

    def slots(self, *, feature_key: str, site_key: str) -> dict[str, dict]:
        db = PostgresConnection(self.database_url, read_only=True, autocommit=False)
        try:
            rows = db.execute(
                "SELECT skill_key,active_release_id,previous_release_id,revision FROM agent_skill_slots WHERE feature_key=? AND site_key=? ORDER BY skill_key",
                (feature_key, site_key),
            ).fetchall()
            return {
                r[0]: {
                    "active": str(r[1]) if r[1] else None,
                    "previous": str(r[2]) if r[2] else None,
                    "revision": r[3],
                }
                for r in rows
            }
        finally:
            db.close()

    def activate(
        self,
        *,
        feature_key: str,
        site_key: str,
        changes: dict[str, tuple[str, int]],
        expected_active: dict[str, str | None] | None = None,
    ) -> None:
        """Switch all requested slots or none, with per-slot expected revisions.

        Optionally require unchanged slots to retain the active IDs observed by the caller.
        """
        db = PostgresConnection(self.database_url, autocommit=False)
        try:
            db.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(current_database() || ':' || "
                "current_schema() || ':agent_skill_slots:' || ? || ':' || ?, 0))",
                (feature_key, site_key),
            )
            for skill_key, expected_release_id in sorted((expected_active or {}).items()):
                row = db.execute(
                    "SELECT active_release_id FROM agent_skill_slots WHERE feature_key=? AND site_key=? AND skill_key=? FOR UPDATE",
                    (feature_key, site_key, skill_key),
                ).fetchone()
                active_release_id = str(row[0]) if row and row[0] else None
                if active_release_id != expected_release_id:
                    raise RevisionConflict(f"Slot active release conflict: {skill_key}")
            for skill_key in sorted(changes):
                release_id, expected = changes[skill_key]
                db.execute(
                    "INSERT INTO agent_skill_slots(feature_key,site_key,skill_key) VALUES (?,?,?) ON CONFLICT DO NOTHING",
                    (feature_key, site_key, skill_key),
                )
                row = db.execute(
                    "SELECT active_release_id,previous_release_id,revision FROM agent_skill_slots WHERE feature_key=? AND site_key=? AND skill_key=? FOR UPDATE",
                    (feature_key, site_key, skill_key),
                ).fetchone()
                if row[2] != expected:
                    raise RevisionConflict(f"Slot revision conflict: {skill_key}")
                release = db.execute(
                    "SELECT manifest_jsonb,artifacts_jsonb,content_digest,status FROM agent_skill_releases WHERE release_id=? AND feature_key=? AND skill_key=? FOR UPDATE",
                    (release_id, feature_key, skill_key),
                ).fetchone()
                if not release or release[3] not in ("validated", "published"):
                    raise ArtifactError(f"Unknown or invalid release: {release_id}")
                if (
                    _digest(_json({"manifest": release[0], "artifacts": release[1]}).encode())
                    != release[2]
                ):
                    raise ArtifactError("Release content digest mismatch")
                self._skill(release[0], release[1])
                db.execute(
                    "UPDATE agent_skill_releases SET status='published',published_at=COALESCE(published_at,now()) WHERE release_id=?",
                    (release_id,),
                )
                db.execute(
                    "UPDATE agent_skill_slots SET active_release_id=?,previous_release_id=?,revision=revision+1,updated_at=now() WHERE feature_key=? AND site_key=? AND skill_key=?",
                    (
                        release_id,
                        row[1] if str(row[0]) == release_id else row[0],
                        feature_key,
                        site_key,
                        skill_key,
                    ),
                )
            active = db.execute(
                "SELECT r.manifest_jsonb,r.artifacts_jsonb FROM agent_skill_slots s JOIN agent_skill_releases r ON r.release_id=s.active_release_id WHERE s.feature_key=? AND s.site_key=?",
                (feature_key, site_key),
            ).fetchall()
            Registry(tuple(self._skill(row[0], row[1]) for row in active), self.executors)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def rollback(
        self, *, feature_key: str, site_key: str, skill_key: str, expected_revision: int
    ) -> None:
        slot = self.slots(feature_key=feature_key, site_key=site_key).get(skill_key)
        if not slot or not slot["previous"]:
            raise ArtifactError("No previous release")
        self.activate(
            feature_key=feature_key,
            site_key=site_key,
            changes={skill_key: (slot["previous"], expected_revision)},
        )

    def resolve_active(self, *, feature_key: str, site_key: str) -> tuple[Registry, dict[str, str]]:
        db = PostgresConnection(self.database_url, read_only=True, autocommit=False)
        try:
            rows = db.execute(
                "SELECT s.skill_key,r.release_id,r.manifest_jsonb,r.artifacts_jsonb,r.content_digest,r.status FROM agent_skill_slots s JOIN agent_skill_releases r ON r.release_id=s.active_release_id WHERE s.feature_key=? AND s.site_key=? ORDER BY s.skill_key",
                (feature_key, site_key),
            ).fetchall()
            skills = []
            pinned = {}
            for key, release_id, manifest, artifacts, digest, status in rows:
                if (
                    status != "published"
                    or _digest(_json({"manifest": manifest, "artifacts": artifacts}).encode())
                    != digest
                ):
                    raise ArtifactError(f"Invalid active release: {release_id}")
                skills.append(self._skill(manifest, artifacts))
                pinned[key] = str(release_id)
            return Registry(tuple(skills), self.executors), pinned
        finally:
            db.close()
