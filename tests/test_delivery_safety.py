import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from factory.config import Settings
from factory.integrations import DeliveryLedger, IntegrationAudit, IntegrationManager
from factory.publishing import PublishingCenter
from factory.store import Store


UPLOADED_STATES = (
    "uploaded_verification_pending", "uploaded_private", "uploaded_public", "uploaded_unlisted",
)


class DeliverySafetyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        settings = Settings(self.root, self.root / "state", "ffmpeg", "ffprobe", "127.0.0.1", 0, False)
        self.store = Mock(spec=Store)
        self.publishing = Mock(spec=PublishingCenter)
        self.publishing.queue.return_value = {"items": [{"job_id": "pilot", "release_ready": True}]}
        self.publishing.audit.return_value = {"release_ready": True, "blockers": []}
        self.manager = IntegrationManager(settings, self.store, self.publishing)
        self.manager.audit = Mock(spec=IntegrationAudit)
        self.manager.vault = Mock(available=True)
        self.manager.vault.contains.return_value = True
        self.manager.vault.get.return_value = {"access_token": "test-access-token"}
        self.enterContext(patch.object(self.manager, "_config", return_value={"client_id": "test", "client_secret": "test"}))
        self.network = self.enterContext(patch("factory.integrations.urlopen", side_effect=AssertionError("Unexpected network request")))
        self.token = self.enterContext(patch.object(self.manager, "_youtube_access_token", return_value="test-access-token"))

    def prepare_release(self):
        output = self.root / "release"
        output.mkdir()
        (output / "video.mp4").write_bytes(b"test-video")
        (output / "youtube-upload.json").write_text(json.dumps({
            "snippet": {"title": "Test pilot"}, "status": {"privacyStatus": "private"},
        }), encoding="utf-8")
        job = {"id": "pilot", "output_dir": str(output)}
        self.store.get_job.return_value = job
        return job

    def test_preflight_preserves_uploaded_delivery_even_when_readiness_changes(self):
        for uploaded in UPLOADED_STATES:
            for authenticated, release_ready in ((True, True), (False, True), (True, False)):
                with self.subTest(status=uploaded, authenticated=authenticated, release_ready=release_ready):
                    original = self.manager.deliveries.stage("pilot", "youtube", uploaded, [])
                    original_file = self.manager.deliveries.path.read_bytes()
                    self.manager.vault.contains.return_value = authenticated
                    self.manager.vault.get.return_value = {"access_token": "test-access-token"} if authenticated else None
                    self.publishing.queue.return_value["items"][0]["release_ready"] = release_ready

                    result = self.manager.preflight("youtube", "pilot")

                    self.assertEqual(result["delivery"], original)
                    self.assertEqual(self.manager.deliveries.path.read_bytes(), original_file)
                    self.assertFalse(result["upload_performed"])
                    self.assertFalse(result["network_contacted"])
                    with self.assertRaisesRegex(ValueError, "upload duplicado"):
                        self.manager.youtube_upload_private("pilot", confirmed=True)
        self.network.assert_not_called()
        self.token.assert_not_called()
        self.publishing.audit.assert_not_called()

    def test_duplicate_upload_is_rejected_before_credentials_or_preflight(self):
        with patch.object(self.manager, "preflight") as preflight:
            for uploaded in UPLOADED_STATES:
                with self.subTest(status=uploaded):
                    original = self.manager.deliveries.stage("pilot", "youtube", uploaded, [])

                    with self.assertRaisesRegex(ValueError, "upload duplicado"):
                        self.manager.youtube_upload_private("pilot", confirmed=True)

                    self.assertEqual(self.manager.deliveries.list(), [original])
            preflight.assert_not_called()
        self.network.assert_not_called()
        self.token.assert_not_called()

    def test_stage_allows_readiness_and_remote_status_progression(self):
        ledger = DeliveryLedger(self.root / "progression.json")
        original = ledger.stage("pilot", "youtube", "blocked_auth", ["Login required"])
        for status in ("manual_approval", *UPLOADED_STATES):
            with self.subTest(status=status):
                row = ledger.stage("pilot", "youtube", status, [])
                self.assertEqual(row["id"], original["id"])
                self.assertEqual(row["created_at"], original["created_at"])
                self.assertEqual(row["status"], status)
                self.assertEqual(row["blockers"], [])
                self.assertEqual(ledger.list(), [row])

    def test_other_job_or_platform_upload_does_not_block_new_private_upload(self):
        self.manager.deliveries.stage("other-pilot", "youtube", "uploaded_public", [])
        self.manager.deliveries.stage("pilot", "reels", "uploaded_public", [])
        job = self.prepare_release()
        initiate_response = Mock()
        initiate_response.headers = {"Location": "https://upload.example.test/session"}
        upload_response = Mock()
        upload_response.read.return_value = json.dumps({
            "id": "test-video-id", "status": {"privacyStatus": "private"},
        }).encode("utf-8")

        def response_for(request, **kwargs):
            response = initiate_response if request.method == "POST" else upload_response
            context = Mock()
            context.__enter__ = Mock(return_value=response)
            context.__exit__ = Mock(return_value=False)
            return context

        self.network.side_effect = response_for
        result = self.manager.youtube_upload_private("pilot", confirmed=True)

        self.assertEqual(result["delivery"]["status"], "uploaded_private")
        self.assertEqual(result["video_id"], "test-video-id")
        self.assertTrue(result["upload_performed"])
        self.assertEqual(self.network.call_count, 2)
        self.token.assert_called_once_with()
        self.publishing.audit.assert_called_once_with(job, refresh_integrity=True)
        self.assertEqual({(row["job_id"], row["platform"]): row["status"]
                          for row in self.manager.deliveries.list()}, {
            ("other-pilot", "youtube"): "uploaded_public",
            ("pilot", "reels"): "uploaded_public",
            ("pilot", "youtube"): "uploaded_private",
        })
        with self.assertRaisesRegex(ValueError, "upload duplicado"):
            self.manager.youtube_upload_private("pilot", confirmed=True)
        self.assertEqual(self.network.call_count, 2)

    def test_final_integrity_failure_blocks_upload_despite_ready_queue(self):
        job = self.prepare_release()
        self.publishing.audit.return_value = {
            "release_ready": False, "blockers": ["Video changed after approval"],
        }

        with self.assertRaisesRegex(ValueError, "Video changed after approval"):
            self.manager.youtube_upload_private("pilot", confirmed=True)

        self.publishing.audit.assert_called_once_with(job, refresh_integrity=True)
        self.token.assert_not_called()
        self.network.assert_not_called()
        self.assertEqual(self.manager.deliveries.list()[0]["status"], "manual_approval")


if __name__ == "__main__":
    unittest.main()
