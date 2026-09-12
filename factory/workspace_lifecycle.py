"""Safe, local lifecycle operations for non-personal workspaces.

This module deliberately has no HTTP or CLI dependency.  Callers must decide
how to authenticate and confirm a destructive request before calling it.
Every operation is constrained to a provisioned tenant under
``data/workspaces``; the personal 3AM Shelter root is never eligible.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .workspaces import DEFAULT_WORKSPACE_ID, WorkspaceContext, WorkspaceRegistry, normalize_workspace_id


class WorkspaceLifecycleError(RuntimeError):
    """Raised when a lifecycle operation cannot preserve its safety contract."""


_REQUEST_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_DEMO_MANIFEST = ".ffactory-demo.json"
_DEMO_DIR = "demo"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class WorkspaceLifecycle:
    """Export, demo and deletion primitives scoped to provisioned client roots."""

    def __init__(self, registry: WorkspaceRegistry, *, export_dir: Path | None = None,
                 deletion_backup_dir: Path | None = None, backup_retention: int = 3):
        if backup_retention < 1:
            raise ValueError("A retenção de backups deve ser de pelo menos um arquivo")
        self.registry = registry
        control_root = registry.personal_data_dir / "workspace-lifecycle"
        self.export_dir = (export_dir or control_root / "exports").resolve()
        self.deletion_backup_dir = (deletion_backup_dir or control_root / "deletion-backups").resolve()
        self.backup_retention = backup_retention

    @staticmethod
    def _request_id(value: str | None) -> str:
        request_id = str(value or f"export-{uuid.uuid4().hex}").strip().lower()
        if not _REQUEST_ID.fullmatch(request_id):
            raise ValueError("Identificador de exportação inválido")
        return request_id

    def _context(self, workspace_id: str) -> WorkspaceContext:
        normalized = normalize_workspace_id(workspace_id)
        if normalized == DEFAULT_WORKSPACE_ID:
            raise PermissionError("O espaço pessoal 3am-shelter não pode ser exportado, demonstrado ou excluído")
        context = self.registry.get(normalized)
        root = context.data_dir.resolve()
        if context.personal or root.parent != self.registry.workspaces_dir:
            raise WorkspaceLifecycleError("A operação só pode atingir uma raiz isolada de cliente")
        return context

    @staticmethod
    def _files(context: WorkspaceContext, *, include_private: bool = True) -> list[Path]:
        root = context.data_dir.resolve()
        files: list[Path] = []
        for current, directories, names in os.walk(root, followlinks=False):
            current_path = Path(current)
            if current_path.is_symlink():
                raise WorkspaceLifecycleError("Links simbólicos não podem participar de exportação ou exclusão")
            for directory in directories:
                if (current_path / directory).is_symlink():
                    raise WorkspaceLifecycleError("Links simbólicos não podem participar de exportação ou exclusão")
            if not include_private and current_path == root:
                directories[:] = [directory for directory in directories if directory != "private"]
            for name in names:
                item = current_path / name
                if item.is_symlink() or not item.is_file():
                    raise WorkspaceLifecycleError("Arquivo inválido dentro do espaço")
                resolved = item.resolve()
                if root not in resolved.parents:
                    raise WorkspaceLifecycleError("Arquivo fora do escopo do espaço")
                files.append(item)
        return sorted(files, key=lambda item: item.relative_to(root).as_posix())

    @staticmethod
    def _manifest(context: WorkspaceContext, files: list[Path], *, include_private: bool) -> dict[str, Any]:
        root = context.data_dir.resolve()
        return {
            "format": "ffactory-workspace-export/v1",
            "created_at": _now(),
            "workspace": {"id": context.id, "name": context.name, "personal": False},
            "algorithm": "sha256",
            "private_credentials_included": include_private,
            "excluded_paths": [] if include_private else ["private/"],
            "files": [
                {"path": item.relative_to(root).as_posix(), "size_bytes": item.stat().st_size,
                 "sha256": _sha256(item)}
                for item in files
            ],
        }

    @staticmethod
    def _lock_down(path: Path) -> None:
        """Best-effort private file permissions; ACL ownership remains platform policy."""
        try:
            path.chmod(0o600)
        except OSError:
            pass

    def _archive(self, context: WorkspaceContext, target_dir: Path, request_id: str,
                 *, kind: str, include_private: bool) -> dict[str, Any]:
        files = self._files(context, include_private=include_private)
        manifest = self._manifest(context, files, include_private=include_private)
        target_dir.mkdir(parents=True, exist_ok=True)
        archive = target_dir / f"{context.id}-{request_id}.zip"
        receipt = target_dir / f"{context.id}-{request_id}.manifest.json"
        if archive.exists() or receipt.exists():
            if archive.is_file() and receipt.is_file():
                saved = json.loads(receipt.read_text(encoding="utf-8"))
                if saved.get("archive_sha256") == _sha256(archive):
                    return {**saved, "idempotent": True}
            raise WorkspaceLifecycleError("Já existe uma exportação parcial ou divergente com este identificador")
        temporary = archive.with_name(f".{archive.name}.{uuid.uuid4().hex}.tmp")
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
                for item in files:
                    bundle.write(item, item.relative_to(context.data_dir).as_posix())
                bundle.writestr("workspace-export-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            temporary.replace(archive)
            self._lock_down(archive)
            record = {
                "kind": kind,
                "request_id": request_id,
                "created_at": _now(),
                "archive": str(archive),
                "archive_sha256": _sha256(archive),
                "manifest": manifest,
                "idempotent": False,
            }
            _atomic_json(receipt, record)
            self._lock_down(receipt)
            return record
        except Exception:
            temporary.unlink(missing_ok=True)
            archive.unlink(missing_ok=True)
            receipt.unlink(missing_ok=True)
            raise

    def export_workspace(self, workspace_id: str, *, request_id: str | None = None) -> dict[str, Any]:
        """Create an atomic ZIP plus sidecar manifest/checksum for one client workspace."""
        return self._archive(self._context(workspace_id), self.export_dir, self._request_id(request_id),
                             kind="export", include_private=False)

    def deletion_plan(self, workspace_id: str) -> dict[str, Any]:
        """Return a non-mutating deletion preview; it never creates a backup or changes files."""
        context = self._context(workspace_id)
        files = self._files(context)
        return {
            "dry_run": True,
            "workspace_id": context.id,
            "workspace_root": str(context.data_dir),
            "file_count": len(files),
            "total_bytes": sum(item.stat().st_size for item in files),
            "backup_required": True,
            "confirmation_required": f"DELETE:{context.id}",
        }

    def _receipt_path(self, workspace_id: str) -> Path:
        return self.deletion_backup_dir / f"{workspace_id}.deletion.json"

    def _prune_backups(self, workspace_id: str) -> None:
        archives = sorted(self.deletion_backup_dir.glob(f"{workspace_id}-backup-*.zip"),
                          key=lambda item: item.stat().st_mtime, reverse=True)
        for archive in archives[self.backup_retention:]:
            archive.unlink(missing_ok=True)
            archive.with_suffix(".manifest.json").unlink(missing_ok=True)

    def delete_workspace(self, workspace_id: str, *, confirmation: str) -> dict[str, Any]:
        """Backup then remove one client workspace, with rollback if removal fails.

        This intentionally requires an exact, caller-visible confirmation string.  HTTP
        or CLI adapters should additionally require a recent re-authentication.
        """
        normalized = normalize_workspace_id(workspace_id)
        if normalized == DEFAULT_WORKSPACE_ID:
            raise PermissionError("O espaço pessoal 3am-shelter não pode ser exportado, demonstrado ou excluído")
        if confirmation != f"DELETE:{normalized}":
            raise PermissionError("Confirmação explícita de exclusão ausente ou inválida")
        try:
            context = self._context(normalized)
        except ValueError:
            receipt = self._receipt_path(normalized)
            if receipt.is_file():
                saved = json.loads(receipt.read_text(encoding="utf-8"))
                return {**saved, "already_deleted": True}
            raise
        backup = self._archive(context, self.deletion_backup_dir, f"backup-{uuid.uuid4().hex}",
                               kind="deletion-backup", include_private=True)
        root = context.data_dir
        tombstone = root.with_name(f".deleting-{context.id}-{uuid.uuid4().hex}")
        root.replace(tombstone)
        try:
            shutil.rmtree(tombstone)
        except Exception as exc:
            if tombstone.exists() and not root.exists():
                tombstone.replace(root)
            raise WorkspaceLifecycleError("A exclusão falhou; o espaço foi restaurado e o backup foi preservado") from exc
        record = {
            "workspace_id": context.id,
            "deleted_at": _now(),
            "backup_archive": backup["archive"],
            "backup_sha256": backup["archive_sha256"],
        }
        _atomic_json(self._receipt_path(context.id), record)
        self._lock_down(self._receipt_path(context.id))
        self._prune_backups(context.id)
        return {**record, "already_deleted": False}

    def demo_status(self, workspace_id: str) -> dict[str, Any]:
        context = self._context(workspace_id)
        marker = context.data_dir / _DEMO_MANIFEST
        if not marker.is_file():
            return {"workspace_id": context.id, "seeded": False}
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkspaceLifecycleError("Marcador de demonstração inválido") from exc
        if data.get("managed_by") != "workspace-lifecycle/demo-v1" or data.get("workspace_id") != context.id:
            raise WorkspaceLifecycleError("Marcador de demonstração não pertence ao espaço selecionado")
        return {"workspace_id": context.id, "seeded": True, "seeded_at": data.get("seeded_at")}

    def seed_demo(self, workspace_id: str) -> dict[str, Any]:
        """Seed a discardable file-only demo bundle without modifying application data."""
        context = self._context(workspace_id)
        status = self.demo_status(context.id)
        if status["seeded"]:
            return {**status, "idempotent": True}
        demo_dir = context.data_dir / _DEMO_DIR
        if demo_dir.exists():
            raise WorkspaceLifecycleError("A pasta demo já existe sem um marcador controlado")
        demo_dir.mkdir()
        try:
            (demo_dir / "README.txt").write_text(
                "Dados demonstrativos descartáveis. Não representam dados de 3AM Shelter.\n", encoding="utf-8"
            )
            (demo_dir / "first-project.json").write_text(json.dumps({
                "title": "Primeiro projeto demonstrativo", "status": "draft", "network": "disabled",
                "safe_to_delete": True,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            _atomic_json(context.data_dir / _DEMO_MANIFEST, {
                "managed_by": "workspace-lifecycle/demo-v1", "workspace_id": context.id,
                "seeded_at": _now(), "paths": ["demo/README.txt", "demo/first-project.json"],
            })
        except Exception:
            shutil.rmtree(demo_dir, ignore_errors=True)
            (context.data_dir / _DEMO_MANIFEST).unlink(missing_ok=True)
            raise
        return {**self.demo_status(context.id), "idempotent": False}

    def reset_demo(self, workspace_id: str) -> dict[str, Any]:
        """Remove only the service-owned demo bundle, never arbitrary workspace files."""
        context = self._context(workspace_id)
        status = self.demo_status(context.id)
        if not status["seeded"]:
            return {"workspace_id": context.id, "reset": False, "idempotent": True}
        demo_dir = context.data_dir / _DEMO_DIR
        if not demo_dir.is_dir() or demo_dir.is_symlink():
            raise WorkspaceLifecycleError("Pasta demo inválida; nenhuma exclusão foi executada")
        shutil.rmtree(demo_dir)
        (context.data_dir / _DEMO_MANIFEST).unlink()
        return {"workspace_id": context.id, "reset": True, "idempotent": False}
