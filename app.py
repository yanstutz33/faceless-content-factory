from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from factory.config import Settings
from factory.backup import BackupManager
from factory.commerce import CommercePackager, validate_commerce_brief
from factory.commercial_center import CommercialCenter
from factory.integrations import IntegrationManager
from factory.pipeline import Pipeline
from factory.publishing import PublishingCenter
from factory.store import Store
from factory.web import serve


ROOT = Path(__file__).parent


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Faceless Content Factory")
    sub = parser.add_subparsers(dest="command", required=True)
    generate = sub.add_parser("generate", help="Generate one complete local video package")
    generate.add_argument("--topic", default="Biblioteca chuvosa à noite")
    generate.add_argument("--duration", type=int, choices=[1800, 3600], default=3600)
    generate.add_argument("--profile", choices=["youtube_long"], default="youtube_long")
    generate.add_argument("--asset", help="Optional JPG/PNG/WebP source image")
    generate.add_argument("--confirm-asset-rights", action="store_true",
                          help="Confirm that the supplied asset may be used commercially")
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
    metrics.add_argument("--impressions", type=int, default=0)
    metrics.add_argument("--clicks", type=int, default=0)
    metrics.add_argument("--average-view-seconds", type=float, default=0)
    metrics.add_argument("--thumbnail-variant", choices=["a", "b"], default="a")
    metrics.add_argument("--conversions", type=int, default=0)
    metrics.add_argument("--revenue", type=float, default=0)
    sub.add_parser("serve", help="Open the local operations dashboard")
    sub.add_parser("migrate-covers", help="Replace legacy thumbnails with the approved visual collection")
    sub.add_parser("sync-video-visuals", help="Rebuild videos from the same approved image used by their poster")
    sub.add_parser("repair-manifests", help="Repair and validate complete artifact manifests")
    pilot = sub.add_parser("establish-pilot-cohort", help="Tag current pilots and archive historical review jobs")
    pilot.add_argument("--cohort-id", default="pilot-flow-2026-08-30")
    lyria = sub.add_parser("lyria-generate", help="Generate and register one instrumental track with Google Lyria 3")
    lyria.add_argument("--name", required=True)
    lyria.add_argument("--prompt", required=True)
    lyria.add_argument("--model", choices=["lyria-3-clip-preview", "lyria-3-pro-preview"], default="lyria-3-pro-preview")
    lyria.add_argument("--confirm-rights", action="store_true")
    youtube = sub.add_parser("youtube-package", help="Prepare a private YouTube upload package without uploading")
    youtube.add_argument("job_id")
    vertical = sub.add_parser("vertical-package", help="Create a manual-safe 9:16 derivative from an approved job")
    vertical.add_argument("job_id")
    vertical.add_argument("--duration", type=int, default=30)
    bilibili = sub.add_parser("bilibili-package", help="Prepare a localized Bilibili package without uploading")
    bilibili.add_argument("job_id")
    sub.add_parser("doctor", help="Check FFmpeg, FFprobe, storage and safe operation mode")
    commerce = sub.add_parser("commerce-check", help="Validate one affiliate product brief without publishing")
    commerce.add_argument("product_json", type=Path)
    commerce_package = sub.add_parser("commerce-package", help="Prepare a rights-safe Shopee package without uploading")
    commerce_package.add_argument("job_id")
    commerce_package.add_argument("product_json", type=Path)
    commerce_package.add_argument("--duration", type=int, default=30)
    sub.add_parser("integrations", help="Show connector readiness without exposing credentials")
    preflight = sub.add_parser("preflight", help="Stage a manual-safe delivery check without uploading")
    preflight.add_argument("platform", choices=["youtube", "tiktok", "reels", "shopee"])
    preflight.add_argument("--job-id")
    sub.add_parser("backup", help="Create and verify a local database backup")
    sub.add_parser("commerce-overview", help="Show affiliate products, campaigns and results")
    commerce_product = sub.add_parser("commerce-save-product", help="Validate and save a Shopee product brief")
    commerce_product.add_argument("product_json", type=Path)
    commerce_campaign = sub.add_parser("commerce-create-campaign", help="Create a manual-safe affiliate campaign")
    commerce_campaign.add_argument("campaign_json", type=Path)
    commerce_metrics = sub.add_parser("commerce-metrics", help="Record one commercial performance snapshot")
    commerce_metrics.add_argument("campaign_id")
    commerce_metrics.add_argument("metrics_json", type=Path)
    pinterest_package = sub.add_parser("commerce-pinterest-package", help="Prepare a Video Pin package without uploading")
    pinterest_package.add_argument("campaign_id")
    pinterest_package.add_argument("--board-name", default="Achados úteis")
    args = parser.parse_args()

    settings = Settings.load(ROOT)
    store = Store(settings.data_dir / "factory.db")
    pipeline = Pipeline(settings, store)
    publishing = PublishingCenter(pipeline, store)
    integrations = IntegrationManager(settings, store, publishing)
    commercial = CommercialCenter(store, CommercePackager(pipeline, store))
    if args.command == "generate":
        job_id = pipeline.create(args.topic, args.duration, args.narration, not args.no_subtitles,
                                 args.profile, args.asset,
                                 source_asset_rights_confirmed=args.confirm_asset_rights)
        print(json.dumps(pipeline.run(job_id), ensure_ascii=False, indent=2))
    elif args.command == "list":
        print(json.dumps(store.list_jobs(), ensure_ascii=False, indent=2))
    elif args.command == "approve":
        pipeline.approve(args.job_id)
        print(f"Aprovado: {args.job_id}")
    elif args.command == "metrics":
        store.add_metrics(args.job_id, args.platform, args.views, args.likes, args.watch_minutes,
                          args.impressions, args.clicks, args.average_view_seconds,
                          args.thumbnail_variant, args.conversions, args.revenue)
        print(f"Métricas registradas: {args.job_id}")
    elif args.command == "serve":
        serve(pipeline, store, settings.host, settings.port, ROOT / "web")
    elif args.command == "migrate-covers":
        print(json.dumps(pipeline.synchronize_video_visuals(), ensure_ascii=False, indent=2))
    elif args.command == "sync-video-visuals":
        print(json.dumps(pipeline.synchronize_video_visuals(), ensure_ascii=False, indent=2))
    elif args.command == "repair-manifests":
        print(json.dumps(pipeline.repair_artifact_manifests(), ensure_ascii=False, indent=2))
    elif args.command == "establish-pilot-cohort":
        print(json.dumps(pipeline.establish_current_pilot_cohort(args.cohort_id), ensure_ascii=False, indent=2))
    elif args.command == "lyria-generate":
        print(json.dumps(pipeline.lyria.generate(args.name, args.prompt, args.model, args.confirm_rights),
                         ensure_ascii=False, indent=2))
    elif args.command == "youtube-package":
        print(json.dumps(pipeline.prepare_youtube_package(args.job_id), ensure_ascii=False, indent=2))
    elif args.command == "vertical-package":
        print(json.dumps(pipeline.prepare_vertical_package(args.job_id, args.duration), ensure_ascii=False, indent=2))
    elif args.command == "bilibili-package":
        print(json.dumps(publishing.bilibili.prepare(args.job_id), ensure_ascii=False, indent=2))
    elif args.command == "doctor":
        report = pipeline.diagnostics()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report["ok"]:
            sys.exit(1)
    elif args.command == "commerce-check":
        result = validate_commerce_brief(json.loads(args.product_json.read_text(encoding="utf-8")))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["passed"]:
            sys.exit(2)
    elif args.command == "commerce-package":
        product = json.loads(args.product_json.read_text(encoding="utf-8"))
        result = CommercePackager(pipeline, store).prepare(args.job_id, product, args.duration)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "integrations":
        print(json.dumps(integrations.readiness(), ensure_ascii=False, indent=2))
    elif args.command == "preflight":
        print(json.dumps(integrations.preflight(args.platform, args.job_id), ensure_ascii=False, indent=2))
    elif args.command == "backup":
        result = BackupManager(store.db_path, settings.data_dir / "backups", settings.backup_keep).create()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "commerce-overview":
        print(json.dumps(commercial.overview(), ensure_ascii=False, indent=2))
    elif args.command == "commerce-save-product":
        product = json.loads(args.product_json.read_text(encoding="utf-8"))
        print(json.dumps(commercial.create_product(product), ensure_ascii=False, indent=2))
    elif args.command == "commerce-create-campaign":
        campaign = json.loads(args.campaign_json.read_text(encoding="utf-8"))
        print(json.dumps(commercial.create_campaign(campaign), ensure_ascii=False, indent=2))
    elif args.command == "commerce-metrics":
        metrics_data = json.loads(args.metrics_json.read_text(encoding="utf-8"))
        print(json.dumps(commercial.record_metrics(args.campaign_id, metrics_data), ensure_ascii=False, indent=2))
    elif args.command == "commerce-pinterest-package":
        print(json.dumps(commercial.prepare_pinterest(args.campaign_id, {"board_name": args.board_name}),
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
