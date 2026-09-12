from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from factory.config import Settings
from factory.backup import BackupManager
from factory.commerce import CommercePackager, validate_commerce_brief
from factory.commercial_center import CommercialCenter
from factory.integrations import IntegrationManager
from factory.autopilot import Autopilot
from factory.auth import LocalAuth
from factory.nightshift import NightShift
from factory.music_audit import MusicDiversityAuditor
from factory.pipeline import Pipeline
from factory.publishing import PublishingCenter
from factory.security import SecurityAuditor
from factory.web import serve
from factory.workspace_lifecycle import WorkspaceLifecycle
from factory.workspaces import DEFAULT_WORKSPACE_ID, WorkspaceRegistry


ROOT = Path(__file__).parent


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Faceless Content Factory")
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE_ID,
                        help="Espaço isolado a operar; o padrão preserva a instalação pessoal")
    sub = parser.add_subparsers(dest="command", required=True)
    workspace_create = sub.add_parser("workspace-create", help="Create an isolated client workspace")
    workspace_create.add_argument("workspace_id")
    workspace_create.add_argument("--name", required=True)
    sub.add_parser("workspace-list", help="List provisioned workspaces without opening their data")
    sub.add_parser("workspace-status", help="Show safe lifecycle and demo status for a client workspace")
    workspace_export = sub.add_parser("workspace-export", help="Export one client workspace with checksums")
    workspace_export.add_argument("--request-id")
    sub.add_parser("workspace-demo-seed", help="Add discardable onboarding demo files")
    sub.add_parser("workspace-demo-reset", help="Remove only service-owned demo files")
    sub.add_parser("workspace-delete-plan", help="Preview deletion without changing files")
    workspace_delete = sub.add_parser("workspace-delete", help="Backup and delete a client workspace")
    workspace_delete.add_argument("--confirmation", required=True)
    workspace_delete.add_argument("--username", required=True)
    auth_bootstrap = sub.add_parser("auth-bootstrap", help="Create the first local administrator safely")
    auth_bootstrap.add_argument("--username", required=True)
    sub.add_parser("auth-status", help="Check whether the selected workspace has a local administrator")
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
    english_metadata = sub.add_parser("migrate-english-metadata", help="Apply English titles to one pilot cohort")
    english_metadata.add_argument("--cohort-id", default="pilot-flow-2026-08-30")
    sub.add_parser("phase2-status", help="Show the audited progress of the three autonomous local batches")
    editorial = sub.add_parser("editorial-baseline", help="Preview or apply a safe one-video-per-week plan")
    editorial.add_argument("--apply", action="store_true", help="Archive stale plans and create the next weekly plan")
    review_cleanup = sub.add_parser("archive-superseded-reviews", help="Preview or archive old review packages")
    review_cleanup.add_argument("--apply", action="store_true", help="Archive candidates without deleting files")
    sub.add_parser("music-diversity-audit", help="Compare approved tracks without changing their review state")
    sub.add_parser("security-audit", help="Check tracked secrets, vault, remote access and backup recovery")
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
    smart_cuts = sub.add_parser("smart-cuts", help="Create ranked, traceable 9:16 candidates")
    smart_cuts.add_argument("job_id")
    smart_cuts.add_argument("--durations", default="15,30,60")
    smart_review = sub.add_parser("smart-cuts-review", help="Record an assisted editorial review without uploading")
    smart_review.add_argument("job_id")
    smart_review.add_argument("--reviewer", default="Codex assisted editorial review")
    smart_review.add_argument("--notes", default="")
    sub.add_parser("youtube-sync-metrics", help="Import read-only YouTube Analytics snapshots")
    reach_setup = sub.add_parser("youtube-setup-reach", help="Create one daily YouTube thumbnail reach report")
    reach_setup.add_argument("--confirm", action="store_true")
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
    restore_test = sub.add_parser("backup-restore-test", help="Test the latest backup in an isolated copy")
    restore_test.add_argument("--file", help="Optional backup filename; defaults to the latest")
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
    registry = WorkspaceRegistry(settings.data_dir)
    if args.command == "workspace-create":
        context = registry.provision(args.workspace_id, args.name)
        context.open_store()
        print(json.dumps(context.public_info(), ensure_ascii=False, indent=2))
        return
    if args.command == "workspace-list":
        print(json.dumps([item.public_info() for item in registry.list()], ensure_ascii=False, indent=2))
        return
    context = registry.get(args.workspace)
    settings = context.scoped_settings(settings)
    lifecycle = WorkspaceLifecycle(registry)
    auth = None
    if settings.local_auth or args.command in {"auth-bootstrap", "auth-status", "workspace-delete"}:
        auth = LocalAuth(registry.personal_data_dir / "private" / "access.db")
    if args.command == "auth-bootstrap":
        password = getpass.getpass("Senha do administrador: ")
        confirmation = getpass.getpass("Repita a senha: ")
        if password != confirmation:
            raise ValueError("As senhas não coincidem")
        print(json.dumps(auth.bootstrap_admin(args.username, password, context.id), ensure_ascii=False, indent=2))
        return
    if args.command == "auth-status":
        print(json.dumps({"workspace_id": context.id, "admin_ready": auth.has_admin(context.id)},
                         ensure_ascii=False, indent=2))
        return
    if args.command == "workspace-status":
        print(json.dumps({"workspace": context.public_info(), "demo": lifecycle.demo_status(context.id),
                          "deletion": lifecycle.deletion_plan(context.id)}, ensure_ascii=False, indent=2))
        return
    if args.command == "workspace-export":
        print(json.dumps(lifecycle.export_workspace(context.id, request_id=args.request_id),
                         ensure_ascii=False, indent=2))
        return
    if args.command == "workspace-demo-seed":
        print(json.dumps(lifecycle.seed_demo(context.id), ensure_ascii=False, indent=2))
        return
    if args.command == "workspace-demo-reset":
        print(json.dumps(lifecycle.reset_demo(context.id), ensure_ascii=False, indent=2))
        return
    if args.command == "workspace-delete-plan":
        print(json.dumps(lifecycle.deletion_plan(context.id), ensure_ascii=False, indent=2))
        return
    if args.command == "workspace-delete":
        password = getpass.getpass("Confirme a senha atual do administrador: ")
        login = auth.login(args.username, password, context.id)
        token = login.pop("session_token")
        try:
            session = auth.session(token)
            if not session:
                raise PermissionError("Sessão administrativa inválida")
            auth.require_role(session, {"admin"})
            verified = auth.reauthenticate(token, password)
            if not auth.recently_reauthenticated(verified):
                raise PermissionError("Reautenticação recente obrigatória")
            print(json.dumps(lifecycle.delete_workspace(
                context.id, confirmation=args.confirmation
            ), ensure_ascii=False, indent=2))
        finally:
            auth.logout(token)
        return
    store = context.open_store()
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
        serve(pipeline, store, settings.host, settings.port, ROOT / "web", auth=auth,
              workspace_id=context.id, operational_dir=registry.personal_data_dir / "private",
              lifecycle=lifecycle)
    elif args.command == "migrate-covers":
        print(json.dumps(pipeline.synchronize_video_visuals(), ensure_ascii=False, indent=2))
    elif args.command == "sync-video-visuals":
        print(json.dumps(pipeline.synchronize_video_visuals(), ensure_ascii=False, indent=2))
    elif args.command == "repair-manifests":
        print(json.dumps(pipeline.repair_artifact_manifests(), ensure_ascii=False, indent=2))
    elif args.command == "migrate-english-metadata":
        print(json.dumps(pipeline.migrate_pilot_metadata_to_english(args.cohort_id), ensure_ascii=False, indent=2))
    elif args.command == "phase2-status":
        class _IdleRunner:
            @staticmethod
            def snapshot() -> dict[str, object]:
                return {"active": [], "worker_limit": 0}

        nightshift = NightShift(pipeline, store, _IdleRunner(), Autopilot(settings, store))
        print(json.dumps(nightshift.phase2_certification(), ensure_ascii=False, indent=2))
    elif args.command == "editorial-baseline":
        print(json.dumps(Autopilot(settings, store).apply_weekly_baseline(args.apply), ensure_ascii=False, indent=2))
    elif args.command == "archive-superseded-reviews":
        print(json.dumps(Autopilot(settings, store).archive_superseded_reviews(args.apply), ensure_ascii=False, indent=2))
    elif args.command == "music-diversity-audit":
        auditor = MusicDiversityAuditor(settings.ffmpeg, settings.data_dir / "reports")
        print(json.dumps(auditor.audit(store.list_music_assets(approved_only=True)), ensure_ascii=False, indent=2))
    elif args.command == "security-audit":
        print(json.dumps(SecurityAuditor(settings).audit(), ensure_ascii=False, indent=2))
    elif args.command == "establish-pilot-cohort":
        print(json.dumps(pipeline.establish_current_pilot_cohort(args.cohort_id), ensure_ascii=False, indent=2))
    elif args.command == "lyria-generate":
        print(json.dumps(pipeline.lyria.generate(args.name, args.prompt, args.model, args.confirm_rights),
                         ensure_ascii=False, indent=2))
    elif args.command == "youtube-package":
        print(json.dumps(pipeline.prepare_youtube_package(args.job_id), ensure_ascii=False, indent=2))
    elif args.command == "vertical-package":
        print(json.dumps(pipeline.prepare_vertical_package(args.job_id, args.duration), ensure_ascii=False, indent=2))
    elif args.command == "smart-cuts":
        durations = [int(value.strip()) for value in args.durations.split(",") if value.strip()]
        print(json.dumps(pipeline.prepare_smart_cuts(args.job_id, durations), ensure_ascii=False, indent=2))
    elif args.command == "smart-cuts-review":
        print(json.dumps(pipeline.review_smart_cuts(args.job_id, args.reviewer, args.notes),
                         ensure_ascii=False, indent=2))
    elif args.command == "youtube-sync-metrics":
        print(json.dumps(integrations.sync_youtube_metrics(), ensure_ascii=False, indent=2))
    elif args.command == "youtube-setup-reach":
        print(json.dumps(integrations.ensure_youtube_reach_reporting(args.confirm), ensure_ascii=False, indent=2))
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
    elif args.command == "backup-restore-test":
        result = BackupManager(store.db_path, settings.data_dir / "backups", settings.backup_keep).test_restore(args.file)
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
