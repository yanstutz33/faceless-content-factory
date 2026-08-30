from __future__ import annotations

import base64
import binascii
import json
import re
import subprocess
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import Settings
from .store import Store
from .vault import SecureVault


LYRIA_MODELS = {
    "lyria-3-clip-preview": {"label": "Lyria 3 Clip", "duration": "30 segundos", "price_usd": 0.04},
    "lyria-3-pro-preview": {"label": "Lyria 3 Pro", "duration": "até alguns minutos", "price_usd": 0.08},
}
LYRIA_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
LYRIA_DOCS_URL = "https://ai.google.dev/gemini-api/docs/music-generation"


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value[:48] or "lyria-track"


class LyriaMusicService:
    """Generate music through Google's public Gemini API without exposing the API key."""

    def __init__(self, settings: Settings, store: Store):
        self.settings = settings
        self.store = store
        self.vault = SecureVault(settings.data_dir / "private" / "music-providers.vault")

    def _stored_key(self) -> str:
        value = self.vault.get("api:gemini")
        return str(value or "").strip()

    def _api_key(self) -> str:
        return self.settings.gemini_api_key.strip() or self._stored_key()

    def status(self) -> dict[str, Any]:
        source = "environment" if self.settings.gemini_api_key.strip() else (
            "encrypted_vault" if self._stored_key() else "none"
        )
        return {
            "configured": source != "none",
            "key_source": source,
            "provider": "Gemini API · Lyria 3",
            "default_model": self.settings.lyria_model,
            "models": [{"id": model_id, **details} for model_id, details in LYRIA_MODELS.items()],
            "paid_preview": True,
            "docs_url": LYRIA_DOCS_URL,
        }

    def configure(self, api_key: str) -> dict[str, Any]:
        api_key = str(api_key or "").strip()
        if not 20 <= len(api_key) <= 200 or any(character.isspace() for character in api_key):
            raise ValueError("A chave da Gemini API parece incompleta")
        self.vault.set("api:gemini", api_key)
        return self.status()

    def disconnect(self) -> dict[str, Any]:
        self.vault.pop("api:gemini")
        return self.status()

    @staticmethod
    def _extract_audio(payload: dict[str, Any]) -> tuple[bytes, str]:
        candidates: list[dict[str, Any]] = []
        output_audio = payload.get("output_audio")
        if isinstance(output_audio, dict):
            candidates.append(output_audio)
        for step in payload.get("steps", []):
            if not isinstance(step, dict) or step.get("type") != "model_output":
                continue
            candidates.extend(block for block in step.get("content", []) if isinstance(block, dict))
        for block in candidates:
            if block.get("type") not in {None, "audio"}:
                continue
            encoded = block.get("data")
            if not isinstance(encoded, str) or not encoded:
                continue
            try:
                audio = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error):
                continue
            if audio:
                mime = str(block.get("mime_type") or block.get("mimeType") or "audio/mpeg")
                return audio, mime
        raise RuntimeError("O Lyria respondeu sem um arquivo de áudio utilizável")

    def _call_api(self, api_key: str, model: str, prompt: str) -> dict[str, Any]:
        body: dict[str, Any] = {"model": model, "input": prompt}
        if model == "lyria-3-pro-preview":
            body["response_format"] = {"type": "audio"}
        request = urllib.request.Request(
            LYRIA_ENDPOINT,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.lyria_timeout_seconds) as response:
                raw = response.read(40 * 1024 * 1024 + 1)
        except urllib.error.HTTPError as exc:
            messages = {
                400: "O Google recusou o prompt ou o modelo solicitado",
                401: "A chave da Gemini API não foi aceita",
                403: "Ative o faturamento e o acesso ao Lyria 3 neste projeto do Google",
                429: "O limite de gerações do Google foi atingido; tente novamente mais tarde",
            }
            raise ValueError(messages.get(exc.code, "O Google não conseguiu gerar a música agora")) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError("A conexão com a Gemini API expirou ou está indisponível") from exc
        if len(raw) > 40 * 1024 * 1024:
            raise RuntimeError("A resposta musical ultrapassou o limite seguro de 40 MB")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("A Gemini API retornou uma resposta inválida") from exc
        if not isinstance(value, dict):
            raise RuntimeError("A Gemini API retornou um formato inesperado")
        return value

    def _validate_audio(self, path: Path) -> None:
        result = subprocess.run(
            [self.settings.ffmpeg, "-v", "error", "-t", "3", "-i", str(path), "-f", "null", "-"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode:
            raise RuntimeError("O áudio recebido do Lyria não passou na validação local")

    def generate(self, name: str, prompt: str, model: str, rights_confirmed: bool) -> dict[str, Any]:
        if not rights_confirmed:
            raise ValueError("Confirme que leu os termos e pode usar o áudio gerado")
        api_key = self._api_key()
        if not api_key:
            raise ValueError("Conecte uma chave da Gemini API antes de gerar músicas")
        model = str(model or self.settings.lyria_model).strip()
        if model not in LYRIA_MODELS:
            raise ValueError("Modelo musical do Google inválido")
        name = " ".join(str(name or "Faixa Lyria").split()).strip()[:100]
        prompt = " ".join(str(prompt or "").split()).strip()
        if not 20 <= len(prompt) <= 3000:
            raise ValueError("Descreva a música em 20 a 3.000 caracteres")
        safety = " Instrumental only, no vocals, original composition, no copyrighted samples, no artist imitation."
        if "no vocals" not in prompt.lower():
            prompt += safety
        payload = self._call_api(api_key, model, prompt)
        audio, mime = self._extract_audio(payload)
        extension = ".wav" if "wav" in mime.lower() else ".mp3"
        destination_dir = self.settings.data_dir / "music" / "lyria"
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{_slug(name)}-{uuid.uuid4().hex[:10]}{extension}"
        temporary = destination.with_name(destination.stem + ".tmp" + destination.suffix)
        try:
            temporary.write_bytes(audio)
            self._validate_audio(temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        generated_at = datetime.now(UTC).isoformat()
        asset_id = self.store.add_music_asset(
            name, str(destination), "provider_generated", LYRIA_DOCS_URL,
            f"Gerada por {model} em {generated_at}; prompt local: {prompt}", True,
        )
        return {
            "id": asset_id,
            "name": name,
            "model": model,
            "duration_class": LYRIA_MODELS[model]["duration"],
            "price_estimate_usd": LYRIA_MODELS[model]["price_usd"],
            "file": str(destination),
            "size_bytes": destination.stat().st_size,
            "registered": True,
        }

    def generate_batch(self, directions: list[dict[str, str]], model: str,
                       rights_confirmed: bool, count: int = 12) -> dict[str, Any]:
        """Generate a bounded, diverse catalog without exposing prompts or API keys to workers."""
        if not rights_confirmed:
            raise ValueError("Confirme os termos e o custo estimado do lote")
        if not self._api_key():
            raise ValueError("Conecte uma chave da Gemini API antes de gerar o lote")
        if model not in LYRIA_MODELS:
            raise ValueError("Modelo musical do Google inválido")
        count = max(1, min(12, int(count)))
        selected = directions[:count]
        results: list[dict[str, Any] | None] = [None] * len(selected)
        failures: list[dict[str, str]] = []
        with ThreadPoolExecutor(max_workers=min(2, len(selected)), thread_name_prefix="lyria-batch") as executor:
            futures = {
                executor.submit(self.generate, item["name"], item["prompt"], model, True): index
                for index, item in enumerate(selected)
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    results[index] = future.result()
                except (ValueError, RuntimeError, OSError) as exc:
                    failures.append({"name": selected[index]["name"], "error": str(exc)})
        generated = [item for item in results if item is not None]
        return {
            "requested": len(selected), "generated": len(generated), "failed": len(failures),
            "model": model,
            "price_estimate_usd": round(len(selected) * LYRIA_MODELS[model]["price_usd"], 2),
            "actual_generated_cost_estimate_usd": round(len(generated) * LYRIA_MODELS[model]["price_usd"], 2),
            "items": generated, "failures": failures,
        }
