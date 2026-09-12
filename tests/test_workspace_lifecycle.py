import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from factory.workspace_lifecycle import WorkspaceLifecycle, WorkspaceLifecycleError
from factory.workspaces import DEFAULT_WORKSPACE_ID, WorkspaceRegistry


class WorkspaceLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.registry = WorkspaceRegistry(self.base / "data")
        self.alpha = self.registry.provision("client-alpha", "Client Alpha")
        self.beta = self.registry.provision("client-beta", "Client Beta")
        (self.alpha.data_dir / "notes.txt").write_text("alpha only", encoding="utf-8")
        (self.beta.data_dir / "notes.txt").write_text("beta only", encoding="utf-8")
        self.exports = self.base / "exports"
        self.backups = self.base / "backups"
        self.service = WorkspaceLifecycle(self.registry, export_dir=self.exports,
                                          deletion_backup_dir=self.backups, backup_retention=1)

    def test_export_is_scoped_manifested_and_idempotent(self):
        private = self.alpha.data_dir / "private"
        private.mkdir()
        (private / "oauth.key").write_text("must-not-export", encoding="utf-8")
        first = self.service.export_workspace("client-alpha", request_id="case-a")
        again = self.service.export_workspace("client-alpha", request_id="case-a")
        self.assertFalse(first["idempotent"])
        self.assertTrue(again["idempotent"])
        self.assertEqual([item["path"] for item in first["manifest"]["files"]], ["notes.txt", "workspace.json"])
        archive = Path(first["archive"])
        self.assertTrue(archive.is_file())
        with zipfile.ZipFile(archive) as bundle:
            self.assertEqual(bundle.read("notes.txt"), b"alpha only")
            manifest = json.loads(bundle.read("workspace-export-manifest.json"))
            self.assertEqual(manifest["workspace"]["id"], "client-alpha")
            self.assertFalse(manifest["private_credentials_included"])
            self.assertNotIn("private/oauth.key", bundle.namelist())
            self.assertNotIn("must-not-export", str(bundle.namelist()))
            self.assertNotIn("beta only", "\n".join(bundle.namelist()))

    def test_traversal_and_personal_workspace_are_rejected_before_mutation(self):
        for invalid in ("../client-beta", "client/other", "client\\other"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.service.deletion_plan(invalid)
        for action in (
            lambda: self.service.export_workspace(DEFAULT_WORKSPACE_ID),
            lambda: self.service.seed_demo(DEFAULT_WORKSPACE_ID),
            lambda: self.service.delete_workspace(DEFAULT_WORKSPACE_ID, confirmation="DELETE:3am-shelter"),
        ):
            with self.subTest(action=action):
                with self.assertRaises(PermissionError):
                    action()
        self.assertTrue((self.alpha.data_dir / "notes.txt").is_file())
        self.assertFalse(self.exports.exists())

    def test_deletion_plan_is_dry_run_and_requires_exact_confirmation(self):
        plan = self.service.deletion_plan("client-alpha")
        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["confirmation_required"], "DELETE:client-alpha")
        self.assertTrue(self.alpha.data_dir.is_dir())
        self.assertFalse(self.backups.exists())
        with self.assertRaises(PermissionError):
            self.service.delete_workspace("client-alpha", confirmation="DELETE:client-beta")
        self.assertTrue(self.alpha.data_dir.is_dir())

    def test_deletion_creates_verified_backup_and_is_idempotent(self):
        result = self.service.delete_workspace("client-alpha", confirmation="DELETE:client-alpha")
        self.assertFalse(result["already_deleted"])
        self.assertFalse(self.alpha.data_dir.exists())
        backup = Path(result["backup_archive"])
        self.assertTrue(backup.is_file())
        with zipfile.ZipFile(backup) as bundle:
            self.assertEqual(bundle.read("notes.txt"), b"alpha only")
        repeated = self.service.delete_workspace("client-alpha", confirmation="DELETE:client-alpha")
        self.assertTrue(repeated["already_deleted"])
        self.assertTrue(self.beta.data_dir.is_dir())

    def test_deletion_backup_retention_prunes_only_older_backups_for_that_workspace(self):
        first = self.service.delete_workspace("client-alpha", confirmation="DELETE:client-alpha")
        recreated = self.registry.provision("client-alpha", "Client Alpha")
        (recreated.data_dir / "notes.txt").write_text("alpha recreated", encoding="utf-8")
        second = self.service.delete_workspace("client-alpha", confirmation="DELETE:client-alpha")
        kept = list(self.backups.glob("client-alpha-backup-*.zip"))
        self.assertEqual(len(kept), 1)
        # Windows TEMP can use an 8.3 alias for the same existing file.
        self.assertTrue(Path(second["backup_archive"]).samefile(kept[0]))
        self.assertFalse(Path(first["backup_archive"]).exists())
        self.assertTrue(self.beta.data_dir.is_dir())

    def test_failed_delete_rolls_back_root_and_preserves_backup(self):
        with patch("factory.workspace_lifecycle.shutil.rmtree", side_effect=OSError("locked")):
            with self.assertRaises(WorkspaceLifecycleError):
                self.service.delete_workspace("client-alpha", confirmation="DELETE:client-alpha")
        self.assertTrue(self.alpha.data_dir.is_dir())
        self.assertEqual((self.alpha.data_dir / "notes.txt").read_text(encoding="utf-8"), "alpha only")
        self.assertEqual(len(list(self.backups.glob("client-alpha-backup-*.zip"))), 1)

    def test_demo_seed_and_reset_are_scoped_and_preserve_workspace_data(self):
        seeded = self.service.seed_demo("client-alpha")
        self.assertTrue(seeded["seeded"])
        self.assertFalse(seeded["idempotent"])
        self.assertTrue(self.service.seed_demo("client-alpha")["idempotent"])
        self.assertTrue((self.alpha.data_dir / "demo" / "first-project.json").is_file())
        self.assertFalse((self.beta.data_dir / "demo").exists())
        reset = self.service.reset_demo("client-alpha")
        self.assertTrue(reset["reset"])
        self.assertEqual((self.alpha.data_dir / "notes.txt").read_text(encoding="utf-8"), "alpha only")
        self.assertFalse((self.alpha.data_dir / "demo").exists())
        self.assertTrue(self.service.reset_demo("client-alpha")["idempotent"])


if __name__ == "__main__":
    unittest.main()
