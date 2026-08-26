from __future__ import annotations

from pathlib import Path

from .config import Settings


def _configured(value: str) -> bool:
    return bool(value and value.strip())


def platform_readiness(settings: Settings) -> dict:
    """Return capability flags without ever returning credential values."""
    youtube_file = Path(settings.youtube_client_secrets_file).expanduser() if settings.youtube_client_secrets_file else None
    youtube_configured = bool(youtube_file and youtube_file.is_file())
    platforms = [
        {
            "id": "youtube",
            "label": "YouTube",
            "package_ready": True,
            "connector_configured": youtube_configured,
            "manual_step": "Entrar com Google e autorizar o canal" if youtube_configured else "Adicionar o arquivo OAuth e autorizar o canal",
            "output": "Vídeo longo, capa, metadados e pacote privado",
        },
        {
            "id": "tiktok",
            "label": "TikTok",
            "package_ready": True,
            "connector_configured": _configured(settings.tiktok_client_key),
            "manual_step": "Entrar no TikTok e autorizar a conta",
            "output": "Vídeo 9:16 e textos de publicação",
        },
        {
            "id": "reels",
            "label": "Instagram Reels",
            "package_ready": True,
            "connector_configured": _configured(settings.meta_app_id),
            "manual_step": "Entrar na Meta e escolher a conta profissional",
            "output": "Vídeo 9:16 e textos de publicação",
        },
        {
            "id": "shopee",
            "label": "Shopee",
            "package_ready": False,
            "connector_configured": _configured(settings.shopee_partner_id),
            "manual_step": "Vincular a conta e confirmar catálogo e direitos da mídia",
            "output": "Validação comercial preparada; geração entra na próxima fase",
        },
    ]
    configured = sum(1 for item in platforms if item["connector_configured"])
    return {
        "mode": "manual-safe",
        "automatic_upload_allowed": False,
        "configured": configured,
        "total": len(platforms),
        "platforms": platforms,
        "security": "Somente indicadores são exibidos; segredos nunca saem do servidor.",
    }
