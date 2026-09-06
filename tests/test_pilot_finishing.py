import json
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

from factory.agents import align_title_to_scene
from factory.config import Settings
from factory.pipeline import Pipeline
from scripts.align_release_metadata import align


class PilotFinishingTests(unittest.TestCase):
    def test_replaced_scene_preserves_phrase_and_removes_wrong_subject(self):
        self.assertEqual(
            align_title_to_scene("The World Can Wait. | Deep Space Lo-fi", "rainy-window-memories"),
            "The World Can Wait. | Rainy Night Lo-fi",
        )
        self.assertEqual(align_title_to_scene("Existing title", "custom-source"), "Existing title")

    def test_short_audio_does_not_shorten_requested_video(self):
        root = Path(__file__).resolve().parents[1]
        settings = Settings.load(root)
        if not shutil.which(settings.ffmpeg) or not shutil.which(settings.ffprobe):
            self.skipTest("FFmpeg unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            loop, audio, output = (directory / name for name in ("loop.mp4", "audio.wav", "out.mp4"))
            pipeline = Pipeline.__new__(Pipeline)
            pipeline.settings = settings
            pipeline.command([settings.ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=30",
                              "-t", "1", "-c:v", "libx264", str(loop)])
            pipeline.command([settings.ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=1.75", str(audio)])
            pipeline.repeat_visual_loop(loop, audio, output, 2)
            result = subprocess.run([settings.ffprobe, "-v", "error", "-show_entries", "format=duration",
                                     "-of", "json", str(output)], capture_output=True, text=True, check=True)
            duration = float(json.loads(result.stdout)["format"]["duration"])
            self.assertGreaterEqual(duration, 2)
            self.assertLess(duration, 2.15)

    def test_metadata_alignment_preserves_video_approval_and_recoverable_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "jobs" / "pilot"
            out.mkdir(parents=True)
            metadata = {"title": "Rest Tonight. | Deep Space Lo-fi", "visual_source": {"reference_id": "rainy-window-memories"}}
            metadata["verification"] = {"passed": True, "video": {"width": 1920, "height": 1080}}
            (out / "publication-package.json").write_text('{"media_validation": {"video": {"width": 1280}}}', encoding="utf-8")
            (out / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            original = (out / "metadata.json").read_bytes()
            (out / "video.mp4").write_bytes(b"unchanged-video")
            manifest = Pipeline.artifact_manifest(out, ["metadata.json", "video.mp4", "publication-package.json"])
            (out / "artifact-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            pipeline = Pipeline.__new__(Pipeline)
            pipeline.settings = Mock(data_dir=root, ffprobe="unused")
            pipeline.store = Mock()
            pipeline.store.get_job.return_value = {"id": "pilot", "output_dir": str(out), "status": "approved", "duration": 1800}
            probe = Mock(stdout=json.dumps({"streams": [{"width": 1920, "height": 1080, "r_frame_rate": "30/1"}]}))
            with patch("scripts.align_release_metadata.subprocess.run", return_value=probe):
                result = align(pipeline, "pilot")
            self.assertEqual((out / "video.mp4").read_bytes(), b"unchanged-video")
            self.assertEqual((Path(result["backup"]) / "metadata.json").read_bytes(), original)
            self.assertEqual(result["title"], "Rest Tonight. | Rainy Night Lo-fi")
            self.assertEqual(result["production"]["resolution"], "1920x1080")
            self.assertEqual(json.loads((out / "publication-package.json").read_text(encoding="utf-8"))["media_validation"], metadata["verification"])
            pipeline.store.update.assert_called_once()
            self.assertEqual(pipeline.store.update.call_args.args[1], "approved")
            self.assertTrue(Pipeline.verify_artifact_manifest(out)["passed"])
