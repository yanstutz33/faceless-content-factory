from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


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
    if not product.get("exact_product_confirmed"):
        errors.append("O vídeo precisa mostrar exatamente o produto vinculado")
    if not product.get("affiliate_disclosure"):
        errors.append("Conteúdo com comissão precisa ser identificado como publicidade")
    assets = product.get("assets") or []
    if not assets:
        errors.append("Ao menos um asset rastreável é obrigatório")
    for asset in assets:
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
