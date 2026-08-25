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
        )

