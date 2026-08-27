from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .pipeline import Pipeline
from .store import Store


ALLOWED_LICENSES = {"original", "commercial_license", "public_domain", "cc0", "provider_generated"}


def validate_commerce_brief(product: dict[str, Any]) -> dict[str, Any]:
    """Fail-closed validation before any affiliate video can enter rendering."""
    errors: list[str] = []
    product_url = str(product.get("product_url", "")).strip()
    parsed = urlparse(product_url)
    if not str(product.get("product_id", "")).strip():
        errors.append("Identificador oficial do produto ausente")
    if not str(product.get("title", "")).strip():
        errors.append("Título verificável do produto ausente")
    if parsed.scheme != "https" or not parsed.netloc:
        errors.append("URL HTTPS oficial do produto ausente")
    elif not (parsed.hostname or "").lower().endswith("shopee.com.br"):
        errors.append("A URL precisa apontar para o domínio oficial da Shopee Brasil")
    if not product.get("exact_product_confirmed"):
        errors.append("O vídeo precisa mostrar exatamente o produto vinculado")
    if not product.get("affiliate_disclosure"):
        errors.append("Conteúdo com comissão precisa ser identificado como publicidade")
    assets = product.get("assets") or []
    if not assets:
        errors.append("Ao menos um asset rastreável é obrigatório")
    for asset in assets:
        source_host = (urlparse(str(asset.get("source_url", ""))).hostname or "").lower()
        if source_host.endswith("pinterest.com") or source_host.endswith("pin.it"):
            errors.append(f"Pinterest pode inspirar a pesquisa, mas não comprova licença: {asset.get('name', 'sem nome')}")
        if not asset.get("approved") or asset.get("license_type") not in ALLOWED_LICENSES:
            errors.append(f"Asset sem direitos comerciais comprovados: {asset.get('name', 'sem nome')}")
        if not asset.get("source_url") and asset.get("license_type") != "original":
            errors.append(f"Origem do asset não registrada: {asset.get('name', 'sem nome')}")
    claims = product.get("claims") or []
    if any(not claim.get("source") for claim in claims):
        errors.append("Toda alegação de produto precisa de fonte verificável")
    return {
        "passed": not errors,
        "errors": errors,
        "publish_mode": "manual_safe",
        "required_disclosure": "#publicidade",
        "pinterest_policy": "research_only_not_media_source",
        "product_linking": "exact_product_must_be_attached_in_platform",
        "recommended_profile": "vertical_short",
    }


class CommercePackager:
    """Prepare a rights-safe Shopee affiliate package without contacting Shopee."""

    def __init__(self, pipeline: Pipeline, store: Store):
        self.pipeline = pipeline
        self.store = store

    def prepare(self, job_id: str, product: dict[str, Any], duration: int = 30) -> dict[str, Any]:
        validation = validate_commerce_brief(product)
        if not validation["passed"]:
            raise ValueError("Brief comercial bloqueado: " + "; ".join(validation["errors"]))
        job = self.store.get_job(job_id)
        if not job or job["status"] != "approved":
            raise ValueError("A produção precisa estar aprovada antes de virar conteúdo comercial")
        output = Path(job["output_dir"])
        if not (output / "vertical-short.mp4").is_file():
            self.pipeline.prepare_vertical_package(job_id, duration)
        claims = [{"text": str(item.get("text", "")).strip(), "source": str(item.get("source", "")).strip()}
                  for item in product.get("claims") or []]
        package = {
            "mode": "prepared_not_uploaded",
            "created_at": datetime.now(UTC).isoformat(),
            "job_id": job_id,
            "platform": "shopee",
            "product": {"id": str(product["product_id"]), "title": str(product["title"]),
                        "url": str(product["product_url"])},
            "media": {"video": "vertical-short.mp4", "thumbnail": "vertical-thumbnail.jpg",
                      "rights_manifest": "asset-manifest.json"},
            "copy": {"disclosure": validation["required_disclosure"],
                     "caption": f"{str(product['title']).strip()} · confira os detalhes no produto vinculado. {validation['required_disclosure']}",
                     "call_to_action": "Confira preço, disponibilidade e condições atuais no link oficial."},
            "claims": claims,
            "validation": validation,
            "automatic_upload_allowed": False,
            "manual_checks": ["Confirmar que o vídeo mostra o produto exato", "Vincular o item correto na plataforma",
                              "Revalidar preço e disponibilidade antes de publicar"],
        }
        (output / "commerce-package.json").write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
        self.store.event(job_id, "commerce", "Pacote Shopee preparado com direitos e divulgação; nenhum upload foi realizado")
        return package
