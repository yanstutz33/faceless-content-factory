import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from factory.agents import ContentCrew, PROFILES
from factory.config import Settings
from factory.pipeline import Pipeline, safe_slug, srt_timestamp
from factory.store import Store
from factory.web import create_server


ROOT = Path(__file__).parents[1]
LOCAL_FFMPEG = ROOT / ".tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
FFMPEG = LOCAL_FFMPEG if LOCAL_FFMPEG.exists() else Path(shutil.which("ffmpeg") or LOCAL_FFMPEG)
LOCAL_FFPROBE = ROOT / ".tools" / "ffmpeg" / "bin" / "ffprobe.exe"
FFPROBE = LOCAL_FFPROBE if LOCAL_FFPROBE.exists() else Path(shutil.which("ffprobe") or LOCAL_FFPROBE)


class CoreTests(unittest.TestCase):
    def settings(self, root: Path) -> Settings:
        return Settings(root, root / "data", str(FFMPEG), str(FFPROBE), "127.0.0.1", 0, False)

    def test_helpers_preserve_accents_in_slug(self):
        self.assertEqual(safe_slug("Chuva & Café"), "chuva-cafe")
        self.assertEqual(srt_timestamp(65.25), "00:01:05,250")

    def test_agent_crew_delivers_auditable_plan(self):
        plan = ContentCrew().run("Biblioteca chuvosa", 1800, "youtube_long", False)
        required = {"research", "strategy", "script", "visual", "seo", "compliance", "review", "production"}
        self.assertTrue(required.issubset(plan))
        self.assertGreaterEqual(plan["review"]["score"], 80)
        self.assertIn("Biblioteca", plan["seo"]["title"])
        self.assertEqual(plan["compliance"]["publish_mode"], "manual_safe")
        self.assertEqual(plan["visual"]["sound_profile"], "rain")
        self.assertGreaterEqual(len(ContentCrew().ideas()), 5)

    def test_editorial_calendar(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "factory.db")
            item_id = store.add_calendar_item("Rainy cafe", "rainy_places", "youtube_long", 1800, "2026-09-01T19:00")
            self.assertGreater(item_id, 0)
            self.assertEqual(store.list_calendar()[0]["status"], "planned")
            store.link_calendar_job(item_id, "job-123")
            self.assertEqual(store.list_calendar()[0]["job_id"], "job-123")

    def test_asset_catalog_requires_traceable_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "owned.jpg"
            image.write_bytes(b"placeholder")
            store = Store(root / "factory.db")
            asset_id = store.add_asset("Owned scene", str(image), "original", None, "Created in-house", True)
            self.assertGreater(asset_id, 0)
            self.assertTrue(store.list_assets(approved_only=True)[0]["approved"])

    def test_queue_profile_summary_and_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            job_id = pipeline.create("Night rain", 15, profile="preview", priority=3)
            job = store.get_job(job_id)
            self.assertEqual(job["status"], "queued")
            self.assertEqual(job["profile"], "preview")
            self.assertEqual(store.summary()["in_progress"], 1)
            self.assertIn("Night rain", pipeline.generate_plan("Night rain", 15, "preview")["seo"]["title"])

    def test_interrupted_jobs_are_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            job_id = pipeline.create("Recover this render", 5, profile="preview")
            store.update(job_id, "rendering", progress=62)
            self.assertEqual(store.recover_interrupted(), [job_id])
            job = store.get_job(job_id)
            self.assertEqual(job["status"], "queued")
            self.assertEqual(job["progress"], 0)
            self.assertEqual(job["events"][-1]["stage"], "recovery")

    def test_metrics_summary_uses_latest_snapshot_per_platform(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            job_id = pipeline.create("Metrics snapshot", 5, profile="preview")
            store.add_metrics(job_id, "youtube", 100, 10, 20)
            store.add_metrics(job_id, "youtube", 175, 14, 31)
            store.add_metrics(job_id, "tiktok", 50, 7, 8)
            summary = store.summary()
            self.assertEqual(summary["views"], 225)
            self.assertEqual(summary["likes"], 21)
            self.assertEqual(summary["watch_minutes"], 39)

    def test_profile_duration_is_safely_capped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            job_id = pipeline.create("Vertical rain", 9999, profile="vertical_short")
            self.assertEqual(store.get_job(job_id)["duration"], PROFILES["vertical_short"]["max_duration"])

    @unittest.skipUnless(FFMPEG.exists(), "FFmpeg portátil não encontrado")
    def test_preview_render_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            job_id = pipeline.create("Render smoke test", 5, profile="preview")
            job = pipeline.run(job_id)
            self.assertEqual(job["status"], "awaiting_approval")
            self.assertEqual(job["progress"], 100)
            self.assertTrue((Path(job["output_dir"]) / "video.mp4").exists())
            self.assertTrue((Path(job["output_dir"]) / "agents.json").exists())
            self.assertTrue((Path(job["output_dir"]) / "thumbnail-design.json").exists())
            report = json.loads((Path(job["output_dir"]) / "render-report.json").read_text(encoding="utf-8"))
            manifest = json.loads((Path(job["output_dir"]) / "artifact-manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(report["passed"])
            self.assertTrue(report["video"]["codec"])
            self.assertTrue(report["audio"]["codec"])
            self.assertIn("video.mp4", {item["name"] for item in manifest["files"]})

    @unittest.skipUnless(FFMPEG.exists(), "FFmpeg portátil não encontrado")
    def test_theme_sound_profiles_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            for profile in ("rain", "cozy", "cosmic", "focus"):
                output = root / f"{profile}.wav"
                pipeline.create_ambient_audio(output, 2, profile)
                self.assertTrue(output.is_file())
                self.assertGreater(output.stat().st_size, 10_000)

    @unittest.skipUnless(FFMPEG.exists(), "FFmpeg portátil não encontrado")
    def test_narration_failure_falls_back_to_ambient(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            job_id = pipeline.create("Narration graceful fallback", 5, narration=True, profile="preview")
            with patch.object(pipeline, "synthesize_narration", side_effect=RuntimeError("offline")):
                job = pipeline.run(job_id)
            self.assertEqual(job["status"], "awaiting_approval")
            self.assertEqual(job["metadata"]["narration_status"], "ambient_fallback")
            self.assertTrue(any("voz neural" in warning.lower() for warning in job["metadata"]["quality"]["warnings"]))

    @unittest.skipUnless(FFMPEG.exists(), "FFmpeg portátil não encontrado")
    def test_multiscene_render_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            scenes = []
            for index, color in enumerate(("#102030", "#304050")):
                path = root / f"scene-{index}.jpg"
                pipeline.command([str(FFMPEG), "-y", "-f", "lavfi", "-i", f"color=c={color}:s=960x540", "-frames:v", "1", str(path)])
                scenes.append({"name": f"Scene {index}", "path": str(path), "license_type": "original", "approved": True})
            job_id = pipeline.create("Two scene test", 6, profile="preview", source_assets=scenes)
            job = pipeline.run(job_id)
            output = Path(job["output_dir"])
            self.assertEqual(job["status"], "awaiting_approval")
            self.assertTrue((output / "asset-manifest.json").exists())
            self.assertEqual(len(json.loads((output / "asset-manifest.json").read_text(encoding="utf-8"))), 2)

    def test_dashboard_api_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            server = create_server(pipeline, store, "127.0.0.1", 0, ROOT / "web")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                dashboard = json.load(urllib.request.urlopen(base + "/api/dashboard"))
                self.assertEqual(dashboard["summary"]["total"], 0)
                self.assertTrue(dashboard["operation"]["ok"])
                series = json.load(urllib.request.urlopen(base + "/api/series"))
                self.assertGreaterEqual(len(series), 4)
                request = urllib.request.Request(base + "/api/jobs", data=b'{"topic":"x"}', headers={"Content-Type": "application/json"}, method="POST")
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request)
                self.assertEqual(error.exception.code, 400)
                error.exception.close()
                with self.assertRaises(urllib.error.HTTPError) as traversal:
                    urllib.request.urlopen(base + "/%2e%2e/.env.example")
                self.assertEqual(traversal.exception.code, 404)
                traversal.exception.close()
            finally:
                server.shutdown()
                server.server_close()

    def test_artifact_endpoint_supports_byte_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            job_id = pipeline.create("Range streaming", 5, profile="preview")
            job = store.get_job(job_id)
            store.update(job_id, "failed", error="fixture")
            video = Path(job["output_dir"]) / "video.mp4"
            video.write_bytes(b"0123456789")
            server = create_server(pipeline, store, "127.0.0.1", 0, ROOT / "web")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                request = urllib.request.Request(
                    base + f"/api/jobs/{job_id}/artifacts/video.mp4",
                    headers={"Range": "bytes=2-5"},
                )
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(response.status, 206)
                    self.assertEqual(response.headers["Content-Range"], "bytes 2-5/10")
                    self.assertEqual(response.read(), b"2345")
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
