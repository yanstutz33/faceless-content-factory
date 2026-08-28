import json
import hashlib
import os
import re
import shutil
import sqlite3
from contextlib import closing
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from factory.agents import ContentCrew, PROFILES
from factory.autopilot import Autopilot
from factory.backup import BackupManager
from factory.bilibili import BilibiliPackager
from factory.config import Settings
from factory.commerce import CommercePackager, validate_commerce_brief
from factory.commercial_center import CommercialCenter
from factory.creative import CreativeDirector, MUSIC_ARRANGEMENTS
from factory.integrations import DeliveryLedger, IntegrationAudit, IntegrationManager
from factory.llm import OpenAIPlanEnhancer
from factory.nightshift import NightShift
from factory.pipeline import Pipeline, safe_slug, srt_timestamp
from factory.publishing import PublishingCenter
from factory.store import Store
from factory.teams import SHARED_SKILLS, skill_catalog, team_catalog
from factory.web import CalendarScheduler, create_server
from factory.vault import SecureVault


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
        self.assertIn("lo-fi", plan["visual"]["sound"].lower())
        self.assertIn("Lo-fi", plan["seo"]["title"])
        self.assertGreaterEqual(len(ContentCrew().ideas()), 5)

    def test_specialized_teams_execute_distinct_playbooks(self):
        youtube = ContentCrew().run("Café noturno", 1800, "youtube_long", False, "youtube_ambient")
        vertical = ContentCrew().run("Café noturno", 30, "vertical_short", True, "tiktok_experiments")
        bilibili = ContentCrew().run("Café noturno", 1800, "youtube_long", False, "bilibili_lab")
        self.assertEqual(youtube["strategy"]["primary_goal"], "watch_time")
        self.assertEqual(vertical["strategy"]["primary_goal"], "completion_and_shares")
        self.assertIn("experiment", vertical["strategy"])
        self.assertEqual(bilibili["seo"]["localized"]["locale"], "zh-CN")
        self.assertTrue(set(SHARED_SKILLS).issubset(youtube["team"]["skills_executed"]))

    def test_team_and_skill_catalogs_are_consistent(self):
        teams = team_catalog()
        skills = skill_catalog()
        skill_ids = {item["id"] for item in skills}
        self.assertEqual(len(teams), 4)
        self.assertEqual(len(skill_ids), len(skills))
        self.assertEqual(next(team for team in teams if team["id"] == "tiktok_experiments")["recommended_profile"],
                         "vertical_short")
        for team in teams:
            self.assertTrue(set(team["shared_skills"]).issubset(skill_ids))
            self.assertTrue(set(team["skills"]).issubset(skill_ids))

    def test_creative_director_avoids_repeating_a_previous_recipe(self):
        director = CreativeDirector()
        scenes = ("janela-chuvosa", "cidade-noturna", "cafe-vazio")
        first = director.plan("Café noturno para estudar", "cozy", "preview", scenes, [], [])
        history = [{
            "id": "old-job", "topic": "Café noturno para estudar",
            "metadata": {"creative_fingerprint": first},
        }]
        second = director.plan("Café noturno para estudar", "cozy", "preview", scenes, history, [])
        similarity, _ = director.similarity(first, second)
        self.assertLess(similarity, .72)
        self.assertNotEqual(
            (first["scene"], first["music_arrangement"], first["motion_effect"]),
            (second["scene"], second["music_arrangement"], second["motion_effect"]),
        )
        self.assertEqual(second["novelty"]["closest_job_id"], "old-job")
        self.assertEqual(second["novelty"]["candidates_evaluated"], 48)

    def test_creative_learning_uses_metrics_without_overriding_novelty(self):
        director = CreativeDirector()
        insights = [{
            "retention_rate": 78, "ctr": 8.5, "engagement_rate": 6.0,
            "music_arrangement": "night_rhodes", "treatment": "teal_noir",
            "motion_effect": "dust_motes",
        }]
        dna = director.plan("Foco depois da meia-noite", "focus", "preview", ("studio",), [], insights)
        self.assertEqual(dna["learning"]["mode"], "measured")
        self.assertEqual(dna["learning"]["evidence_count"], 1)
        self.assertEqual(dna["learning"]["preferred"]["music_arrangement"], "night_rhodes")
        self.assertGreaterEqual(dna["novelty"]["score"], 99)

    def test_creative_status_exposes_scale_and_future_cuts_boundary(self):
        status = CreativeDirector().status([], [])
        self.assertEqual(status["engine"], "creative_dna_v2")
        self.assertEqual(status["catalog"]["music_arrangements"], len(MUSIC_ARRANGEMENTS))
        self.assertGreaterEqual(status["catalog"]["candidate_space"], 25_000)
        self.assertEqual(status["future_modules"]["smart_cuts"]["status"], "planned")

    def test_pipeline_persists_selected_team_and_blocks_commerce_entrypoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            job_id = pipeline.create("Gancho vertical", 15, profile="vertical_short", team_id="tiktok_experiments")
            self.assertEqual(store.get_job(job_id)["team_id"], "tiktok_experiments")
            with self.assertRaisesRegex(ValueError, "Centro de Afiliados"):
                pipeline.create("Produto", 15, profile="vertical_short", team_id="affiliate_commerce")

    def test_optional_llm_keeps_local_plan_without_api_key(self):
        enhancer = OpenAIPlanEnhancer("")
        plan = ContentCrew(enhancer).run("Café silencioso", 1800, "youtube_long", False)
        self.assertFalse(enhancer.configured)
        self.assertNotIn("provider", plan)

    def test_commerce_brief_fails_closed_without_media_rights(self):
        result = validate_commerce_brief({"product_id": "123", "title": "Produto", "product_url": "https://shopee.com.br/item/123",
                                          "exact_product_confirmed": True, "affiliate_disclosure": True,
                                          "assets": [{"name": "Pin", "license_type": "unknown", "approved": False}]})
        self.assertFalse(result["passed"])
        self.assertEqual(result["pinterest_policy"], "research_only_not_media_source")

    def test_commerce_brief_accepts_traceable_original_media(self):
        result = validate_commerce_brief({"product_id": "123", "title": "Produto", "product_url": "https://shopee.com.br/item/123",
                                          "exact_product_confirmed": True, "affiliate_disclosure": True,
                                          "assets": [{"name": "Demo própria", "license_type": "original", "approved": True}],
                                          "claims": [{"text": "Material informado", "source": "página oficial"}]})
        self.assertTrue(result["passed"])

    def test_commerce_brief_rejects_non_shopee_and_pinterest_media(self):
        result = validate_commerce_brief({"product_id": "123", "title": "Produto", "product_url": "https://example.com/item/123",
                                          "exact_product_confirmed": True, "affiliate_disclosure": True,
                                          "assets": [{"name": "Pin", "license_type": "commercial_license", "approved": True,
                                                      "source_url": "https://pinterest.com/pin/123"}]})
        self.assertFalse(result["passed"])
        self.assertTrue(any("Shopee Brasil" in error for error in result["errors"]))
        self.assertTrue(any("Pinterest" in error for error in result["errors"]))

    def test_commerce_packager_creates_manual_safe_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            job_id = pipeline.create("Produto em uso", 5, profile="preview")
            job = store.get_job(job_id)
            store.update(job_id, "approved", {"verification": {"passed": True}, "quality_gate": {"passed": True}}, progress=100)
            output = Path(job["output_dir"])
            def vertical(_job_id, _duration):
                (output / "vertical-short.mp4").write_bytes(b"video")
                (output / "vertical-thumbnail.jpg").write_bytes(b"image")
                return {"mode": "prepared_not_uploaded"}
            product = {"product_id": "123", "title": "Luminária", "product_url": "https://shopee.com.br/item/123",
                       "affiliate_url": "https://s.shopee.com.br/abc",
                       "exact_product_confirmed": True, "affiliate_disclosure": True,
                       "assets": [{"name": "Demonstração própria", "license_type": "original", "approved": True}],
                       "claims": [{"text": "Material informado pelo vendedor", "source": "Página oficial"}]}
            with patch.object(pipeline, "prepare_vertical_package", side_effect=vertical):
                package = CommercePackager(pipeline, store).prepare(job_id, product, 5)
            self.assertFalse(package["automatic_upload_allowed"])
            self.assertEqual(package["platform"], "shopee")
            self.assertEqual(package["team"]["id"], "affiliate_commerce")
            self.assertIn("product_truth", package["team"]["skills_executed"])
            self.assertEqual(package["product"]["affiliate_url"], "https://s.shopee.com.br/abc")
            self.assertTrue((output / "commerce-package.json").is_file())

    def test_commercial_center_tracks_catalog_campaign_and_profit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            packager = CommercePackager(pipeline, store)
            center = CommercialCenter(store, packager)
            product = center.create_product({
                "product_id": "SKU-123", "title": "Luminária de mesa",
                "product_url": "https://shopee.com.br/produto/123",
                "affiliate_url": "https://s.shopee.com.br/abc", "price": 79.9,
                "exact_product_confirmed": True, "affiliate_disclosure": True,
                "assets": [{"name": "Demonstração própria", "license_type": "original", "approved": True}],
                "claims": [{"text": "Potência informada pelo vendedor", "source": "Ficha oficial"}],
            })
            self.assertEqual(product["status"], "validated")
            campaign = center.create_campaign({"product_id": product["id"], "name": "Teste 01",
                                               "destination": "shopee_video", "cost": 20})
            self.assertEqual(campaign["status"], "draft")
            measured = center.record_metrics(campaign["id"], {"clicks": 50, "conversions": 5,
                                                                "commission": 60, "cost": 20})
            self.assertEqual(measured["conversion_rate"], 10)
            self.assertEqual(measured["roi"], 200)
            overview = center.overview()
            self.assertEqual(overview["summary"]["profit"], 40)
            self.assertFalse(overview["automatic_upload_allowed"])

    def test_commercial_center_blocks_invalid_product_from_campaign(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            center = CommercialCenter(store, CommercePackager(pipeline, store))
            product = center.create_product({
                "product_id": "SKU-INVALID", "title": "Produto",
                "product_url": "https://example.com/product", "affiliate_url": "https://example.com/affiliate",
                "assets": [{"name": "Pin", "license_type": "commercial_license", "approved": True,
                            "source_url": "https://pinterest.com/pin/123"}],
            })
            self.assertEqual(product["status"], "blocked")
            with self.assertRaisesRegex(ValueError, "validação comercial"):
                center.create_campaign({"product_id": product["id"], "name": "Não pode entrar"})

    def test_commercial_campaign_package_keeps_affiliate_link_and_manual_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            packager = CommercePackager(pipeline, store)
            center = CommercialCenter(store, packager)
            job_id = pipeline.create("Demonstração de produto", 5, profile="preview")
            store.update(job_id, "approved", {}, progress=100)
            product = center.create_product({
                "product_id": "SKU-PACK", "title": "Produto demonstrado",
                "product_url": "https://shopee.com.br/produto/pack",
                "affiliate_url": "https://s.shopee.com.br/pack", "exact_product_confirmed": True,
                "affiliate_disclosure": True,
                "assets": [{"name": "Vídeo próprio", "license_type": "original", "approved": True}],
            })
            campaign = center.create_campaign({"product_id": product["id"], "name": "Pacote",
                                               "job_id": job_id, "destination": "shopee_video"})
            with patch.object(packager, "prepare", return_value={"automatic_upload_allowed": False}) as prepare:
                result = center.prepare_campaign(campaign["id"], 15)
            self.assertEqual(prepare.call_args.args[1]["affiliate_url"], "https://s.shopee.com.br/pack")
            self.assertEqual(result["campaign"]["status"], "packaged")
            self.assertFalse(result["automatic_upload_allowed"])

    def test_pinterest_package_reuses_validated_commercial_media_without_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            commerce = CommercePackager(pipeline, store)
            center = CommercialCenter(store, commerce)
            job_id = pipeline.create("Produto original para Pinterest", 5, profile="preview")
            store.update(job_id, "approved", {}, progress=100)
            output = Path(store.get_job(job_id)["output_dir"])
            (output / "vertical-short.mp4").write_bytes(b"video")
            (output / "vertical-thumbnail.jpg").write_bytes(b"cover")
            (output / "commerce-package.json").write_text("{}", encoding="utf-8")
            product = center.create_product({
                "product_id": "SKU-PIN", "title": "Luminária autoral",
                "product_url": "https://shopee.com.br/produto/pin",
                "affiliate_url": "https://s.shopee.com.br/pin", "exact_product_confirmed": True,
                "affiliate_disclosure": True,
                "assets": [{"name": "Vídeo próprio", "license_type": "original", "approved": True}],
            })
            campaign = center.create_campaign({"product_id": product["id"], "name": "Pin seguro",
                                               "job_id": job_id, "destination": "shopee_video"})
            with patch.object(commerce, "prepare", return_value={"automatic_upload_allowed": False}):
                center.prepare_campaign(campaign["id"], 15)
            result = center.prepare_pinterest(campaign["id"], {"board_name": "Achados testados"})
            payload = result["package"]["api_plan"]["payload_template"]
            self.assertEqual(result["campaign"]["pinterest_status"], "prepared")
            self.assertEqual(result["package"]["board_target"]["name"], "Achados testados")
            self.assertEqual(payload["link"], "https://s.shopee.com.br/pin")
            self.assertEqual(payload["media_source"]["source_type"], "video_id")
            self.assertFalse(result["automatic_upload_allowed"])
            self.assertTrue(result["login_required"])
            self.assertTrue((output / "pinterest-package.json").is_file())

    def test_backup_manager_creates_integrity_checked_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "factory.db")
            store.add_calendar_item("Backup test", None, "preview", 5, "2026-09-01T19:00")
            manager = BackupManager(store.db_path, root / "backups", keep=2)
            first = manager.create()
            second = manager.create()
            self.assertEqual(first["integrity"], "ok")
            self.assertEqual(second["integrity"], "ok")
            self.assertEqual(len(manager.list()), 2)
            with closing(sqlite3.connect(root / "backups" / second["file"])) as database:
                self.assertEqual(database.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_integration_audit_scrubs_sensitive_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = IntegrationAudit(Path(tmp) / "audit.jsonl")
            audit.record("test", "youtube", {"access_token": "never-store-in-log", "nested": {"client_secret": "hidden"}})
            raw = (Path(tmp) / "audit.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("never-store-in-log", raw)
            self.assertNotIn("hidden", raw)
            self.assertEqual(audit.recent()[0]["detail"]["access_token"], "[redacted]")

    def test_delivery_retry_policy_is_bounded(self):
        base = datetime.fromisoformat("2026-08-26T12:00:00+00:00")
        first = datetime.fromisoformat(DeliveryLedger.retry_after(1, base))
        late = datetime.fromisoformat(DeliveryLedger.retry_after(20, base))
        self.assertEqual((first - base).total_seconds(), 15)
        self.assertEqual((late - base).total_seconds(), 3600)

    def test_secure_vault_round_trip_uses_encrypted_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = SecureVault(Path(tmp) / "oauth.vault")
            vault.set("token:test", {"access_token": "sensitive-value"})
            self.assertEqual(vault.get("token:test")["access_token"], "sensitive-value")
            self.assertNotIn(b"sensitive-value", (Path(tmp) / "oauth.vault").read_bytes())
            self.assertIsNotNone(vault.pop("token:test"))
            self.assertFalse(vault.contains("token:test"))

    def test_oauth_flow_prepares_pkce_and_stores_tokens_without_exposing_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            secrets_file = root / "client.json"
            secrets_file.write_text(json.dumps({"installed": {"client_id": "client-id", "client_secret": "client-secret",
                                                               "redirect_uris": ["http://127.0.0.1:8787/api/oauth/callback/youtube"]}}), encoding="utf-8")
            settings = replace(self.settings(root), youtube_client_secrets_file=str(secrets_file))
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(settings, store)
            manager = IntegrationManager(settings, store, PublishingCenter(pipeline, store))
            start = manager.oauth_start("youtube")
            query = parse_qs(urlparse(start["authorization_url"]).query)
            self.assertIn("code_challenge", query)
            self.assertNotIn("verifier", json.dumps(start))
            with patch.object(manager, "_post_form", return_value={"access_token": "top-secret", "refresh_token": "refresh"}):
                result = manager.oauth_callback("youtube", query["state"][0], "authorization-code")
            self.assertTrue(result["connected"])
            self.assertNotIn("top-secret", json.dumps(result))
            self.assertTrue(manager.readiness()["platforms"][0]["authenticated"])

    def test_oauth_callback_rejects_expired_state_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            secrets_file = root / "client.json"
            secrets_file.write_text(json.dumps({"installed": {"client_id": "id", "client_secret": "secret",
                                                               "redirect_uris": ["http://127.0.0.1:8787/api/oauth/callback/youtube"]}}), encoding="utf-8")
            settings = replace(self.settings(root), youtube_client_secrets_file=str(secrets_file))
            store = Store(root / "data" / "factory.db")
            manager = IntegrationManager(settings, store, PublishingCenter(Pipeline(settings, store), store))
            manager.vault.set("pending:expired", {"platform": "youtube", "verifier": "v",
                                                   "created_at": "2020-01-01T00:00:00+00:00"})
            with patch.object(manager, "_post_form") as post:
                with self.assertRaisesRegex(ValueError, "expirou"):
                    manager.oauth_callback("youtube", "expired", "code")
                post.assert_not_called()

    def test_editorial_calendar(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "factory.db")
            item_id = store.add_calendar_item("Rainy cafe", "rainy_places", "youtube_long", 1800, "2026-09-01T19:00")
            self.assertGreater(item_id, 0)
            self.assertEqual(store.list_calendar()[0]["status"], "planned")
            store.link_calendar_job(item_id, "job-123")
            self.assertEqual(store.list_calendar()[0]["job_id"], "job-123")

    def test_due_calendar_item_enters_queue_automatically(self):
        class CapturingRunner:
            def __init__(self):
                self.submitted = []

            def submit(self, job_id):
                self.submitted.append(job_id)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            due_id = store.add_calendar_item("Due ambience", None, "preview", 5, "2020-01-01T10:00")
            future_id = store.add_calendar_item("Future ambience", None, "preview", 5, "2099-01-01T10:00")
            runner = CapturingRunner()
            autopilot = Autopilot(self.settings(root), store)
            created = CalendarScheduler(pipeline, store, runner, autopilot).run_once()
            calendar = {item["id"]: item for item in store.list_calendar()}
            self.assertEqual(len(created), 1)
            self.assertEqual(runner.submitted, created)
            self.assertEqual(calendar[due_id]["status"], "producing")
            self.assertEqual(calendar[due_id]["job_id"], created[0])
            self.assertEqual(calendar[future_id]["status"], "planned")
            self.assertEqual(store.get_job(created[0])["events"][-1]["stage"], "calendar")
            self.assertIsNone(store.claim_calendar_item(due_id))
            store.update(created[0], "awaiting_approval", {}, progress=100)
            self.assertEqual({item["id"]: item for item in store.list_calendar()}[due_id]["status"], "ready")

    def test_autopilot_plans_week_without_duplicate_topics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            autopilot = Autopilot(self.settings(root), store)
            status = autopilot.configure({
                "enabled": True, "series_ids": ["rainy_places", "cozy_worlds"],
                "cadence": 3, "publish_hour": "18:30", "duration": 1200,
            })
            self.assertTrue(status["enabled"])
            first = autopilot.ensure_plan(datetime(2026, 8, 25, 10, 0))
            second = autopilot.ensure_plan(datetime(2026, 8, 25, 10, 0))
            self.assertEqual(len(first), 3)
            self.assertEqual(second, [])
            calendar = store.list_calendar()
            self.assertEqual({item["origin"] for item in calendar}, {"autopilot"})
            self.assertEqual({item["series_id"] for item in calendar}, {"rainy_places", "cozy_worlds"})
            self.assertEqual(len({item["topic"] for item in calendar}), 3)
            self.assertTrue(all(item["duration"] == 1200 for item in calendar))

    def test_night_shift_runs_bounded_batch_and_never_publishes(self):
        class FakeRunner:
            def __init__(self):
                self.active = set()

            def submit(self, job_id):
                self.active.add(job_id)

            def snapshot(self):
                return {"active": sorted(self.active), "worker_limit": 1}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            autopilot = Autopilot(self.settings(root), store)
            autopilot.configure({"enabled": True, "series_ids": ["rainy_places"], "cadence": 3,
                                 "publish_hour": "19:00", "duration": 300})
            autopilot.ensure_plan(datetime(2026, 8, 26, 10, 0))
            runner = FakeRunner()
            night = NightShift(pipeline, store, runner, autopilot)
            night.configure({"enabled": True, "start_hour": "22:00", "end_hour": "07:00", "batch_limit": 2})
            self.assertTrue(night.in_window(datetime(2026, 8, 26, 23, 0)))
            self.assertTrue(night.in_window(datetime(2026, 8, 27, 6, 0)))
            self.assertFalse(night.in_window(datetime(2026, 8, 27, 12, 0)))
            result = night.run_once(force=True)
            self.assertEqual(len(result["created"]), 2)
            self.assertFalse(result["publish_performed"])
            self.assertEqual(len(runner.active), 2)
            self.assertEqual(sum(item["status"] == "producing" for item in store.list_calendar()), 2)

    def test_manual_calendar_bypasses_autopilot_pause(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "factory.db")
            store.add_calendar_item("Automatic", None, "preview", 5, "2020-01-01T09:00", "autopilot")
            manual_id = store.add_calendar_item("Manual", None, "preview", 5, "2020-01-01T10:00")
            claimed = store.claim_due_calendar(datetime(2026, 8, 25, 10, 0), allow_autopilot=False)
            self.assertEqual(claimed["id"], manual_id)

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
            store.add_metrics(job_id, "shorts", 200, 20, 40, impressions=1000, clicks=80,
                              average_view_seconds=4, thumbnail_variant="b")
            summary = store.summary()
            self.assertEqual(summary["views"], 425)
            self.assertEqual(summary["likes"], 41)
            self.assertEqual(summary["watch_minutes"], 79)
            insights = store.performance_insights()
            self.assertEqual(insights[0]["views"], 200)
            self.assertEqual(insights[0]["ctr"], 8.0)
            self.assertEqual(store.thumbnail_insights()[0]["thumbnail_variant"], "b")

    def test_youtube_package_is_private_and_never_uploads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            job_id = pipeline.create("Private upload package", 5, profile="preview")
            job = store.get_job(job_id)
            output = Path(job["output_dir"])
            (output / "video.mp4").write_bytes(b"video")
            (output / "artifact-manifest.json").write_text(
                json.dumps(pipeline.artifact_manifest(output, ["video.mp4"])), encoding="utf-8"
            )
            metadata = {"title": "Private", "description": "Review first", "tags": ["lofi"],
                        "verification": {"passed": True}, "quality_gate": {"passed": True},
                        "files": {"subtitles": None}}
            store.update(job_id, "awaiting_approval", metadata, progress=100)
            pipeline.approve(job_id)
            package = pipeline.prepare_youtube_package(job_id)
            self.assertEqual(package["status"]["privacyStatus"], "private")
            self.assertEqual(package["mode"], "prepared_not_uploaded")
            self.assertFalse(package["automatic_upload_allowed"])
            self.assertTrue((output / "youtube-upload.json").exists())

    def test_profile_duration_is_safely_capped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            job_id = pipeline.create("Vertical rain", 9999, profile="vertical_short")
            self.assertEqual(store.get_job(job_id)["duration"], PROFILES["vertical_short"]["max_duration"])

    def test_starter_scene_selection_is_topic_aware(self):
        self.assertEqual(Pipeline.select_starter_scene("Trem noturno sob chuva", "rain"), "lofi-night-train.jpg")
        self.assertEqual(Pipeline.select_starter_scene("Cabana junto ao lago", "cozy"), "lofi-lakeside-cabin.jpg")
        self.assertEqual(Pipeline.select_starter_scene("Observatório lunar", "cosmic"), "lofi-lunar-observatory.jpg")
        self.assertEqual(Pipeline.select_starter_scene("Apartamento anime original sob chuva", "rain"), "lofi-anime-rainy-apartment.jpg")
        generic = {Pipeline.select_starter_scene(f"Foco silencioso {index}", "focus") for index in range(12)}
        self.assertGreaterEqual(len(generic), 3)

    def test_publishing_center_blocks_untraceable_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            job_id = pipeline.create("Release without rights", 5, profile="preview")
            job = store.get_job(job_id)
            store.update(job_id, "approved", {
                "verification": {"passed": True}, "quality_gate": {"passed": True, "score": 100}
            }, progress=100)
            audit = PublishingCenter(pipeline, store).audit(store.get_job(job_id) or job)
            self.assertFalse(audit["eligible"])
            self.assertIn("Manifesto de direitos não encontrado", audit["blockers"])
            self.assertFalse(audit["automatic_upload_allowed"])

    def test_bilibili_package_is_localized_and_never_uploads(self):
        cafe = BilibiliPackager._localized_identity("Café lo-fi noturno", {})
        self.assertEqual(cafe["scene_zh"], "深夜咖啡馆")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            job_id = pipeline.create("Cabana na neve para dormir", 60, profile="preview")
            job = store.get_job(job_id)
            output = Path(job["output_dir"])
            (output / "video.mp4").write_bytes(b"validated-video")
            metadata = dict(job["metadata"])
            metadata["verification"] = {"passed": True}
            metadata["quality_gate"] = {"passed": True}
            store.update(job_id, "approved", metadata, progress=100)
            (output / "artifact-manifest.json").write_text(
                json.dumps(pipeline.artifact_manifest(output, ["video.mp4"])), encoding="utf-8"
            )

            def fake_command(_args):
                (output / "bilibili-cover.jpg").write_bytes(b"cover" * 300)

            with patch.object(pipeline, "command", side_effect=fake_command):
                package = BilibiliPackager(pipeline, store).prepare(job_id)
            self.assertEqual(package["mode"], "prepared_not_uploaded")
            self.assertFalse(package["automatic_upload_allowed"])
            self.assertIn("雪夜小屋", package["localization"]["titles"]["zh_hans"])
            self.assertIn("Snowy Night Cabin", package["localization"]["titles"]["en"])
            self.assertTrue(package["localization"]["human_review_required"])
            self.assertTrue((output / "bilibili-subtitles-zh-Hans.srt").is_file())
            self.assertTrue((output / "bilibili-subtitles-en.srt").is_file())
            self.assertTrue((output / "bilibili-upload.json").is_file())
            store.add_metrics(job_id, "bilibili", 25, 4, 9)
            self.assertEqual(store.get_job(job_id)["metrics"][0]["platform"], "bilibili")

    def test_vertical_package_requires_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            job_id = pipeline.create("Vertical gate", 5, profile="preview")
            with self.assertRaisesRegex(ValueError, "aprovada"):
                pipeline.prepare_vertical_package(job_id, 30)

    @unittest.skipUnless(FFMPEG.exists(), "FFmpeg portátil não encontrado")
    def test_quality_gate_rejects_black_silent_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            video = root / "bad.mp4"
            pipeline.command([
                str(FFMPEG), "-y", "-f", "lavfi", "-i", "color=black:s=320x180:r=24",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "5",
                "-c:v", "libx264", "-c:a", "aac", str(video),
            ])
            technical = pipeline.inspect_video(video, 5)
            gate = pipeline.quality_gate(video, 5, {"motion": {"camera_motion": "none"}}, technical)
            self.assertFalse(gate["passed"])
            self.assertIn("brightness", gate["failed_check_ids"])
            self.assertIn("motion", gate["failed_check_ids"])
            self.assertIn("audio", gate["failed_check_ids"])

    @unittest.skipUnless(FFMPEG.exists(), "FFmpeg portátil não encontrado")
    def test_preview_render_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / "assets" / "starter", root / "assets" / "starter")
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            job_id = pipeline.create("Render smoke test", 5, profile="preview")
            job = pipeline.run(job_id)
            self.assertEqual(job["status"], "awaiting_approval")
            self.assertEqual(job["progress"], 100)
            self.assertTrue((Path(job["output_dir"]) / "video.mp4").exists())
            self.assertTrue((Path(job["output_dir"]) / "agents.json").exists())
            self.assertTrue((Path(job["output_dir"]) / "thumbnail-design.json").exists())
            self.assertTrue((Path(job["output_dir"]) / "thumbnail-a.jpg").exists())
            self.assertTrue((Path(job["output_dir"]) / "thumbnail-b.jpg").exists())
            self.assertEqual(job["metadata"]["selected_thumbnail"], "a")
            self.assertEqual(job["metadata"]["music"]["style"], "original_lofi_chill")
            self.assertGreaterEqual(job["metadata"]["music"]["bpm"], 70)
            self.assertEqual(job["metadata"]["motion"]["style"], "localized_atmospheric_loop")
            self.assertEqual(job["metadata"]["motion"]["cycle_seconds"], 12)
            self.assertEqual(job["metadata"]["motion"]["camera_motion"], "none")
            self.assertTrue(job["metadata"]["creative_fingerprint"]["scene"])
            fingerprint = job["metadata"]["creative_fingerprint"]
            self.assertIn(fingerprint["music_arrangement"], {item["name"] for item in MUSIC_ARRANGEMENTS})
            self.assertIn(fingerprint["treatment"], {"nocturne_blue", "amber_glow", "violet_dream", "teal_noir",
                                                       "soft_film", "moonlit_silver", "dusk_mauve", "emerald_night"})
            self.assertEqual(fingerprint["novelty"]["candidates_evaluated"], 48)
            self.assertGreaterEqual(fingerprint["novelty"]["score"], 0)
            self.assertGreaterEqual(len(job["metadata"]["music"]["layers"]), 4)
            self.assertTrue((Path(job["output_dir"]) / "motion-overlay.mp4").exists())
            assets = json.loads((Path(job["output_dir"]) / "asset-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(assets[0]["license_type"], "original_ai_generated")
            report = json.loads((Path(job["output_dir"]) / "render-report.json").read_text(encoding="utf-8"))
            manifest = json.loads((Path(job["output_dir"]) / "artifact-manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(report["passed"])
            self.assertTrue(report["atomic_promotion"])
            self.assertFalse((Path(job["output_dir"]) / "video.rendering.mp4").exists())
            self.assertTrue(report["video"]["codec"])
            self.assertTrue(report["audio"]["codec"])
            self.assertTrue(job["metadata"]["quality_gate"]["passed"])
            self.assertEqual(job["metadata"]["quality_gate"]["score"], 100)
            self.assertTrue((Path(job["output_dir"]) / "quality-gate.json").is_file())
            self.assertIn("video.mp4", {item["name"] for item in manifest["files"]})
            self.assertIn("quality-gate.json", {item["name"] for item in manifest["files"]})
            pipeline.select_thumbnail(job_id, "b")
            selected = store.get_job(job_id)
            self.assertEqual(selected["thumbnail_variant"], "b")
            self.assertEqual(selected["metadata"]["selected_thumbnail"], "b")
            design = json.loads((Path(job["output_dir"]) / "thumbnail-design.json").read_text(encoding="utf-8"))
            self.assertEqual(design["selected"], "b")
            self.assertEqual(
                (Path(job["output_dir"]) / "thumbnail.jpg").read_bytes(),
                (Path(job["output_dir"]) / "thumbnail-b.jpg").read_bytes(),
            )
            pipeline.approve(job_id)
            publishing = PublishingCenter(pipeline, store)
            before = publishing.audit(store.get_job(job_id))
            self.assertTrue(before["eligible"])
            self.assertFalse(before["release_ready"])
            release = publishing.prepare(job_id, 5)
            self.assertEqual(release["mode"], "prepared_not_uploaded")
            self.assertFalse(release["automatic_upload_allowed"])
            self.assertEqual(release["destinations"]["youtube"]["privacy"], "private")
            self.assertEqual(release["destinations"]["bilibili"]["upload"], "manual")
            self.assertTrue((Path(job["output_dir"]) / "release-manifest.json").is_file())
            vertical = json.loads((Path(job["output_dir"]) / "vertical-package.json").read_text(encoding="utf-8"))
            self.assertEqual(vertical["resolution"], "720x1280")
            self.assertEqual(vertical["mode"], "prepared_not_uploaded")
            self.assertFalse(vertical["automatic_upload_allowed"])
            self.assertTrue(vertical["validation"]["passed"])
            self.assertEqual(vertical["platforms"]["youtube_shorts"]["upload"], "manual")
            self.assertTrue((Path(job["output_dir"]) / "vertical-short.mp4").is_file())
            self.assertTrue((Path(job["output_dir"]) / "vertical-thumbnail.jpg").is_file())
            self.assertTrue((Path(job["output_dir"]) / "bilibili-cover.jpg").is_file())
            self.assertTrue((Path(job["output_dir"]) / "bilibili-upload.json").is_file())
            queue = publishing.queue()
            self.assertEqual(queue["summary"]["ready"], 1)
            self.assertTrue(queue["items"][0]["release_ready"])

    def test_job_claim_is_atomic_and_blocks_duplicate_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), first)
            job_id = pipeline.create("Reserva atômica", 5, profile="preview")
            second = Store(first.db_path)
            self.assertTrue(first.claim_job(job_id))
            self.assertFalse(second.claim_job(job_id))
            self.assertEqual(second.get_job(job_id)["status"], "planning")

    def test_approval_blocks_video_changed_after_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            job_id = pipeline.create("Integridade antes da aprovação", 5, profile="preview")
            job = store.get_job(job_id)
            output = Path(job["output_dir"])
            video = output / "video.mp4"
            video.write_bytes(b"arquivo-validado")
            (output / "artifact-manifest.json").write_text(
                json.dumps(pipeline.artifact_manifest(output, ["video.mp4"])), encoding="utf-8"
            )
            store.update(job_id, "awaiting_approval", {"quality_gate": {"passed": True}}, progress=100)
            video.write_bytes(b"arquivo-alterado")
            with self.assertRaisesRegex(ValueError, "mudou após a validação"):
                pipeline.approve(job_id)

    @unittest.skipUnless(FFMPEG.exists(), "FFmpeg portátil não encontrado")
    def test_theme_sound_profiles_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            hashes = set()
            for profile in ("rain", "cozy", "cosmic", "focus"):
                output = root / f"{profile}.wav"
                music = pipeline.create_ambient_audio(output, 2, profile, f"unique {profile}")
                self.assertTrue(output.is_file())
                self.assertGreater(output.stat().st_size, 10_000)
                self.assertEqual(music["style"], "original_lofi_chill")
                hashes.add(hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(len(hashes), 4)

    def test_motion_recipes_change_with_the_atmosphere(self):
        filters = {}
        recipes = {}
        for profile in ("rain", "cozy", "cosmic", "focus"):
            filters[profile], recipes[profile] = Pipeline.visual_motion(profile, 960, 540, 24)
            self.assertNotIn("zoompan", filters[profile])
            self.assertEqual(recipes[profile]["camera_motion"], "none")
            self.assertEqual(recipes[profile]["source_policy"], "original_or_commercially_licensed")
        self.assertEqual(len(set(recipe["effects"][0] for recipe in recipes.values())), 3)
        self.assertEqual(recipes["cosmic"]["atmosphere"], "estrelas pulsantes")

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
                self.assertEqual(dashboard["creative"]["engine"], "creative_dna_v2")
                creative = json.load(urllib.request.urlopen(base + "/api/creative-system"))
                self.assertGreaterEqual(creative["catalog"]["candidate_space"], 25_000)
                series = json.load(urllib.request.urlopen(base + "/api/series"))
                self.assertGreaterEqual(len(series), 4)
                insights = json.load(urllib.request.urlopen(base + "/api/insights"))
                self.assertEqual(insights, [])
                publishing = json.load(urllib.request.urlopen(base + "/api/publishing"))
                self.assertEqual(publishing["mode"], "manual-safe")
                self.assertFalse(publishing["automatic_upload_allowed"])
                self.assertEqual(publishing["summary"]["total"], 0)
                platforms = json.load(urllib.request.urlopen(base + "/api/platforms"))
                self.assertEqual(platforms["mode"], "manual-safe")
                self.assertFalse(platforms["automatic_upload_allowed"])
                self.assertEqual(platforms["total"], 6)
                self.assertTrue(all("secret" not in key for item in platforms["platforms"] for key in item))
                planned = {item["id"]: item for item in platforms["platforms"] if item["state"] == "planned"}
                self.assertEqual(planned, {})
                bilibili = next(item for item in platforms["platforms"] if item["id"] == "bilibili")
                self.assertEqual(bilibili["state"], "package_ready")
                self.assertTrue(bilibili["package_ready"])
                self.assertFalse(bilibili["upload_enabled"])
                pinterest = next(item for item in platforms["platforms"] if item["id"] == "pinterest")
                self.assertEqual(pinterest["state"], "package_ready")
                self.assertTrue(pinterest["package_ready"])
                self.assertFalse(pinterest["upload_enabled"])
                serialized_platforms = json.dumps(platforms)
                self.assertNotIn("client-secret", serialized_platforms)
                commerce = json.load(urllib.request.urlopen(base + "/api/commerce-center"))
                self.assertEqual(commerce["summary"]["products"], 0)
                self.assertFalse(commerce["automatic_upload_allowed"])
                product_request = urllib.request.Request(
                    base + "/api/commerce-center/products",
                    data=json.dumps({"product_id": "API-1", "title": "Produto API",
                                     "product_url": "https://shopee.com.br/produto/api-1",
                                     "affiliate_url": "https://s.shopee.com.br/api-1", "price": 25,
                                     "exact_product_confirmed": True, "affiliate_disclosure": True,
                                     "assets": [{"name": "Asset próprio", "license_type": "original", "approved": True}]}).encode(),
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                product = json.load(urllib.request.urlopen(product_request))
                self.assertEqual(product["status"], "validated")
                campaign_request = urllib.request.Request(
                    base + "/api/commerce-center/campaigns",
                    data=json.dumps({"product_id": product["id"], "name": "Campanha API",
                                     "destination": "shopee_video", "cost": 5}).encode(),
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                campaign = json.load(urllib.request.urlopen(campaign_request))
                self.assertEqual(campaign["status"], "draft")
                backups = json.load(urllib.request.urlopen(base + "/api/system/backups"))
                self.assertGreaterEqual(len(backups), 1)
                preflight_request = urllib.request.Request(
                    base + "/api/integrations/youtube/preflight", data=b"{}",
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                preflight = json.load(urllib.request.urlopen(preflight_request))
                self.assertFalse(preflight["network_contacted"])
                self.assertFalse(preflight["upload_performed"])
                deliveries = json.load(urllib.request.urlopen(base + "/api/integrations/deliveries"))
                self.assertEqual(deliveries[0]["platform"], "youtube")
                audit = json.load(urllib.request.urlopen(base + "/api/integrations/audit"))
                self.assertEqual(audit[0]["event"], "preflight")
                autopilot = json.load(urllib.request.urlopen(base + "/api/autopilot"))
                self.assertEqual(autopilot["mode"], "off")
                autopilot_request = urllib.request.Request(
                    base + "/api/autopilot",
                    data=json.dumps({"enabled": True, "series_ids": ["rainy_places"], "cadence": 2,
                                     "publish_hour": "19:00", "duration": 1200}).encode(),
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                configured = json.load(urllib.request.urlopen(autopilot_request))
                self.assertTrue(configured["enabled"])
                self.assertEqual(configured["planned"], 2)
                night = json.load(urllib.request.urlopen(base + "/api/night-shift"))
                self.assertEqual(night["mode"], "off")
                night_request = urllib.request.Request(
                    base + "/api/night-shift",
                    data=json.dumps({"enabled": True, "start_hour": "22:00", "end_hour": "07:00",
                                     "batch_limit": 2}).encode(),
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                night = json.load(urllib.request.urlopen(night_request))
                self.assertTrue(night["enabled"])
                self.assertEqual(night["batch_limit"], 2)
                request = urllib.request.Request(base + "/api/jobs", data=b'{"topic":"x"}', headers={"Content-Type": "application/json"}, method="POST")
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request)
                self.assertEqual(error.exception.code, 400)
                error_payload = json.loads(error.exception.read())
                self.assertEqual(error_payload["code"], "INVALID_REQUEST")
                self.assertTrue(error_payload["request_id"])
                error.exception.close()
                invalid_limit = urllib.request.Request(base + "/api/jobs?limit=wrong")
                with self.assertRaises(urllib.error.HTTPError) as invalid:
                    urllib.request.urlopen(invalid_limit)
                self.assertEqual(invalid.exception.code, 400)
                self.assertEqual(json.loads(invalid.exception.read())["code"], "INVALID_REQUEST")
                invalid.exception.close()
                put = urllib.request.Request(base + "/api/jobs", data=b"{}", method="PUT")
                with self.assertRaises(urllib.error.HTTPError) as unsupported:
                    urllib.request.urlopen(put)
                self.assertEqual(unsupported.exception.code, 405)
                self.assertEqual(json.loads(unsupported.exception.read())["code"], "METHOD_NOT_ALLOWED")
                unsupported.exception.close()
                with self.assertRaises(urllib.error.HTTPError) as traversal:
                    urllib.request.urlopen(base + "/%2e%2e/.env.example")
                self.assertEqual(traversal.exception.code, 404)
                traversal.exception.close()
            finally:
                server.shutdown()
                server.server_close()

    def test_api_internal_errors_are_traceable_without_leaking_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            server = create_server(pipeline, store, "127.0.0.1", 0, ROOT / "web")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                with patch.object(store, "summary", side_effect=RuntimeError("DO_NOT_LEAK_THIS")):
                    with self.assertRaises(urllib.error.HTTPError) as failure:
                        urllib.request.urlopen(base + "/api/dashboard")
                    payload = json.loads(failure.exception.read())
                    self.assertEqual(failure.exception.code, 500)
                    self.assertEqual(payload["code"], "INTERNAL_ERROR")
                    self.assertTrue(payload["request_id"])
                    self.assertNotIn("DO_NOT_LEAK_THIS", json.dumps(payload))
                    failure.exception.close()
            finally:
                server.shutdown()
                server.server_close()

    def test_frontend_scripts_use_one_detail_extension_runner(self):
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        scripts = re.findall(r'<script src="/([^\"]+\.js)"></script>', index)
        self.assertTrue(scripts)
        self.assertEqual(len(scripts), len(set(scripts)))
        self.assertTrue(all((ROOT / "web" / script).is_file() for script in scripts))
        for name in ("phase3.js", "phase7.js", "phase8.js", "phase9.js", "phase10.js"):
            source = (ROOT / "web" / name).read_text(encoding="utf-8")
            self.assertIn("registerJobDetailExtension", source)
            self.assertNotIn("openJob=", source)
        runner = (ROOT / "web" / "phase13.js").read_text(encoding="utf-8")
        self.assertIn("openJob=async function", runner)
        self.assertLess(index.index('/phase14.js'), index.index('/phase13.js'))
        self.assertLess(index.index('/phase15.js'), index.index('/phase13.js'))
        self.assertIn('id="commerce"', index)
        commerce_ui = (ROOT / "web" / "phase15.js").read_text(encoding="utf-8")
        integrations_ui = (ROOT / "web" / "phase14.js").read_text(encoding="utf-8")
        self.assertIn("data-pinterest-package", commerce_ui)
        self.assertIn("pinterest-package", commerce_ui)
        self.assertIn("package_ready:'PACOTE LOCAL PRONTO'", integrations_ui)
        publishing_ui = (ROOT / "web" / "phase12.js").read_text(encoding="utf-8")
        self.assertIn("bilibili_manual", publishing_ui)

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
