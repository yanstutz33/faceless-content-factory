import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from factory.agents import ContentCrew, PROFILES
from factory.config import Settings
from factory.pipeline import Pipeline, safe_slug, srt_timestamp
from factory.store import Store
from factory.web import create_server


ROOT = Path(__file__).parents[1]
FFMPEG = ROOT / ".tools" / "ffmpeg" / "bin" / "ffmpeg.exe"


class CoreTests(unittest.TestCase):
    def settings(self, root: Path) -> Settings:
        return Settings(root, root / "data", str(FFMPEG), "ffprobe", "127.0.0.1", 0, False)

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
                request = urllib.request.Request(base + "/api/jobs", data=b'{"topic":"x"}', headers={"Content-Type": "application/json"}, method="POST")
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request)
                self.assertEqual(error.exception.code, 400)
                error.exception.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
