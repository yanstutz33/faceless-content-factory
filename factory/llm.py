from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class OpenAIPlanEnhancer:
    """Optional Responses API enhancement with a strict local fallback boundary."""

    def __init__(self, api_key: str = "", model: str = "gpt-5.4", timeout: int = 45):
        self.api_key = api_key.strip()
        self.model = model.strip() or "gpt-5.4"
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def enhance(self, topic: str, duration: int, profile: str, local_plan: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            return local_plan
        schema = {
            "type": "object",
            "properties": {
                "research_keywords": {"type": "array", "items": {"type": "string"}, "minItems": 5, "maxItems": 10},
                "promise": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}, "minItems": 5, "maxItems": 12},
            },
            "required": ["research_keywords", "promise", "title", "description", "tags"],
            "additionalProperties": False,
        }
        payload = {
            "model": self.model,
            "store": False,
            "instructions": (
                "You are the English-language editor for a faceless ambient-music channel. Improve discovery "
                "and clarity without inventing claims, brands, rights, or sources. Titles and descriptions must "
                "be natural English. Prefer short, emotionally reassuring titles such as 'Go to Sleep, It's "
                "3 A.M.' or 'It's Okay. Get Some Rest.' Never return Portuguese metadata."
            ),
            "input": f"Tema: {topic}\nDuração: {duration}s\nFormato: {profile}\nPlano local: {json.dumps(local_plan, ensure_ascii=False)}",
            "max_output_tokens": 900,
            "text": {"format": {"type": "json_schema", "name": "faceless_editorial_plan", "strict": True, "schema": schema}},
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.load(response)
            output_text = result.get("output_text")
            if not output_text:
                for item in result.get("output", []):
                    for content in item.get("content", []):
                        if content.get("type") == "output_text":
                            output_text = content.get("text")
                            break
            enriched = json.loads(output_text or "{}")
            plan = json.loads(json.dumps(local_plan, ensure_ascii=False))
            plan["research"]["keywords"] = enriched["research_keywords"]
            plan["strategy"]["promise"] = enriched["promise"]
            plan["seo"]["title"] = enriched["title"][:96]
            plan["seo"]["description"] = enriched["description"]
            plan["seo"]["tags"] = enriched["tags"]
            plan["provider"] = {"mode": "openai", "model": self.model, "response_id": result.get("id")}
            return plan
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
            local_plan["provider"] = {"mode": "local_fallback", "model": self.model, "error": str(exc)[:300]}
            return local_plan
