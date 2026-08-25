from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from factory.config import Settings
from factory.pipeline import Pipeline
from factory.store import Store
from factory.web import serve


ROOT = Path(__file__).parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Faceless Content Factory")
    sub = parser.add_subparsers(dest="command", required=True)
    generate = sub.add_parser("generate", help="Generate one complete local video package")
    generate.add_argument("--topic", default="Biblioteca chuvosa à noite")
    generate.add_argument("--duration", type=int, default=30)
    generate.add_argument("--profile", choices=["youtube_long", "vertical_short", "preview"], default="youtube_long")
    generate.add_argument("--asset", help="Optional JPG/PNG/WebP source image")
    generate.add_argument("--narration", action="store_true")
    generate.add_argument("--no-subtitles", action="store_true")
    sub.add_parser("list", help="List queued jobs")
    approve = sub.add_parser("approve", help="Approve a rendered package")
    approve.add_argument("job_id")
    metrics = sub.add_parser("metrics", help="Record performance metrics")
    metrics.add_argument("job_id")
    metrics.add_argument("--platform", default="youtube")
    metrics.add_argument("--views", type=int, default=0)
    metrics.add_argument("--likes", type=int, default=0)
    metrics.add_argument("--watch-minutes", type=float, default=0)
    sub.add_parser("serve", help="Open the local operations dashboard")
    sub.add_parser("doctor", help="Check FFmpeg, FFprobe, storage and safe operation mode")
    args = parser.parse_args()

    settings = Settings.load(ROOT)
    store = Store(settings.data_dir / "factory.db")
    pipeline = Pipeline(settings, store)
    if args.command == "generate":
        job_id = pipeline.create(args.topic, max(5, args.duration), args.narration, not args.no_subtitles,
                                 args.profile, args.asset)
        print(json.dumps(pipeline.run(job_id), ensure_ascii=False, indent=2))
    elif args.command == "list":
        print(json.dumps(store.list_jobs(), ensure_ascii=False, indent=2))
    elif args.command == "approve":
        pipeline.approve(args.job_id)
        print(f"Aprovado: {args.job_id}")
    elif args.command == "metrics":
        store.add_metrics(args.job_id, args.platform, args.views, args.likes, args.watch_minutes)
        print(f"Métricas registradas: {args.job_id}")
    elif args.command == "serve":
        serve(pipeline, store, settings.host, settings.port, ROOT / "web")
    elif args.command == "doctor":
        report = pipeline.diagnostics()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report["ok"]:
            sys.exit(1)


if __name__ == "__main__":
    main()
