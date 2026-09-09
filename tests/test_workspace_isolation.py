import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from factory.config import Settings
from factory.integrations import IntegrationManager
from factory.pipeline import Pipeline
from factory.publishing import PublishingCenter
from factory.workspaces import DEFAULT_WORKSPACE_ID, WorkspaceRegistry, normalize_workspace_id


ROOT = Path(__file__).parents[1]


class WorkspaceIsolationTests(unittest.TestCase):
    @staticmethod
    def _job(job_id: str, topic: str, output_dir: Path) -> dict[str, object]:
        return {
            "id": job_id,
            "topic": topic,
            "duration": 1800,
            "narration": False,
            "subtitles": False,
            "output_dir": str(output_dir),
        }

    @staticmethod
    def _settings(root: Path) -> Settings:
        return Settings(root, root / "data", "ffmpeg", "ffprobe", "127.0.0.1", 0, False)

    def test_personal_workspace_preserves_existing_data_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            registry = WorkspaceRegistry(data_dir)
            context = registry.get(DEFAULT_WORKSPACE_ID)
            self.assertTrue(context.personal)
            self.assertEqual(context.data_dir, data_dir.resolve())
            self.assertEqual(context.database_path, data_dir.resolve() / "factory.db")
            self.assertFalse((data_dir / "workspaces").exists())

    def test_lookup_never_provisions_an_unknown_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            registry = WorkspaceRegistry(data_dir)
            with self.assertRaisesRegex(ValueError, "não encontrado"):
                registry.get("client-alpha")
            self.assertFalse((data_dir / "workspaces" / "client-alpha").exists())

    def test_workspace_ids_cannot_escape_the_managed_root(self):
        for value in ("../outside", "client/other", "client\\other", ".", "-client", "client-"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    normalize_workspace_id(value)

    def test_two_workspaces_cannot_read_or_overwrite_each_others_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = WorkspaceRegistry(Path(tmp) / "data")
            alpha = registry.provision("client-alpha", "Client Alpha")
            beta = registry.provision("client-beta", "Client Beta")
            alpha_store = alpha.open_store()
            beta_store = beta.open_store()

            # Identical local identifiers prove that isolation comes from the
            # storage boundary, not from hoping globally generated IDs differ.
            alpha_store.create_job(self._job("same-id", "Alpha only", alpha.jobs_dir / "same-id"))
            beta_store.create_job(self._job("same-id", "Beta only", beta.jobs_dir / "same-id"))

            self.assertEqual(alpha_store.get_job("same-id")["topic"], "Alpha only")
            self.assertEqual(beta_store.get_job("same-id")["topic"], "Beta only")
            alpha_store.update("same-id", "approved", {"owner": "alpha"})
            self.assertEqual(alpha_store.get_job("same-id")["status"], "approved")
            self.assertEqual(beta_store.get_job("same-id")["status"], "queued")
            self.assertNotEqual(alpha.database_path, beta.database_path)
            self.assertTrue(alpha.database_path.is_file())
            self.assertTrue(beta.database_path.is_file())

    def test_all_persistent_application_paths_follow_the_selected_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = WorkspaceRegistry(root / "data")
            context = registry.provision("client-safe", "Client Safe")
            scoped = context.scoped_settings(self._settings(root))
            store = context.open_store()
            pipeline = Pipeline(scoped, store)
            integrations = IntegrationManager(scoped, store, PublishingCenter(pipeline, store))
            self.assertEqual(scoped.data_dir, context.data_dir)
            self.assertEqual(context.jobs_dir.parent, scoped.data_dir)
            self.assertEqual(context.private_dir.parent, scoped.data_dir)
            self.assertEqual(integrations.audit.path, context.audit_path)
            self.assertEqual(integrations.deliveries.path, context.deliveries_path)
            self.assertEqual(integrations.vault.path.parent, context.private_dir)
            self.assertEqual(pipeline.lyria.vault.path.parent, context.private_dir)

    def test_provision_is_idempotent_but_cannot_relabel_a_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = WorkspaceRegistry(Path(tmp) / "data")
            first = registry.provision("client-stable", "Client Stable")
            second = registry.provision("client-stable", "Client Stable")
            self.assertEqual(first, second)
            with self.assertRaisesRegex(ValueError, "outro nome"):
                registry.provision("client-stable", "Different Client")

    def test_cli_provisions_and_selects_an_isolated_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["FACTORY_DATA_DIR"] = str(Path(tmp) / "data")
            created = subprocess.run(
                [sys.executable, str(ROOT / "app.py"), "workspace-create", "client-cli", "--name", "Client CLI"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            selected = subprocess.run(
                [sys.executable, str(ROOT / "app.py"), "--workspace", "client-cli", "list"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(json.loads(created.stdout)["id"], "client-cli")
            self.assertEqual(json.loads(selected.stdout), [])


if __name__ == "__main__":
    unittest.main()
