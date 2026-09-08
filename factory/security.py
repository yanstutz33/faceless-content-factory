from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from .backup import BackupManager
from .config import Settings
from .vault import SecureVault


SECRET_PATTERNS = {
    "Pinterest access token": re.compile(r"pina_[A-Za-z0-9_-]{20,}"),
    "Google client secret": re.compile(r"GOCSPX-[A-Za-z0-9_-]{10,}"),
    "Google API key": re.compile(r"AIza[A-Za-z0-9_-]{20,}"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
}
SENSITIVE_NAMES = {".env", ".env.cloud", "oauth.vault", "client_secret.json"}


class SecurityAuditor:
    """Report security posture without returning any credential value."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def _tracked_files(self) -> list[Path]:
        result = subprocess.run(
            ["git", "-c", f"safe.directory={self.settings.root.as_posix()}", "ls-files", "-z"],
            cwd=self.settings.root, capture_output=True, check=False,
        )
        if result.returncode != 0:
            return []
        return [self.settings.root / item.decode("utf-8", errors="replace")
                for item in result.stdout.split(b"\0") if item]

    def audit(self) -> dict[str, Any]:
        tracked = self._tracked_files()
        sensitive_files, secret_hits = [], []
        for path in tracked:
            relative = path.relative_to(self.settings.root).as_posix()
            if path.name.lower() in SENSITIVE_NAMES or relative.startswith("data/private/"):
                sensitive_files.append(relative)
            try:
                if not path.is_file() or path.stat().st_size > 2_000_000:
                    continue
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for label, pattern in SECRET_PATTERNS.items():
                for match in pattern.finditer(content):
                    line = content.count("\n", 0, match.start()) + 1
                    secret_hits.append({"file": relative, "line": line, "type": label})

        vault = SecureVault(self.settings.data_dir / "private" / "oauth.vault").status()
        backup_manager = BackupManager(
            self.settings.data_dir / "factory.db", self.settings.data_dir / "backups", self.settings.backup_keep
        )
        try:
            restore = backup_manager.test_restore()
        except (OSError, RuntimeError, ValueError) as exc:
            restore = {"restored": False, "error": str(exc)}
        remote_safe = not self.settings.remote_access or (
            len(self.settings.remote_username) >= 3 and len(self.settings.remote_password) >= 24
        )
        checks = [
            {"id": "tracked_secrets", "passed": not secret_hits, "count": len(secret_hits)},
            {"id": "tracked_sensitive_files", "passed": not sensitive_files, "count": len(sensitive_files)},
            {"id": "encrypted_vault", "passed": vault.get("provider") not in {"unknown", "unreadable"}},
            {"id": "manual_safe_publish", "passed": not self.settings.allow_publish},
            {"id": "remote_credentials", "passed": remote_safe},
            {"id": "backup_restore", "passed": bool(restore.get("restored"))},
        ]
        return {
            "passed": all(item["passed"] for item in checks), "checks": checks,
            "secret_hits": secret_hits, "sensitive_files": sensitive_files,
            "vault": vault, "restore": restore,
            "manual_actions": [
                "Revogar o token do Pinterest mostrado em captura de tela e autorizar novamente pelo OAuth oficial."
            ],
            "secrets_returned": False,
        }
