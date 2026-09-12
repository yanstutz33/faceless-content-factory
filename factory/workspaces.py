from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Settings
    from .store import Store


DEFAULT_WORKSPACE_ID = "3am-shelter"
WORKSPACE_SCHEMA_VERSION = 1
_WORKSPACE_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,46}[a-z0-9])?$")


def normalize_workspace_id(value: str) -> str:
    """Validate an opaque workspace identifier before it reaches the filesystem."""
    workspace_id = str(value or "").strip().lower()
    if not _WORKSPACE_ID.fullmatch(workspace_id):
        raise ValueError(
            "O espaço deve usar de 1 a 48 caracteres: letras minúsculas, números e hífens"
        )
    return workspace_id


@dataclass(frozen=True)
class WorkspaceContext:
    id: str
    name: str
    data_dir: Path
    created_at: str | None
    personal: bool = False

    @property
    def database_path(self) -> Path:
        return self.data_dir / "factory.db"

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def private_dir(self) -> Path:
        return self.data_dir / "private"

    @property
    def audit_path(self) -> Path:
        return self.data_dir / "integration-audit.jsonl"

    @property
    def deliveries_path(self) -> Path:
        return self.data_dir / "deliveries.json"

    def scoped_settings(self, settings: Settings) -> Settings:
        """Reuse application configuration while moving every persisted path."""
        return replace(settings, data_dir=self.data_dir, workspace_id=self.id)

    def open_store(self) -> Store:
        # Local import avoids making workspace discovery initialize the database.
        from .store import Store

        return Store(self.database_path)

    def public_info(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "personal": self.personal,
            "created_at": self.created_at,
            "data_dir": str(self.data_dir),
            "database": str(self.database_path),
        }


@dataclass(frozen=True)
class _WorkspaceManifest:
    id: str
    name: str
    schema_version: int
    created_at: str


class WorkspaceRegistry:
    """Provision physically isolated roots without changing the personal install.

    The existing ``data`` directory remains the reserved 3AM Shelter workspace.
    New workspaces live below ``data/workspaces/<id>`` and therefore receive
    separate SQLite databases, media, backups, audit logs and encrypted vaults.
    Merely looking up an identifier never creates a directory.
    """

    manifest_name = "workspace.json"

    def __init__(self, personal_data_dir: Path):
        self.personal_data_dir = personal_data_dir.resolve()
        self.workspaces_dir = (self.personal_data_dir / "workspaces").resolve()

    def personal(self) -> WorkspaceContext:
        return WorkspaceContext(
            id=DEFAULT_WORKSPACE_ID,
            name="3AM Shelter",
            data_dir=self.personal_data_dir,
            created_at=None,
            personal=True,
        )

    def _workspace_root(self, workspace_id: str) -> Path:
        candidate = (self.workspaces_dir / workspace_id).resolve()
        if candidate.parent != self.workspaces_dir:
            raise ValueError("Identificador de espaço inválido")
        return candidate

    def provision(self, workspace_id: str, name: str) -> WorkspaceContext:
        workspace_id = normalize_workspace_id(workspace_id)
        display_name = str(name or "").strip()
        if workspace_id == DEFAULT_WORKSPACE_ID:
            raise ValueError("3am-shelter é o espaço pessoal reservado")
        if not display_name or len(display_name) > 120:
            raise ValueError("O nome do espaço deve ter de 1 a 120 caracteres")

        root = self._workspace_root(workspace_id)
        manifest_path = root / self.manifest_name
        if root.exists():
            if not manifest_path.is_file():
                raise ValueError("A pasta do espaço já existe sem um manifesto válido")
            existing = self.get(workspace_id)
            if existing.name != display_name:
                raise ValueError("O identificador já pertence a outro nome de espaço")
            return existing

        root.mkdir(parents=True, exist_ok=False)
        manifest = _WorkspaceManifest(
            id=workspace_id,
            name=display_name,
            schema_version=WORKSPACE_SCHEMA_VERSION,
            created_at=datetime.now(UTC).isoformat(),
        )
        temporary = manifest_path.with_suffix(".tmp")
        try:
            temporary.write_text(
                json.dumps(asdict(manifest), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(manifest_path)
        except Exception:
            temporary.unlink(missing_ok=True)
            try:
                root.rmdir()
            except OSError:
                pass
            raise
        return self.get(workspace_id)

    def get(self, workspace_id: str) -> WorkspaceContext:
        workspace_id = normalize_workspace_id(workspace_id)
        if workspace_id == DEFAULT_WORKSPACE_ID:
            return self.personal()
        root = self._workspace_root(workspace_id)
        manifest_path = root / self.manifest_name
        if not manifest_path.is_file():
            raise ValueError("Espaço não encontrado; crie-o explicitamente antes de usar")
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = _WorkspaceManifest(
                id=normalize_workspace_id(raw["id"]),
                name=str(raw["name"]).strip(),
                schema_version=int(raw["schema_version"]),
                created_at=str(raw["created_at"]),
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Manifesto do espaço inválido") from exc
        if manifest.id != workspace_id or manifest.schema_version != WORKSPACE_SCHEMA_VERSION:
            raise ValueError("Manifesto do espaço não corresponde ao diretório ou à versão esperada")
        if not manifest.name or len(manifest.name) > 120:
            raise ValueError("Manifesto do espaço possui nome inválido")
        return WorkspaceContext(
            id=manifest.id,
            name=manifest.name,
            data_dir=root,
            created_at=manifest.created_at,
        )

    def list(self) -> list[WorkspaceContext]:
        workspaces = [self.personal()]
        if not self.workspaces_dir.is_dir():
            return workspaces
        for child in sorted(self.workspaces_dir.iterdir(), key=lambda item: item.name):
            if not child.is_dir():
                continue
            try:
                workspaces.append(self.get(child.name))
            except ValueError:
                # Invalid or partial folders are never exposed as usable tenants.
                continue
        return workspaces
