import base64
import json
import hashlib
import math
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
import wave
from array import array
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
from factory.lyria import LYRIA_MODELS
from factory.music_sources import FLOW_MUSIC_PROMPTS, flow_music_guide
from factory.nightshift import NightShift
from factory.pipeline import COVER_MOTION, Pipeline, STARTER_SCENES, safe_slug, srt_timestamp
from factory.publishing import PublishingCenter
from factory.store import Store
from factory.teams import SHARED_SKILLS, skill_catalog, team_catalog
from factory.templates import series_catalog
from factory.web import CalendarScheduler, create_server
from factory.vault import SecureVault
from factory.visual_style import (COVER_STYLE_ID, cover_assets, cover_reference,
                                  select_cover_references, visual_direction)


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
        self.assertTrue(plan["seo"]["title"].isascii())
        self.assertEqual(plan["compliance"]["publish_mode"], "manual_safe")
        self.assertEqual(plan["visual"]["sound_profile"], "rain")
        self.assertIn("lo-fi", plan["visual"]["sound"].lower())
        self.assertIn("Lo-fi", plan["seo"]["title"])
        self.assertNotIn("Duração", plan["seo"]["description"])
        self.assertGreaterEqual(len(ContentCrew().ideas()), 5)
        self.assertEqual(plan["visual"]["thumbnail"]["style_id"], COVER_STYLE_ID)
        self.assertNotIn("faixa escura", plan["visual"]["thumbnail"]["composition"])

    def test_approved_cover_collection_is_semantic_and_minimal(self):
        assets = cover_assets(ROOT)
        self.assertEqual(len(assets), 9)
        pair = select_cover_references(ROOT, "Café japonês sob chuva para descansar")
        self.assertIsNotNone(pair)
        assert pair is not None
        self.assertNotEqual(pair[0]["id"], pair[1]["id"])
        self.assertTrue(any("cafe" in item["id"] or "konbini" in item["id"] for item in pair))
        direction = visual_direction()
        self.assertEqual(direction["id"], COVER_STYLE_ID)
        self.assertIn("single short lowercase word", direction["typography"])
        self.assertIn("rain belongs outdoors", direction["weather"])

    def test_cover_selection_excludes_recent_primary_references(self):
        excluded: set[str] = set()
        selected: list[str] = []
        for index in range(9):
            pair = select_cover_references(ROOT, f"Cena noturna original {index}", excluded)
            self.assertIsNotNone(pair)
            assert pair is not None
            selected.append(pair[0]["id"])
            excluded.add(pair[0]["id"])
        self.assertEqual(len(set(selected)), 9)
        self.assertIsNone(select_cover_references(ROOT, "Coleção esgotada", excluded))

    def test_thumbnail_variants_cannot_show_a_different_scene_after_play(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cover_source = ROOT / "assets" / "covers" / COVER_STYLE_ID.replace("_", "-")
            cover_target = root / "assets" / "covers" / COVER_STYLE_ID.replace("_", "-")
            shutil.copytree(cover_source, cover_target)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            out = root / "data" / "jobs" / "same-scene"
            out.mkdir(parents=True)
            pair = select_cover_references(root, "Observatório sob a aurora")
            assert pair is not None
            canonical = cover_reference(root, pair[0]["id"])
            assert canonical is not None

            def copy_thumbnail(source: Path, output: Path, width: int, height: int) -> None:
                del width, height
                shutil.copy2(source, output)

            with patch.object(pipeline, "create_thumbnail", side_effect=copy_thumbnail):
                design = pipeline.create_thumbnail_variants(
                    out, "Observatório sob a aurora", 1280, 720,
                    Path(canonical["path"]), canonical_cover=canonical,
                )

            self.assertEqual(design["variants"][0]["reference_id"], canonical["id"])
            self.assertEqual(design["variants"][1]["reference_id"], canonical["id"])
            self.assertEqual((out / "thumbnail-a.jpg").read_bytes(), Path(canonical["path"]).read_bytes())
            self.assertEqual((out / "thumbnail-b.jpg").read_bytes(), Path(canonical["path"]).read_bytes())
            self.assertEqual((out / "thumbnail.jpg").read_bytes(), Path(canonical["path"]).read_bytes())

    def test_thumbnail_batch_uses_nine_collection_covers_then_unique_scene(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cover_source = ROOT / "assets" / "covers" / COVER_STYLE_ID.replace("_", "-")
            cover_target = root / "assets" / "covers" / COVER_STYLE_ID.replace("_", "-")
            shutil.copytree(cover_source, cover_target)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            job_ids = []
            for index in range(10):
                job_id = f"thumbnail-batch-{index}"
                out = root / "data" / "outputs" / job_id
                out.mkdir(parents=True)
                (out / f"scene-{index}.jpg").write_bytes(f"unique-production-scene-{index}".encode())
                (out / "thumbnail.jpg").write_bytes(b"old")
                store.create_job({
                    "id": job_id, "topic": f"Cena noturna {index}", "duration": 1800,
                    "narration": False, "subtitles": False, "output_dir": str(out),
                    "profile": "youtube_long",
                })
                store.update(job_id, "awaiting_approval", {"files": {}}, progress=100, quality_score=100)
                job_ids.append(job_id)

            def copy_thumbnail(source: Path, output: Path, width: int, height: int) -> None:
                del width, height
                shutil.copy2(source, output)

            with patch.object(pipeline, "create_thumbnail", side_effect=copy_thumbnail):
                result = pipeline.rebalance_thumbnail_batch(job_ids)

            self.assertEqual(result["count"], 10)
            self.assertEqual(result["unique_collection_covers"], 9)
            selected_refs = []
            selected_hashes = []
            for job_id in job_ids:
                job = store.get_job(job_id)
                assert job is not None
                selected_refs.append(job["metadata"]["thumbnail_variants"][0]["reference_id"])
                selected_hashes.append(hashlib.sha256((Path(job["output_dir"]) / "thumbnail.jpg").read_bytes()).hexdigest())
                self.assertEqual(job["status"], "awaiting_approval")
                self.assertTrue((Path(job["output_dir"]) / "artifact-manifest.json").is_file())
            self.assertEqual(len(set(selected_refs[:9])), 9)
            self.assertEqual(selected_refs[9], "production-scene")
            self.assertEqual(len(set(selected_hashes)), 10)
            self.assertTrue(Path(result["backup_dir"]).is_dir())

    def test_thumbnail_batch_rejects_duplicates_before_touching_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            out = root / "data" / "jobs" / "duplicate"
            out.mkdir(parents=True)
            thumbnail = out / "thumbnail.jpg"
            thumbnail.write_bytes(b"untouched")
            (out / "background.jpg").write_bytes(b"scene")
            store.create_job({
                "id": "duplicate", "topic": "Cena duplicada", "duration": 1800,
                "narration": False, "subtitles": False, "output_dir": str(out),
            })
            store.update("duplicate", "awaiting_approval", {}, progress=100)
            with self.assertRaisesRegex(ValueError, "duplicadas"):
                pipeline.rebalance_thumbnail_batch(["duplicate", "duplicate"])
            self.assertEqual(thumbnail.read_bytes(), b"untouched")

    def test_flow_music_guide_offers_distinct_safe_prompts(self):
        guide = flow_music_guide()
        self.assertEqual(guide["mode"], "official_link_bridge_with_api_option")
        self.assertEqual(len(FLOW_MUSIC_PROMPTS), 12)
        self.assertEqual(len({item["name"] for item in FLOW_MUSIC_PROMPTS}), 12)
        self.assertEqual(len({item["prompt"] for item in FLOW_MUSIC_PROMPTS}), 12)
        self.assertGreaterEqual(len({re.search(r"(\d+) BPM", item["prompt"]).group(1)
                                     for item in FLOW_MUSIC_PROMPTS}), 10)
        self.assertGreaterEqual(sum("No piano" in item["prompt"] for item in FLOW_MUSIC_PROMPTS), 5)
        for item in FLOW_MUSIC_PROMPTS:
            self.assertIn("no vocals", item["prompt"])
            self.assertIn("no artist imitation", item["prompt"])

    def test_lyria_key_is_encrypted_and_never_returned_by_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            key = "fake-test-key-long-enough-for-validation-only"
            status = pipeline.lyria.configure(key)
            self.assertTrue(status["configured"])
            self.assertEqual(status["key_source"], "encrypted_vault")
            self.assertNotIn(key, json.dumps(status))
            vault = root / "data" / "private" / "music-providers.vault"
            self.assertTrue(vault.is_file())
            self.assertNotIn(key.encode(), vault.read_bytes())

    def test_lyria_generation_registers_validated_provider_track(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            pipeline.lyria.configure("fake-test-key-long-enough-for-validation-only")
            response = {"steps": [{"type": "model_output", "content": [{
                "type": "audio", "mime_type": "audio/mpeg", "data": base64.b64encode(b"ID3-test-audio").decode(),
            }]}]}
            with patch.object(pipeline.lyria, "_call_api", return_value=response) as request, \
                 patch.object(pipeline.lyria, "_validate_audio") as validate:
                result = pipeline.lyria.generate(
                    "Midnight Rhodes", "Warm Rhodes lo-fi at 72 BPM for late night focus",
                    "lyria-3-pro-preview", True,
                )
            request_prompt = request.call_args.args[2]
            self.assertIn("Instrumental only", request_prompt)
            self.assertEqual(result["price_estimate_usd"], LYRIA_MODELS["lyria-3-pro-preview"]["price_usd"])
            validate.assert_called_once()
            track = store.get_music_asset(result["id"])
            self.assertEqual(track["license_type"], "provider_generated")
            self.assertTrue(Path(track["path"]).is_file())

    def test_lyria_batch_uses_distinct_directions_and_reports_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            service = Pipeline(self.settings(root), store).lyria
            service.configure("fake-test-key-long-enough-for-validation-only")
            with patch.object(service, "generate", side_effect=lambda name, prompt, model, rights: {
                "id": len(name), "name": name, "model": model, "price_estimate_usd": 0.08,
            }) as generate:
                result = service.generate_batch(list(FLOW_MUSIC_PROMPTS), "lyria-3-pro-preview", True, 4)
            self.assertEqual(result["requested"], 4)
            self.assertEqual(result["generated"], 4)
            self.assertEqual(result["failed"], 0)
            self.assertEqual(result["price_estimate_usd"], 0.32)
            self.assertEqual(generate.call_count, 4)
            self.assertEqual([item["name"] for item in result["items"]],
                             [item["name"] for item in FLOW_MUSIC_PROMPTS[:4]])

    def test_lyria_generation_requires_connection_rights_and_known_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            service = Pipeline(self.settings(root), store).lyria
            with self.assertRaisesRegex(ValueError, "Confirme"):
                service.generate("Track", "A sufficiently detailed instrumental prompt", "lyria-3-pro-preview", False)
            service.configure("fake-test-key-long-enough-for-validation-only")
            with self.assertRaisesRegex(ValueError, "Modelo"):
                service.generate("Track", "A sufficiently detailed instrumental prompt", "unknown", True)

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

    def test_creative_director_keeps_the_semantic_scene_priority(self):
        director = CreativeDirector()
        dna = director.plan(
            "Trem noturno para foco", "rain", "youtube_long",
            ("lofi-night-train.jpg", "lofi-rooftop-greenhouse.jpg", "lofi-rainy-cafe.jpg"), [], [],
        )
        self.assertEqual(dna["scene"], "lofi-night-train.jpg")

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

    def test_direct_asset_requires_explicit_commercial_rights(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "scene.jpg"
            image.write_bytes(b"placeholder")
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            with self.assertRaisesRegex(ValueError, "direitos comerciais"):
                pipeline.create("Cena própria", 5, profile="preview", source_asset=str(image))
            job_id = pipeline.create(
                "Cena própria", 5, profile="preview", source_asset=str(image),
                source_asset_rights_confirmed=True,
            )
            asset = store.get_job(job_id)["source_assets"][0]
            self.assertTrue(asset["approved"])
            self.assertTrue(asset["rights_confirmed"])

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

    def test_commerce_brief_rejects_lookalike_domains(self):
        product = {"product_id": "123", "title": "Produto", "product_url": "https://evilshopee.com.br/item/123",
                   "exact_product_confirmed": True, "affiliate_disclosure": True,
                   "assets": [{"name": "Demo", "license_type": "original", "approved": True}]}
        result = validate_commerce_brief(product)
        self.assertFalse(result["passed"])
        self.assertTrue(any("Shopee Brasil" in error for error in result["errors"]))
        product["product_url"] = "https://loja.shopee.com.br/item/123"
        self.assertTrue(validate_commerce_brief(product)["passed"])

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

    def test_legacy_template_plans_are_archived_without_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "factory.db"
            store = Store(database)
            item_id = store.add_calendar_item(
                "Old cosmic plan", "cosmic_focus", "youtube_long", 3600, "2099-09-01T19:00"
            )
            refreshed = Store(database)
            item = next(entry for entry in refreshed.list_calendar() if entry["id"] == item_id)
            self.assertEqual(item["status"], "archived")
            self.assertIsNone(item["job_id"])
            self.assertEqual(
                refreshed.get_autopilot()["series_ids"],
                ["japan_after_rain", "city_after_dark", "rainy_refuges"],
            )

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
            due_id = store.add_calendar_item("Due ambience", None, "preview", 5, "2020-01-01T10:00",
                                             team_id="bilibili_lab")
            future_id = store.add_calendar_item("Future ambience", None, "preview", 5, "2099-01-01T10:00")
            runner = CapturingRunner()
            autopilot = Autopilot(self.settings(root), store)
            created = CalendarScheduler(pipeline, store, runner, autopilot).run_once()
            calendar = {item["id"]: item for item in store.list_calendar()}
            self.assertEqual(len(created), 1)
            self.assertEqual(runner.submitted, created)
            self.assertEqual(calendar[due_id]["status"], "producing")
            self.assertEqual(calendar[due_id]["job_id"], created[0])
            self.assertEqual(store.get_job(created[0])["team_id"], "bilibili_lab")
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
            self.assertEqual({item["series_id"] for item in calendar}, {"japan_after_rain", "rainy_refuges"})
            self.assertEqual(len({item["topic"] for item in calendar}), 3)
            self.assertTrue(all(item["duration"] == 1800 for item in calendar))

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
            self.assertTrue(result["cohort_id"].startswith("phase2-"))
            self.assertEqual(len(runner.active), 2)
            self.assertEqual({store.get_job(job_id)["cohort_id"] for job_id in result["created"]},
                             {result["cohort_id"]})
            self.assertEqual(sum(item["status"] == "producing" for item in store.list_calendar()), 2)

            report = night.daily_report()
            self.assertEqual(report["summary"]["active"], 2)
            self.assertEqual(report["summary"]["blocked"], 0)
            self.assertFalse(report["publish_performed"])
            self.assertIn("andamento", report["next_action"])

    def test_night_shift_blocks_phase2_until_ten_pilot_approvals(self):
        class FakeRunner:
            @staticmethod
            def snapshot():
                return {"active": [], "worker_limit": 1}

            @staticmethod
            def submit(_job_id):
                raise AssertionError("A Fase 2 não deveria iniciar")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            autopilot = Autopilot(self.settings(root), store)
            for index in range(10):
                job_id = pipeline.create(f"Piloto humano {index}", 1800, cohort_id="pilot-explicit")
                store.update(job_id, "awaiting_approval")
            night = NightShift(pipeline, store, FakeRunner(), autopilot)
            result = night.run_once(force=True)
            self.assertEqual(result["created"], [])
            self.assertIn("Aprove 10 vídeo(s)", result["reason"])
            self.assertEqual(night.phase2_certification()["status"], "blocked_by_pilot")

    def test_phase2_certification_requires_three_integral_autonomous_batches(self):
        class FakeRunner:
            @staticmethod
            def snapshot():
                return {"active": [], "worker_limit": 1}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            night = NightShift(pipeline, store, FakeRunner(), Autopilot(self.settings(root), store))
            for batch in range(3):
                job_id = pipeline.create(f"Lote autônomo {batch}", 1800,
                                         cohort_id=f"phase2-2026-09-0{batch + 1}-220000")
                job = store.get_job(job_id)
                out = Path(job["output_dir"])
                (out / "video.mp4").write_bytes(f"video-{batch}".encode())
                (out / "publication-package.json").write_text("{}", encoding="utf-8")
                manifest = pipeline.artifact_manifest(out, ["video.mp4", "publication-package.json"])
                (out / "artifact-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
                store.update(job_id, "awaiting_approval", metadata={
                    "verification": {"passed": True}, "quality_gate": {"passed": True},
                })
            certification = night.phase2_certification()
            self.assertEqual(certification["status"], "certified")
            self.assertEqual(certification["consecutive_successful_batches"], 3)
            self.assertEqual(certification["remaining_batches"], 0)
            self.assertTrue(all(not batch["publish_performed"] for batch in certification["batches"]))

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

    def test_library_readiness_requires_real_files_and_variety_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            starter = root / "assets" / "starter"
            starter.mkdir(parents=True)
            for index in range(12):
                (starter / f"scene-{index:02}.jpg").write_bytes(b"original-scene")
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(replace(self.settings(root), music_catalog_human_approved=True), store)
            for index in range(12):
                track = root / f"track-{index:02}.wav"
                track.write_bytes(b"original-track")
                store.add_music_asset(f"Track {index}", str(track), "original", None, None, True)
            readiness = pipeline.library_readiness()
            self.assertTrue(readiness["ready"])
            self.assertEqual(readiness["music_tracks"], 12)
            self.assertEqual(readiness["starter_scenes"], 12)

    def test_music_listening_review_is_persistent_and_rejected_tracks_leave_rotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            starter = root / "assets" / "starter"
            starter.mkdir(parents=True)
            for index in range(12):
                (starter / f"scene-{index:02}.jpg").write_bytes(b"original-scene")
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            track_ids = []
            for index in range(12):
                track = root / f"flow-{index:02}.mp3"
                track.write_bytes(b"ID3-provider-track")
                track_ids.append(store.add_music_asset(
                    f"Flow {index}", str(track), "provider_generated",
                    "https://www.flowmusic.app/", "Google AI Plus", True,
                ))
            self.assertFalse(pipeline.library_readiness()["ready"])
            for track_id in track_ids:
                reviewed = store.review_music_asset(track_id, "approved")
                self.assertEqual(reviewed["human_review"], "approved")
            self.assertTrue(pipeline.library_readiness()["ready"])
            rejected = store.review_music_asset(track_ids[-1], "rejected")
            self.assertFalse(rejected["approved"])
            self.assertEqual(rejected["human_review"], "rejected")
            self.assertEqual(len(store.list_music_assets(approved_only=True)), 11)
            self.assertFalse(pipeline.library_readiness()["ready"])

    def test_original_music_bootstrap_registers_distinct_traceable_tracks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            result = pipeline.bootstrap_original_music_catalog(target_count=2, duration_seconds=16)
            tracks = store.list_music_assets(approved_only=True)
            manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(result["registered"], 2)
            self.assertEqual(len(tracks), 2)
            self.assertEqual(len({item["sha256"] for item in manifest["tracks"]}), 2)
            self.assertTrue(all(item["license"] == "original" for item in manifest["tracks"]))

    def test_rejecting_music_quarantines_linked_publishable_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            track = root / "repetitive.mp3"
            track.write_bytes(b"ID3-repetitive")
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            track_id = store.add_music_asset(
                "Repetitive track", str(track), "provider_generated", "https://example.test", None, True
            )
            store.review_music_asset(track_id, "approved")
            job_id = pipeline.create("Long night", 1800, music_asset_id=track_id)
            store.update(job_id, "approved", {
                "music": {"style": "licensed_music_library", "track_id": track_id,
                          "track_name": "Repetitive track"},
                "verification": {"passed": True}, "quality_gate": {"passed": True, "score": 100},
            }, progress=100)

            rejected = store.review_music_asset(track_id, "rejected")

            self.assertEqual(rejected["invalidated_jobs"], [job_id])
            job = store.get_job(job_id)
            self.assertEqual(job["status"], "rejected")
            self.assertIn("reprovada", job["error"])
            audit = PublishingCenter(pipeline, store).audit(job)
            self.assertFalse(audit["eligible"])
            self.assertTrue(any(check["id"] == "music" and not check["passed"] for check in audit["checks"]))

    def test_long_video_never_falls_back_to_synthetic_music(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            job_id = pipeline.create("No approved music", 1800)
            job = store.get_job(job_id)
            self.assertIsNone(store.reserve_music_asset())
            self.assertIsNone(job["music_asset_id"])

    def test_legacy_synthetic_jobs_can_be_quarantined_without_deleting_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            job_id = pipeline.create("Old synthetic package", 1800)
            output = Path(store.get_job(job_id)["output_dir"])
            artifact = output / "video.mp4"
            artifact.write_bytes(b"preserved")
            store.update(job_id, "approved", {
                "music": {"style": "original_lofi_chill", "bpm": 72},
            }, progress=100)

            self.assertEqual(store.quarantine_legacy_music_jobs(), [job_id])
            self.assertEqual(store.get_job(job_id)["status"], "rejected")
            self.assertEqual(artifact.read_bytes(), b"preserved")

    def test_pilot_cohort_archives_historical_jobs_without_deleting_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            current = pipeline.create("Current pilot", 1800)
            historical = pipeline.create("Historical package", 1800)
            current_out = Path(store.get_job(current)["output_dir"])
            historical_out = Path(store.get_job(historical)["output_dir"])
            (current_out / "video.mp4").write_bytes(b"current")
            (historical_out / "video.mp4").write_bytes(b"historical")
            store.update(current, "awaiting_approval", {}, progress=100)
            store.update(historical, "awaiting_approval", {}, progress=100)

            result = store.establish_pilot_cohort("pilot-test", [current], [current, historical])

            self.assertEqual(result["tagged"], [current])
            self.assertEqual(result["quarantined"], [historical])
            self.assertEqual(store.get_job(current)["cohort_id"], "pilot-test")
            self.assertEqual(store.get_job(historical)["status"], "rejected")
            self.assertEqual((historical_out / "video.mp4").read_bytes(), b"historical")

    def test_artifact_manifest_never_hashes_itself_and_validates_every_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "video.mp4").write_bytes(b"video")
            (out / "metadata.json").write_bytes(b"metadata")
            manifest = Pipeline.artifact_manifest(
                out, ["video.mp4", "metadata.json", "artifact-manifest.json"],
            )
            (out / "artifact-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            self.assertNotIn("artifact-manifest.json", [item["name"] for item in manifest["files"]])
            self.assertEqual(Pipeline.verify_artifact_manifest(out)["count"], 2)
            (out / "metadata.json").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "metadata.json"):
                Pipeline.verify_artifact_manifest(out)

    @unittest.skipUnless(FFMPEG.exists(), "FFmpeg portátil não encontrado")
    def test_legacy_cover_migration_is_recoverable_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / "assets" / "covers", root / "assets" / "covers")
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            job_id = pipeline.create("Rainy vinyl room", 15, profile="preview")
            job = store.get_job(job_id)
            out = Path(job["output_dir"])
            for name in ("thumbnail.jpg", "thumbnail-a.jpg", "thumbnail-b.jpg", "background.jpg"):
                shutil.copy2(ROOT / "assets" / "covers" / "nocturnal-rain-v1" / "rainy-konbini-clean.png", out / name)
            old_design = {"selected": "b", "variants": []}
            (out / "thumbnail-design.json").write_text(json.dumps(old_design), encoding="utf-8")
            (out / "metadata.json").write_text(json.dumps({"selected_thumbnail": "b"}), encoding="utf-8")
            (out / "artifact-manifest.json").write_text(json.dumps({"files": []}), encoding="utf-8")
            store.update(job_id, "awaiting_approval", {"selected_thumbnail": "b"}, progress=100)
            before = hashlib.sha256((out / "thumbnail.jpg").read_bytes()).hexdigest()
            result = pipeline.migrate_existing_covers()
            self.assertEqual(result["count"], 1)
            design = json.loads((out / "thumbnail-design.json").read_text(encoding="utf-8"))
            self.assertEqual(design["style_id"], COVER_STYLE_ID)
            self.assertEqual(design["selected"], "b")
            backup = Path(result["backup_dir"]) / job_id / "thumbnail.jpg"
            self.assertTrue(backup.is_file())
            self.assertEqual(hashlib.sha256(backup.read_bytes()).hexdigest(), before)
            self.assertEqual(pipeline.migrate_existing_covers()["count"], 0)

    @unittest.skipUnless(FFMPEG.exists(), "FFmpeg portátil não encontrado")
    def test_music_library_rotates_least_used_tracks_and_renders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            tracks = []
            for index, frequency in enumerate((220, 330)):
                path = root / f"track-{index}.wav"
                with wave.open(str(path), "wb") as output:
                    output.setnchannels(1);output.setsampwidth(2);output.setframerate(22050)
                    samples = array("h", (int(math.sin(2 * math.pi * frequency * i / 22050) * 5000)
                                          for i in range(22050)))
                    output.writeframes(samples.tobytes())
                tracks.append(store.add_music_asset(f"Track {index}", str(path), "original", None, None, True))
                store.review_music_asset(tracks[-1], "approved")
            first = store.reserve_music_asset()
            second = store.reserve_music_asset()
            third = store.reserve_music_asset()
            self.assertEqual([first["id"], second["id"], third["id"]], [tracks[0], tracks[1], tracks[0]])
            rendered = root / "library.wav"
            metadata = pipeline.create_library_audio(rendered, 2, "focus", {**second, "preferred": False})
            self.assertTrue(rendered.is_file())
            self.assertEqual(metadata["style"], "licensed_music_library")
            self.assertEqual(metadata["selection"], "least_used_rotation")

    def test_flow_catalog_can_reversibly_replace_synthetic_rotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "factory.db")
            synthetic = root / "synthetic.wav"
            flow = root / "flow.mp3"
            synthetic.touch()
            flow.touch()
            source = "generated-locally://faceless-factory/original-lofi-v1"
            synthetic_id = store.add_music_asset("Synthetic", str(synthetic), "original", source, None, True)
            flow_id = store.add_music_asset("Flow", str(flow), "provider_generated",
                                            "https://www.flowmusic.app/", "Google AI Plus", True)
            self.assertEqual(store.archive_music_assets_by_source(source), 1)
            active = {item["id"] for item in store.list_music_assets(approved_only=True)}
            self.assertNotIn(synthetic_id, active)
            self.assertIn(flow_id, active)
            self.assertTrue(synthetic.is_file())

    def test_public_interface_only_offers_long_videos_and_friendly_artifacts(self):
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn('<option value="preview">', index)
        self.assertNotIn('<option value="vertical_short">', index)
        self.assertIn('1 hora · recomendado', index)
        self.assertIn('30 minutos', index)
        self.assertIn('data-artifact="metadata.json"', app)
        self.assertIn('FFACTORY — Autonomous Mood Studio', index)
        self.assertIn('https://www.flowmusic.app/', app)
        self.assertIn('/api/music-assets/${Number(track.id)}/preview', app)
        self.assertIn('/api/music-assets/${Number(button.dataset.trackId)}/review', app)
        self.assertIn('Aprovar faixa', app)
        self.assertIn('3AM Shelter', index)
        self.assertIn('https://www.youtube.com/channel/UCaxI2elEbTGftx6QIXNhvsw', index)
        self.assertNotIn('/api/channel-assets/pausa-pra-anime-youtube-banner-2560x1440.png', index)
        self.assertNotIn('target="_blank" rel="noopener">Metadados', app)

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
            self.assertIn("Lo-fi", pipeline.generate_plan("Night rain", 15, "preview")["seo"]["title"])

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
            long_id = pipeline.create("Nunca menos de trinta minutos", 30, profile="youtube_long")
            preview_id = pipeline.create("Prévia curta", 1, profile="preview")
            self.assertEqual(store.get_job(long_id)["duration"], 1800)
            self.assertEqual(store.get_job(preview_id)["duration"], 5)

    def test_starter_scene_selection_is_topic_aware(self):
        self.assertEqual(Pipeline.select_starter_scene("Trem noturno sob chuva", "rain"), "lofi-night-train.jpg")
        self.assertEqual(Pipeline.select_starter_scene("Café silencioso ao amanhecer", "focus"), "lofi-rainy-cafe.jpg")
        self.assertEqual(Pipeline.select_starter_scene("Cabana junto ao lago", "cozy"), "lofi-lakeside-cabin.jpg")
        self.assertEqual(Pipeline.select_starter_scene("Observatório lunar", "cosmic"), "lofi-lunar-observatory.jpg")
        self.assertEqual(Pipeline.select_starter_scene("Apartamento anime original sob chuva", "rain"), "lofi-anime-rainy-apartment.jpg")
        generic = {Pipeline.select_starter_scene(f"Foco silencioso {index}", "focus") for index in range(12)}
        self.assertEqual(Pipeline.select_starter_scene("Estufa no telhado", "rain"), "lofi-rooftop-greenhouse.jpg")
        self.assertEqual(Pipeline.select_starter_scene("Lavanderia junto ao mar", "rain"), "lofi-coastal-laundromat.jpg")
        self.assertEqual(Pipeline.select_starter_scene("Biblioteca de observatório sob a aurora", "cosmic"),
                         "lofi-observatory-library.jpg")
        self.assertEqual(Pipeline.select_starter_scene("Cabana de vidro entre cedros", "cozy"),
                         "lofi-forest-glass-cabin.jpg")
        self.assertGreaterEqual(len(STARTER_SCENES["focus"]), 8)
        self.assertEqual(len(MUSIC_ARRANGEMENTS), 12)
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
            self.assertEqual(design["style_id"], COVER_STYLE_ID)
            self.assertEqual({item["style"] for item in design["variants"]},
                             {"cinematográfica limpa", "cinematográfica alternativa"})
            self.assertEqual(design["selected"], "b")
            selected_manifest = json.loads(
                (Path(job["output_dir"]) / "artifact-manifest.json").read_text(encoding="utf-8")
            )
            self.assertIn("quality-gate.json", {item["name"] for item in selected_manifest["files"]})
            self.assertEqual(
                (Path(job["output_dir"]) / "thumbnail.jpg").read_bytes(),
                (Path(job["output_dir"]) / "thumbnail-b.jpg").read_bytes(),
            )
            pipeline.approve(job_id)
            publishing = PublishingCenter(pipeline, store)
            before = publishing.audit(store.get_job(job_id))
            self.assertFalse(before["eligible"])
            self.assertFalse(before["release_ready"])
            self.assertIn("Prévia ou teste curto não entra na publicação", before["blockers"])
            with self.assertRaisesRegex(ValueError, "Prévia ou teste curto"):
                publishing.prepare(job_id, 5)
            queue = publishing.queue()
            self.assertEqual(queue["summary"]["total"], 0)

    def test_pilot_certification_separates_automatic_gates_from_human_review(self):
        jobs = []
        for index in range(10):
            jobs.append({
                "id": f"pilot-{index}", "topic": f"Piloto {index}", "status": "awaiting_approval",
                "profile": "youtube_long", "duration": 1800,
                "metadata": {
                    "music": {"track_name": f"Faixa {index}"},
                    "creative_fingerprint": {
                        "scene": f"scene-{index}", "treatment": f"treatment-{index}",
                        "composition": f"composition-{index}", "motion_effect": f"motion-{index}",
                        "novelty": {"score": 70 + index},
                    },
                },
            })

        class PilotStore:
            @staticmethod
            def list_jobs(_limit):
                return jobs

        center = PublishingCenter(object(), PilotStore())
        automatic_checks = [
            {"id": "approval", "passed": False},
            {"id": "technical", "passed": True},
            {"id": "quality", "passed": True},
            {"id": "rights", "passed": True},
            {"id": "music", "passed": True},
        ]
        with patch.object(center, "audit", side_effect=lambda job, **kwargs: {"checks": automatic_checks}):
            certification = center.pilot_certification()
        self.assertTrue(certification["automatic_checks_passed"])
        self.assertFalse(certification["human_target_met"])
        self.assertEqual(certification["status"], "human_review_pending")
        self.assertEqual(certification["unique_tracks"], 10)
        self.assertEqual(certification["unique_visuals"], 10)
        self.assertEqual(certification["pending_review_count"], 10)

    def test_pilot_certification_uses_latest_explicit_cohort_only(self):
        jobs = []
        for index in range(10):
            jobs.append({
                "id": f"current-{index}", "topic": f"Atual {index}", "status": "awaiting_approval",
                "profile": "youtube_long", "duration": 1800, "cohort_id": "pilot-current",
                "created_at": f"2026-08-30T00:00:{index:02}Z",
                "metadata": {"music": {"track_name": f"Current {index}"},
                             "creative_fingerprint": {"scene": f"current-{index}"}},
            })
        jobs.append({
            "id": "historical", "topic": "Antigo", "status": "awaiting_approval",
            "profile": "youtube_long", "duration": 1800, "cohort_id": None,
            "created_at": "2026-08-01T00:00:00Z",
            "metadata": {"music": {"track_name": "Repeated"},
                         "creative_fingerprint": {"scene": "historical"}},
        })
        jobs.append({
            "id": "autonomous-newer", "topic": "Fase 2", "status": "awaiting_approval",
            "profile": "youtube_long", "duration": 1800, "cohort_id": "phase2-2026-09-02-220000",
            "created_at": "2026-09-02T22:00:00Z",
            "metadata": {"music": {"track_name": "Autonomous"},
                         "creative_fingerprint": {"scene": "phase2"}},
        })

        class CohortStore:
            @staticmethod
            def list_jobs(_limit):
                return jobs

        center = PublishingCenter(object(), CohortStore())
        checks = [{"id": "approval", "passed": False}, {"id": "technical", "passed": True}]
        with patch.object(center, "audit", return_value={"checks": checks}):
            certification = center.pilot_certification()
        self.assertEqual(certification["cohort_id"], "pilot-current")
        self.assertEqual(certification["candidate_count"], 10)
        self.assertEqual(certification["unique_tracks"], 10)

    @unittest.skipUnless(FFMPEG.exists(), "FFmpeg portátil não encontrado")
    def test_long_render_reuses_encoded_visual_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / "assets" / "starter", root / "assets" / "starter")
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            job_id = pipeline.create("Loop eficiente", 25, profile="preview")
            job = pipeline.run(job_id)
            strategy = job["metadata"]["render_strategy"]
            self.assertEqual(job["status"], "awaiting_approval")
            self.assertEqual(strategy["mode"], "encoded_loop_copy")
            self.assertEqual(strategy["visual_seconds_encoded"], 12)
            self.assertEqual(strategy["output_seconds"], 25)
            self.assertFalse(strategy["video_reencoded_for_full_duration"])
            self.assertTrue((Path(job["output_dir"]) / "visual-loop.mp4").is_file())

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

    def test_render_lock_blocks_another_process_and_recovers_stale_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            first = Pipeline(self.settings(root), store)
            second = Pipeline(self.settings(root), store)
            output = root / "data" / "jobs" / "locked"
            output.mkdir(parents=True)
            lock = first.acquire_job_lock(output)
            self.assertIsNotNone(lock)
            self.assertIsNone(second.acquire_job_lock(output))
            first.release_job_lock(lock)
            recovered = second.acquire_job_lock(output)
            self.assertIsNotNone(recovered)
            second.release_job_lock(recovered)
            (output / ".render.lock").write_text(
                json.dumps({"pid": 99999999, "token": "stale"}), encoding="utf-8"
            )
            recovered_stale = first.acquire_job_lock(output)
            self.assertIsNotNone(recovered_stale)
            first.release_job_lock(recovered_stale)

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

    def test_rain_is_masked_to_scene_windows(self):
        rainy_filter, rainy_zone = Pipeline.effect_plate_filter(
            1280, 720, "lofi-rainy-cafe", "angled_rain"
        )
        steam_filter, steam_zone = Pipeline.effect_plate_filter(
            1280, 720, "lofi-rainy-cafe", "cup_steam"
        )
        self.assertIn("crop=", rainy_filter)
        self.assertIn("pad=1280:720", rainy_filter)

        apartment_filter, apartment_zone = Pipeline.effect_plate_filter(
            1920, 1080, "anime-window-night", "window_drops"
        )
        self.assertEqual(apartment_zone["mode"], "window_mask")
        self.assertGreaterEqual(apartment_zone["x"], 0.48)
        self.assertLessEqual(apartment_zone["y"] + apartment_zone["height"], 0.70)
        self.assertIn("pad=1920:1080", apartment_filter)
        self.assertEqual(COVER_MOTION["rainy-window-memories"], "lamp_flicker")
        self.assertEqual(rainy_zone["mode"], "window_mask")
        self.assertLess(rainy_zone["width"], 1)
        self.assertNotIn("crop=", steam_filter)
        self.assertEqual(steam_zone["mode"], "effect_native")

    def test_music_arrangements_use_distinct_rhythm_families(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            pipeline = Pipeline(self.settings(root), store)
            hashes = set()
            rhythms = set()
            layer_sets = []
            for index, arrangement in enumerate(("dusty_keys", "night_rhodes", "glass_mallets", "cassette_guitar")):
                output = root / f"rhythm-{index}.wav"
                music = pipeline.create_lofi_loop(output, "focus", arrangement, {
                    "seed": 1000 + index, "music_arrangement": arrangement, "bpm": 74,
                    "progression_variant": 0, "key_shift": 0, "melody_density": .7,
                    "swing": .08, "texture": "soft_tape",
                })
                hashes.add(hashlib.sha256(output.read_bytes()).hexdigest())
                rhythms.add(music["rhythm_pattern"])
                layer_sets.append(set(music["layers"]))
            self.assertEqual(len(hashes), 4)
            self.assertEqual(rhythms, {"boom_bap", "half_time", "no_drums", "swing_break"})
            self.assertNotIn("kick", layer_sets[2])
            self.assertNotIn("snare", layer_sets[2])

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

    def test_tts_provider_is_explicit_and_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            settings = replace(self.settings(root), tts_provider="unknown")
            pipeline = Pipeline(settings, store)
            script = root / "script.txt"
            script.write_text("Teste de voz", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Provedor TTS inválido"):
                pipeline.synthesize_narration(script, root / "voice.mp3")

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
            shutil.copytree(ROOT / "assets" / "channel", root / "assets" / "channel")
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
                with urllib.request.urlopen(base + "/api/channel-assets/pausa-pra-anime-avatar-800.png") as response:
                    self.assertEqual(response.headers.get_content_type(), "image/png")
                    self.assertGreater(int(response.headers["Content-Length"]), 1_000)
                creative = json.load(urllib.request.urlopen(base + "/api/creative-system"))
                self.assertGreaterEqual(creative["catalog"]["candidate_space"], 25_000)
                series = json.load(urllib.request.urlopen(base + "/api/series"))
                self.assertGreaterEqual(len(series), 4)
                profiles = json.load(urllib.request.urlopen(base + "/api/profiles"))
                self.assertEqual(list(profiles), ["youtube_long"])
                self.assertEqual(profiles["youtube_long"]["min_duration"], 1800)
                self.assertEqual(profiles["youtube_long"]["max_duration"], 3600)
                flow = json.load(urllib.request.urlopen(base + "/api/music-sources/flow"))
                self.assertFalse(flow["api"]["configured"])
                self.assertNotIn("api_key", json.dumps(flow))
                lyria_key = "fake-test-key-long-enough-for-validation-only"
                configure_request = urllib.request.Request(
                    base + "/api/music-sources/lyria/configure",
                    data=json.dumps({"api_key": lyria_key}).encode(),
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                configured = json.load(urllib.request.urlopen(configure_request))
                self.assertTrue(configured["configured"])
                self.assertNotIn(lyria_key, json.dumps(configured))
                blocked_request = urllib.request.Request(
                    base + "/api/music-sources/lyria/disconnect", data=b"{}",
                    headers={"Content-Type": "application/json", "Origin": "https://malicious.example"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as blocked:
                    urllib.request.urlopen(blocked_request)
                self.assertEqual(blocked.exception.code, 403)
                blocked.exception.close()
                track = root / "licensed-lofi.wav"
                with wave.open(str(track), "wb") as output:
                    output.setnchannels(1);output.setsampwidth(2);output.setframerate(22050)
                    output.writeframes(array("h", [0] * 22050).tobytes())
                music_request = urllib.request.Request(
                    base + "/api/music-assets",
                    data=json.dumps({"path": str(track), "license_type": "original",
                                     "rights_confirmed": True}).encode(),
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                imported_music = json.load(urllib.request.urlopen(music_request))
                self.assertEqual(imported_music["count"], 1)
                music_library = json.load(urllib.request.urlopen(base + "/api/music-assets"))
                self.assertEqual(music_library[0]["name"], "licensed-lofi")
                review_request = urllib.request.Request(
                    base + f"/api/music-assets/{imported_music['ids'][0]}/review",
                    data=json.dumps({"decision": "approved"}).encode(),
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                reviewed_music = json.load(urllib.request.urlopen(review_request))
                self.assertEqual(reviewed_music["human_review"], "approved")
                self.assertTrue(reviewed_music["approved"])
                hidden_series_request = urllib.request.Request(
                    base + "/api/batches", data=json.dumps({"series_id": "vertical_moments"}).encode(),
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as hidden_series:
                    urllib.request.urlopen(hidden_series_request)
                self.assertEqual(hidden_series.exception.code, 400)
                hidden_series.exception.close()
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
                daily_report = json.load(urllib.request.urlopen(base + "/api/operations/daily-report"))
                self.assertFalse(daily_report["publish_performed"])
                self.assertIn("summary", daily_report)
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

    def test_remote_access_requires_credentials_and_same_origin_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            settings = replace(self.settings(root), remote_access=True,
                               remote_username="owner", remote_password="strong-test-password")
            pipeline = Pipeline(settings, store)
            server = create_server(pipeline, store, "127.0.0.1", 0, ROOT / "web")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            forwarded = {"Host": "factory.example", "CF-Connecting-IP": "203.0.113.7"}
            credentials = base64.b64encode(b"owner:strong-test-password").decode()
            authenticated = {**forwarded, "Authorization": f"Basic {credentials}"}
            try:
                blocked_request = urllib.request.Request(base + "/api/health", headers=forwarded)
                with self.assertRaises(urllib.error.HTTPError) as blocked:
                    urllib.request.urlopen(blocked_request)
                self.assertEqual(blocked.exception.code, 401)

                public_health = json.load(urllib.request.urlopen(base + "/healthz"))
                self.assertEqual(public_health, {"status": "ok"})
                self.assertIn("Basic", blocked.exception.headers["WWW-Authenticate"])
                blocked.exception.close()

                health_request = urllib.request.Request(base + "/api/health", headers=authenticated)
                health = json.load(urllib.request.urlopen(health_request))
                self.assertTrue(health["remote_access"]["enabled"])
                self.assertTrue(health["remote_access"]["protected"])
                self.assertNotIn("strong-test-password", json.dumps(health))

                same_origin = urllib.request.Request(
                    base + "/api/not-a-route", data=b"{}", method="POST",
                    headers={**authenticated, "Origin": "https://factory.example",
                             "Content-Type": "application/json"},
                )
                with self.assertRaises(urllib.error.HTTPError) as missing:
                    urllib.request.urlopen(same_origin)
                self.assertEqual(missing.exception.code, 404)
                missing.exception.close()

                cross_origin = urllib.request.Request(
                    base + "/api/not-a-route", data=b"{}", method="POST",
                    headers={**authenticated, "Origin": "https://evil.example",
                             "Content-Type": "application/json"},
                )
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    urllib.request.urlopen(cross_origin)
                self.assertEqual(rejected.exception.code, 403)
                rejected.exception.close()
            finally:
                server.shutdown()
                server.server_close()

    def test_remote_server_refuses_weak_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "data" / "factory.db")
            settings = replace(self.settings(root), remote_access=True,
                               remote_username="owner", remote_password="short")
            pipeline = Pipeline(settings, store)
            with self.assertRaisesRegex(ValueError, "pelo menos 16"):
                create_server(pipeline, store, "127.0.0.1", 0, ROOT / "web")

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
        self.assertIn("artifactUrl(item.job_id,'thumbnail.jpg',item.updated_at)", publishing_ui)
        self.assertIn("guidedReviewAdvance", publishing_ui)
        self.assertIn("data-guided-step", publishing_ui)
        app_ui = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("const artifactUrl=", app_ui)
        self.assertIn("artifactUrl(job.id,'thumbnail.jpg',job.updated_at)", app_ui)
        self.assertIn("window.guidedReviewAdvance", app_ui)
        phase7_ui = (ROOT / "web" / "phase7.js").read_text(encoding="utf-8")
        self.assertIn("form.querySelector('[name=\"impressions\"]')", phase7_ui)
        self.assertNotIn('/phase11.js', index)
        self.assertNotIn('id="night-card"', index)

    def test_series_catalog_uses_current_nocturnal_visual_identity(self):
        catalog = series_catalog()
        ids = {item["id"] for item in catalog}
        names = {item["name"] for item in catalog}
        self.assertEqual(ids, {"japan_after_rain", "city_after_dark", "rainy_refuges", "anime_midnight"})
        self.assertNotIn("Foco cósmico", names)
        self.assertNotIn("Mundos acolhedores", names)
        self.assertTrue(all(item["duration"] == 3600 for item in catalog))
        self.assertEqual(len({item["cover_asset"] for item in catalog}), len(catalog))
        self.assertTrue(all(
            (ROOT / "assets" / "covers" / "nocturnal-rain-v1" / item["cover_asset"]).is_file()
            for item in catalog
        ))

    def test_frontend_dialogs_cannot_submit_when_cancelled(self):
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn('method="dialog"', index)
        self.assertNotRegex(
            index,
            r'<button(?![^>]*type="button")[^>]*(?:value="cancel"|data-dialog-close)',
        )
        self.assertIn("source_asset_rights_confirmed", index)
        self.assertIn("source_asset_rights_confirmed", app)
        self.assertIn("$('#new-asset').onclick", app)
        self.assertIn("$('#asset-form').addEventListener('submit'", app)
        self.assertIn("hasRenderedArtifacts", app)
        calendar_ui = (ROOT / "web" / "phase2.js").read_text(encoding="utf-8")
        self.assertIn("activeCalendarStatuses", calendar_ui)
        self.assertNotIn("calendar-error", calendar_ui)

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
