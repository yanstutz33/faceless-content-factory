from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    root: Path
    data_dir: Path
    ffmpeg: str
    ffprobe: str
    host: str
    port: int
    allow_publish: bool
    narration_fallback: bool = True
    workers: int = 1
    calendar_poll_seconds: int = 15
    autopilot_max_review: int = 12
    autopilot_max_active: int = 2
    autopilot_min_free_gb: float = 3.0
    openai_api_key: str = ""
    openai_model: str = "gpt-5.4"
    youtube_client_secrets_file: str = ""
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    tiktok_redirect_uri: str = ""
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_redirect_uri: str = ""
    shopee_partner_id: str = ""
    shopee_partner_key: str = ""
    backup_keep: int = 10
    local_tts_fallback: bool = True

    @classmethod
    def load(cls, root: Path) -> "Settings":
        root = root.resolve()
        load_dotenv(root / ".env")
        local_bin = root / ".tools" / "ffmpeg" / "bin"
        default_ffmpeg = local_bin / "ffmpeg.exe"
        default_ffprobe = local_bin / "ffprobe.exe"
        data = Path(os.getenv("FACTORY_DATA_DIR", "data"))
        if not data.is_absolute():
            data = root / data
        return cls(
            root=root,
            data_dir=data.resolve(),
            ffmpeg=os.getenv("FFMPEG_PATH", str(default_ffmpeg if default_ffmpeg.exists() else "ffmpeg")),
            ffprobe=os.getenv("FFPROBE_PATH", str(default_ffprobe if default_ffprobe.exists() else "ffprobe")),
            host=os.getenv("FACTORY_HOST", "127.0.0.1"),
            port=int(os.getenv("FACTORY_PORT", "8787")),
            allow_publish=os.getenv("ALLOW_PLATFORM_PUBLISH", "false").lower() == "true",
            narration_fallback=os.getenv("NARRATION_FALLBACK_TO_AMBIENT", "true").lower() == "true",
            workers=max(1, min(2, int(os.getenv("FACTORY_WORKERS", "1")))),
            calendar_poll_seconds=max(5, min(300, int(os.getenv("CALENDAR_POLL_SECONDS", "15")))),
            autopilot_max_review=max(1, min(50, int(os.getenv("AUTOPILOT_MAX_REVIEW", "12")))),
            autopilot_max_active=max(1, min(5, int(os.getenv("AUTOPILOT_MAX_ACTIVE", "2")))),
            autopilot_min_free_gb=max(0.5, float(os.getenv("AUTOPILOT_MIN_FREE_GB", "3"))),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4"),
            youtube_client_secrets_file=os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", ""),
            tiktok_client_key=os.getenv("TIKTOK_CLIENT_KEY", ""),
            tiktok_client_secret=os.getenv("TIKTOK_CLIENT_SECRET", ""),
            tiktok_redirect_uri=os.getenv("TIKTOK_REDIRECT_URI", f"http://{os.getenv('FACTORY_HOST', '127.0.0.1')}:{os.getenv('FACTORY_PORT', '8787')}/api/oauth/callback/tiktok"),
            meta_app_id=os.getenv("META_APP_ID", ""),
            meta_app_secret=os.getenv("META_APP_SECRET", ""),
            meta_redirect_uri=os.getenv("META_REDIRECT_URI", f"http://{os.getenv('FACTORY_HOST', '127.0.0.1')}:{os.getenv('FACTORY_PORT', '8787')}/api/oauth/callback/reels"),
            shopee_partner_id=os.getenv("SHOPEE_PARTNER_ID", ""),
            shopee_partner_key=os.getenv("SHOPEE_PARTNER_KEY", ""),
            backup_keep=max(2, min(50, int(os.getenv("FACTORY_BACKUP_KEEP", "10")))),
            local_tts_fallback=os.getenv("LOCAL_TTS_FALLBACK", "true").lower() == "true",
        )
