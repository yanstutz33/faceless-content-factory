"""Align explicit local releases with their encoded scene; never uploads.

Run as a module: python -m scripts.align_release_metadata JOB_ID [...]
Existing metadata and its manifest are backed up before any changes.
Reprepare the release afterwards: derivatives deliberately become stale.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path

from factory.agents import align_title_to_scene
from factory.config import Settings
from factory.pipeline import Pipeline
from factory.store import Store


def align(pipeline: Pipeline, job_id: str) -> dict:
    job = pipeline.store.get_job(job_id)
    if not job:
        raise ValueError("Produção não encontrada")
    out = Path(job["output_dir"])
    pipeline.verify_artifact_manifest(out)
    metadata = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    reference = (metadata.get("visual_source") or {}).get("reference_id")
    if not reference:
        raise ValueError("Produção sem cena codificada rastreável")
    result = subprocess.run([
        pipeline.settings.ffprobe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate", "-of", "json", str(out / "video.mp4"),
    ], check=True, capture_output=True, text=True)
    video = json.loads(result.stdout)["streams"][0]
    metadata["title"] = align_title_to_scene(metadata["title"], reference)
    metadata.setdefault("production", {}).update({
        "resolution": f"{video['width']}x{video['height']}",
        "fps": float(Fraction(video["r_frame_rate"])), "duration_seconds": job["duration"],
    })
    agents = metadata.setdefault("agents", {})
    agents.setdefault("seo", {})["title"] = metadata["title"]
    agents["production"] = dict(metadata["production"])
    names = [item["name"] for item in json.loads((out / "artifact-manifest.json").read_text(encoding="utf-8"))["files"]]
    names = list(dict.fromkeys(names + ["metadata.json", "agents.json"]))
    checklist = None
    if (out / "publication-package.json").is_file():
        checklist = json.loads((out / "publication-package.json").read_text(encoding="utf-8"))
        checklist["media_validation"] = metadata.get("verification", {})
        checklist["quality_gate"] = metadata.get("quality_gate", {})
    archive = pipeline.settings.data_dir / "archive" / "metadata-alignment" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") / job_id
    archive.mkdir(parents=True)
    for name in ("metadata.json", "agents.json", "publication-package.json", "artifact-manifest.json"):
        if (out / name).is_file():
            shutil.copy2(out / name, archive / name)
    for name, value in (("metadata.json", metadata), ("agents.json", agents)):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    if checklist is not None:
        (out / "publication-package.json").write_text(json.dumps(checklist, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = pipeline.artifact_manifest(out, names)
    (out / "artifact-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    pipeline.verify_artifact_manifest(out)
    pipeline.store.update(job_id, job["status"], metadata, error=job.get("error"), progress=job.get("progress"), quality_score=job.get("quality_score"))
    pipeline.store.event(job_id, "metadata", "Metadados alinhados à cena codificada; derivados exigem nova preparação")
    return {"job_id": job_id, "title": metadata["title"], "production": metadata["production"], "backup": str(archive)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_ids", nargs="+")
    args = parser.parse_args()
    settings = Settings.load(Path(__file__).resolve().parents[1])
    pipeline = Pipeline(settings, Store(settings.data_dir / "factory.db"))
    for job_id in args.job_ids:
        print(json.dumps(align(pipeline, job_id), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
