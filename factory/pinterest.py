from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .store import Store


class PinterestPackager:
    """Build an API-shaped Video Pin package without contacting Pinterest."""

    def __init__(self, store: Store):
        self.store = store

    @staticmethod
    def _limited(value: Any, fallback: str, maximum: int) -> str:
        text = " ".join(str(value or fallback).split())
        return text[:maximum].rstrip()

    def prepare(self, campaign: dict[str, Any], product: dict[str, Any], options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = options or {}
        job_id = str(campaign.get("job_id") or "")
        job = self.store.get_job(job_id)
        if not job or job.get("status") != "approved":
            raise ValueError("A campanha precisa de uma produção aprovada antes do Video Pin")
        if product.get("status") != "validated" or not product.get("validation", {}).get("passed"):
            raise ValueError("O produto precisa continuar validado antes do Video Pin")

        output = Path(job["output_dir"])
        required = ["vertical-short.mp4", "vertical-thumbnail.jpg", "commerce-package.json"]
        missing = [name for name in required if not (output / name).is_file()]
        if missing:
            raise ValueError("Prepare o pacote comercial antes do Pinterest: " + ", ".join(missing))

        board_name = self._limited(options.get("board_name"), "Achados úteis", 100)
        title = self._limited(options.get("title"), product["title"], 100)
        default_description = (
            f"{product['title']} em demonstração própria. "
            "Confira preço, disponibilidade e condições atuais no link oficial. #publicidade"
        )
        description = self._limited(options.get("description"), default_description, 500)
        alt_text = self._limited(
            options.get("alt_text"),
            f"Demonstração em vídeo de {product['title']}, produto vinculado à campanha {campaign['name']}.",
            500,
        )
        affiliate_url = str(product.get("affiliate_url") or product["product_url"])
        manifest = {
            "mode": "prepared_not_uploaded",
            "created_at": datetime.now(UTC).isoformat(),
            "platform": "pinterest",
            "format": "video_pin",
            "campaign_id": campaign["id"],
            "job_id": job_id,
            "board_target": {"name": board_name, "board_id": None, "selection": "required_after_login"},
            "product": {
                "id": product["external_id"], "title": product["title"],
                "product_url": product["product_url"], "affiliate_url": affiliate_url,
            },
            "media": {
                "video": "vertical-short.mp4", "cover": "vertical-thumbnail.jpg",
                "rights_manifest": "asset-manifest.json", "source_policy": "original_or_licensed_only",
            },
            "copy": {"title": title, "description": description, "alt_text": alt_text, "link": affiliate_url},
            "api_plan": {
                "version": "v5", "required_scopes": ["boards:read", "pins:write"],
                "steps": ["register_media_upload", "upload_video", "confirm_media_succeeded", "create_pin"],
                "payload_template": {
                    "title": title, "description": description, "alt_text": alt_text,
                    "board_id": "__SELECT_AFTER_LOGIN__", "link": affiliate_url,
                    "media_source": {
                        "source_type": "video_id", "media_id": "__MEDIA_ID_AFTER_UPLOAD__",
                        "cover_image_url": "__PUBLIC_COVER_URL_REQUIRED_BY_PINTEREST__",
                    },
                },
            },
            "automatic_upload_allowed": False,
            "manual_checks": [
                "Selecionar o board oficial depois do login",
                "Revalidar preço, estoque e permissão do link de afiliado",
                "Confirmar a divulgação #publicidade e o produto exato",
                "Hospedar a capa temporariamente apenas durante o envio oficial",
            ],
        }
        (output / "pinterest-package.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.store.event(job_id, "pinterest", "Video Pin preparado localmente; nenhum upload foi realizado")
        return manifest
