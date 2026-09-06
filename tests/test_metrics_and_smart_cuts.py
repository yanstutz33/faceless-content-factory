import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from factory.config import Settings
from factory.integrations import IntegrationManager
from factory.pipeline import Pipeline
from factory.publishing import PublishingCenter
from factory.store import Store


class MetricsAndSmartCutsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.settings = Settings(self.root, self.root / "data", "ffmpeg", "ffprobe", "127.0.0.1", 0, False)
        self.store = Store(self.root / "data" / "factory.db")
        self.pipeline = Pipeline(self.settings, self.store)

    def approved_job(self):
        job_id = self.pipeline.create("Rainy city at 3 A.M.", 1800)
        out = Path(self.store.get_job(job_id)["output_dir"])
        (out / "video.mp4").write_bytes(b"immutable-source-video")
        metadata = {
            "title": "Go to Sleep, It's 3 A.M.",
            "quality_gate": {"passed": True},
            "chapters": [{"time": "00:00:00", "label": "Arrival"},
                         {"time": "00:10:00", "label": "Quiet"},
                         {"time": "00:20:00", "label": "Rest"}],
        }
        self.store.update(job_id, "approved", metadata, progress=100)
        (out / "artifact-manifest.json").write_text(
            json.dumps(self.pipeline.artifact_manifest(out, ["video.mp4"])), encoding="utf-8")
        return job_id, out

    def test_provider_metrics_snapshot_is_idempotent_and_preserves_manual_history(self):
        job_id, _ = self.approved_job()
        self.store.add_metrics(job_id, "youtube", 1, 0, 1)
        first = self.store.upsert_metrics_snapshot(
            job_id, "youtube", views=10, likes=2, watch_minutes=7, source="youtube_api",
            external_id="video-1", snapshot_date="2026-09-05")
        second = self.store.upsert_metrics_snapshot(
            job_id, "youtube", views=12, likes=3, watch_minutes=8, source="youtube_api",
            external_id="video-1", snapshot_date="2026-09-05")
        self.assertEqual((first, second), ("inserted", "updated"))
        rows = self.store.get_job(job_id)["metrics"]
        self.assertEqual(len(rows), 2)
        automatic = next(row for row in rows if row["source"] == "youtube_api")
        self.assertEqual(automatic["views"], 12)
        self.assertEqual(self.store.metrics_sync_status()["jobs"], 1)

    def test_disabled_youtube_analytics_api_has_an_actionable_error(self):
        body = json.dumps({"error": {"message": "disabled", "errors": [
            {"reason": "accessNotConfigured"}], "details": []}}).encode()
        error = HTTPError("https://youtubeanalytics.googleapis.com/v2/reports", 403,
                          "Forbidden", {}, BytesIO(body))
        manager = IntegrationManager(self.settings, self.store, PublishingCenter(self.pipeline, self.store))
        try:
            with patch("factory.integrations.urlopen", side_effect=error):
                with self.assertRaisesRegex(ValueError, "Analytics API está desativada"):
                    manager._authorized_json("https://youtubeanalytics.googleapis.com/v2/reports", "token")
        finally:
            error.close()

    def test_disabled_youtube_reporting_api_has_an_actionable_error(self):
        body = json.dumps({"error": {"message": "disabled", "errors": [
            {"reason": "accessNotConfigured"}], "details": [{"metadata": {
                "service": "youtubereporting.googleapis.com"}}]}}).encode()
        error = HTTPError("https://youtubereporting.googleapis.com/v1/reportTypes", 403,
                          "Forbidden", {}, BytesIO(body))
        manager = IntegrationManager(self.settings, self.store, PublishingCenter(self.pipeline, self.store))
        try:
            with patch("factory.integrations.urlopen", side_effect=error):
                with self.assertRaisesRegex(ValueError, "Reporting API está desativada"):
                    manager._authorized_json("https://youtubereporting.googleapis.com/v1/reportTypes", "token")
        finally:
            error.close()

    def test_youtube_sync_imports_read_only_metrics_for_audited_delivery(self):
        job_id, _ = self.approved_job()
        manager = IntegrationManager(self.settings, self.store, PublishingCenter(self.pipeline, self.store))
        manager.deliveries.stage(job_id, "youtube", "uploaded_public", [])
        manager.audit.record("visibility_confirmed_public", "youtube", {"job_id": job_id, "video_id": "video-1"})
        data_api = {"items": [{"id": "video-1", "statistics": {"viewCount": "20", "likeCount": "4"}}]}
        core = {
            "columnHeaders": [{"name": name} for name in
                              ("views", "estimatedMinutesWatched", "averageViewDuration",
                               "averageViewPercentage", "likes", "comments", "shares")],
            "rows": [[18, 54, 180, 10, 4, 1, 2]],
        }
        def response(url, _token):
            if "youtube/v3/videos" in url:
                return data_api
            return core

        with patch.object(manager, "_youtube_access_token", return_value="token"), \
                patch.object(manager, "_authorized_json", side_effect=response), \
                patch.object(manager, "sync_youtube_reach", return_value={"status": "waiting_for_first_report"}):
            result = manager.sync_youtube_metrics()
        self.assertEqual(result["count"], 1)
        self.assertFalse(result["upload_performed"])
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["reach"]["status"], "waiting_for_first_report")
        row = self.store.get_job(job_id)["metrics"][0]
        self.assertEqual((row["views"], row["impressions"], row["clicks"]), (18, 0, 0))
        self.assertEqual(row["average_view_percentage"], 10)
        self.assertEqual(row["source"], "youtube_api")

    def test_reach_setup_reuses_existing_job(self):
        manager = IntegrationManager(self.settings, self.store, PublishingCenter(self.pipeline, self.store))
        existing = {"id": "reach-job", "name": "FFactory Daily Reach",
                    "reportTypeId": "channel_reach_basic_a1", "createTime": "2026-09-06T00:00:00Z"}
        with patch.object(manager, "_youtube_access_token", return_value="token"), \
                patch.object(manager, "_authorized_json", return_value={"jobs": [existing]}) as request:
            result = manager.ensure_youtube_reach_reporting(True)
        self.assertFalse(result["created"])
        self.assertEqual(result["id"], "reach-job")
        self.assertEqual(request.call_count, 1)

    def test_reach_report_merges_without_erasing_watch_metrics(self):
        job_id, _ = self.approved_job()
        manager = IntegrationManager(self.settings, self.store, PublishingCenter(self.pipeline, self.store))
        manager.deliveries.stage(job_id, "youtube", "uploaded_public", [])
        manager.audit.record("visibility_confirmed_public", "youtube", {"job_id": job_id, "video_id": "video-1"})
        manager.vault.set("youtube:reach_job", {"id": "reach-job"})
        self.store.upsert_metrics_snapshot(
            job_id, "youtube", views=30, watch_minutes=60, source="youtube_api",
            external_id="video-1", snapshot_date="2026-09-05",
        )
        reports = {"reports": [{"id": "report-1", "createTime": "2026-09-06T12:00:00Z",
                                "downloadUrl": "https://youtubereporting.googleapis.com/v1/media/report-1"}]}
        csv_body = ("date,channel_id,video_id,video_thumbnail_impressions,video_thumbnail_impressions_ctr\n"
                    "2026-09-05,channel,video-1,200,4.5\n").encode()
        with patch.object(manager, "_authorized_json", return_value=reports), \
                patch.object(manager, "_authorized_bytes", return_value=csv_body):
            result = manager.sync_youtube_reach("token")
        self.assertEqual(result["rows"], 1)
        row = self.store.get_job(job_id)["metrics"][0]
        self.assertEqual((row["views"], row["watch_minutes"], row["impressions"], row["clicks"]),
                         (30, 60, 200, 9))

    def test_smart_cuts_keep_source_immutable_and_create_traceable_candidates(self):
        job_id, out = self.approved_job()
        source_before = (out / "video.mp4").read_bytes()

        def render(args):
            Path(args[-1]).write_bytes(b"rendered")

        def inspect(_path, expected):
            return {"passed": True, "duration_seconds": expected,
                    "video": {"width": 1080, "height": 1920}, "audio": {"codec": "aac"}}

        with patch.object(self.pipeline, "command", side_effect=render), \
                patch.object(self.pipeline, "inspect_video", side_effect=inspect):
            package = self.pipeline.prepare_smart_cuts(job_id, [15, 30, 60])
        self.assertEqual((out / "video.mp4").read_bytes(), source_before)
        self.assertEqual(len(package["candidates"]), 3)
        self.assertEqual([item["source_start_seconds"] for item in package["candidates"]], [0, 600, 1200])
        self.assertTrue(package["quality_gate"]["passed"])
        self.assertTrue(package["quality_gate"]["source_immutable"])
        manifest = json.loads((out / "smart-cuts" / "artifact-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(package["source_sha256"], package["source_sha256_after"])
        self.assertTrue(package["quality_gate"]["source_immutable"])
        self.assertEqual(len(manifest["files"]), 7)
        self.assertFalse(package["automatic_upload_allowed"])


if __name__ == "__main__":
    unittest.main()
