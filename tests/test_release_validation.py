import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory.config import Settings
from factory.pipeline import Pipeline
from factory.publishing import PublishingCenter
from factory.store import Store


class ReleaseValidationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.store = Store(root / "factory.db")
        settings = Settings(root, root / "data", "unused-ffmpeg", "unused-ffprobe", "127.0.0.1", 0, False)
        self.pipeline = Pipeline(settings, self.store)
        self.job_id = self.pipeline.create("Rainy night release", 1800)
        self.out = Path(self.store.get_job(self.job_id)["output_dir"])
        track_id = self.store.add_music_asset("Reviewed track", str(root / "track.wav"), "original", None, None, True)
        self.store.review_music_asset(track_id, "approved")
        metadata = {
            "title": "Rainy night", "verification": {"passed": True},
            "quality_gate": {"passed": True, "score": 100},
            "music": {"track_id": track_id, "track_name": "Reviewed track", "style": "licensed_music_library"},
        }
        self.store.update(self.job_id, "approved", metadata, progress=100)
        for name in PublishingCenter.SOURCE_ARTIFACTS + PublishingCenter.AUXILIARY_ARTIFACTS:
            (self.out / name).write_bytes(b"{}")
        (self.out / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        (self.out / "asset-manifest.json").write_text(json.dumps([
            {"approved": True, "license_type": "provider_generated", "name": "Original image"},
        ]), encoding="utf-8")
        (self.out / "custom-review.json").write_text('{"reviewed": true}', encoding="utf-8")
        # Older packagers omit existing evidence; final preparation must both
        # restore this coverage and preserve unfamiliar registered artifacts.
        self._write_manifest(["video.mp4", "metadata.json", "custom-review.json"])
        self.center = PublishingCenter(self.pipeline, self.store)

    def _write_manifest(self, names):
        manifest = self.pipeline.artifact_manifest(self.out, names)
        (self.out / "artifact-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def _manifest(self):
        return json.loads((self.out / "artifact-manifest.json").read_text(encoding="utf-8"))

    def _audit(self, **kwargs):
        return self.center.audit(self.store.get_job(self.job_id), **kwargs)

    def _prepare(self):
        def render(args):
            Path(args[-1]).write_bytes(b"rendered-local-media" * 100)

        report = {"passed": True, "video": {"width": 720, "height": 1280}}
        with patch.object(self.pipeline, "command", side_effect=render), \
                patch.object(self.pipeline, "inspect_video", return_value=report):
            return self.center.prepare(self.job_id, 5)

    def test_fresh_preparation_preserves_complete_manifest_without_self_hash(self):
        before = self._audit()
        self.assertTrue(before["eligible"])
        self.assertFalse(before["release_ready"])
        self.assertTrue(before["blockers"])
        self.assertEqual(before["eligibility_blockers"], [])
        release = self._prepare()
        expected = set(PublishingCenter.SOURCE_ARTIFACTS + PublishingCenter.AUXILIARY_ARTIFACTS)
        expected.update(release["files"])
        expected.update(("custom-review.json", "release-manifest.json"))
        names = [item["name"] for item in self._manifest()["files"]]
        self.assertEqual(set(names), expected)
        self.assertEqual(len(names), len(set(names)))
        self.assertNotIn("artifact-manifest.json", names)
        self.assertEqual(self.pipeline.verify_artifact_manifest(self.out)["count"], len(expected))
        self.assertTrue(release["audit"]["release_ready"])
        self.assertTrue(self._audit()["release_ready"])
        persisted = json.loads((self.out / "release-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(persisted, release)

    def test_changes_to_source_evidence_and_derivatives_invalidate_cached_readiness(self):
        self._prepare()
        self.assertTrue(self._audit()["release_ready"])
        for name in ("video.mp4", "metadata.json", "quality-gate.json", "asset-manifest.json",
                     "vertical-short.mp4", "custom-review.json"):
            with self.subTest(name=name):
                path = self.out / name
                original = path.read_bytes()
                path.write_bytes(original + b"\n")
                audit = self._audit()
                self.assertFalse(audit["release_ready"])
                self.assertTrue(any(name in blocker for blocker in audit["blockers"]))
                path.write_bytes(original)

    def test_regenerated_source_hash_does_not_certify_old_derivatives(self):
        self._prepare()
        (self.out / "video.mp4").write_bytes(b"new-visual-source")
        self._write_manifest([item["name"] for item in self._manifest()["files"]])
        self.assertTrue(self.pipeline.verify_artifact_manifest(self.out)["passed"])
        audit = self._audit()
        self.assertTrue(audit["eligible"])
        self.assertFalse(audit["release_ready"])
        self.assertTrue(any("desatualizado" in item and "video.mp4" in item for item in audit["blockers"]))
        self.assertTrue(self._prepare()["audit"]["release_ready"])

    def test_missing_registration_is_actionable_even_when_remaining_hashes_match(self):
        self._prepare()
        self._write_manifest([item["name"] for item in self._manifest()["files"]
                              if item["name"] != "quality-gate.json"])
        self.assertTrue(self.pipeline.verify_artifact_manifest(self.out)["passed"])
        audit = self._audit()
        self.assertFalse(audit["release_ready"])
        self.assertTrue(any("sem integridade registrada" in item and "quality-gate.json" in item
                            for item in audit["blockers"]))

    def test_missing_package_file_has_named_blocker(self):
        self._prepare()
        (self.out / "vertical-thumbnail.jpg").unlink()
        audit = self._audit()
        self.assertFalse(audit["release_ready"])
        self.assertFalse(audit["packages"]["vertical_manual"])
        self.assertTrue(any("vertical-thumbnail.jpg" in item for item in audit["blockers"]))

    def test_legacy_release_without_source_version_requires_preparation(self):
        self._prepare()
        path = self.out / "release-manifest.json"
        release = json.loads(path.read_text(encoding="utf-8"))
        release.pop("source_artifacts")
        path.write_text(json.dumps(release), encoding="utf-8")
        self._write_manifest([item["name"] for item in self._manifest()["files"]])
        audit = self._audit()
        self.assertFalse(audit["release_ready"])
        self.assertTrue(any("vincular os derivados" in item for item in audit["blockers"]))

    def test_dashboard_reuses_validation_and_final_refresh_rehashes(self):
        self._prepare()
        with patch.object(self.pipeline, "verify_artifact_manifest",
                          wraps=self.pipeline.verify_artifact_manifest) as verify:
            self.assertTrue(self._audit()["release_ready"])
            self.assertTrue(self._audit()["release_ready"])
            self.assertEqual(verify.call_count, 1)
            self.assertTrue(self._audit(refresh_integrity=True)["release_ready"])
            self.assertEqual(verify.call_count, 2)

    def test_editorial_certification_does_not_rehash_release_media(self):
        with patch.object(self.center, "_release_checks", side_effect=AssertionError("Unexpected media rehash")):
            self.center.pilot_certification()
            audit = self.center.audit(self.store.get_job(self.job_id), check_release=False)
        self.assertTrue(audit["eligible"])
        self.assertFalse(audit["release_ready"])

    def test_malformed_manifest_and_self_hash_block_readiness(self):
        self._prepare()
        path = self.out / "artifact-manifest.json"
        for manifest in ([], {"files": [None]}, {"files": [{"name": "artifact-manifest.json"}]}):
            with self.subTest(manifest=manifest):
                path.write_text(json.dumps(manifest), encoding="utf-8")
                audit = self._audit()
                self.assertFalse(audit["release_ready"])
                self.assertTrue(audit["blockers"])


if __name__ == "__main__":
    unittest.main()
