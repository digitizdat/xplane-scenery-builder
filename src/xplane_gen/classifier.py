"""Bedrock LLM classification layer with tiered routing and review queue output."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

import boto3
import numpy as np
from rich.console import Console

from xplane_gen.catalog import AssetCatalog

console = Console()

# Model IDs
_HAIKU = "anthropic.claude-haiku-4-5-20251001-v1:0"
_SONNET = "anthropic.claude-sonnet-4-6"
_OPUS = "anthropic.claude-opus-4-7"

# Confidence routing thresholds
_HIGH = 0.85  # auto-approve
_LOW = 0.60  # escalate to Opus or queue for human

# Items below this threshold go to review_queue.json
_REVIEW_THRESHOLD = 0.75

_TOOL_SPEC: dict[str, Any] = {
    "name": "classify_building",
    "description": "Classify a building from satellite imagery and OSM tags.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "building_type": {"type": "string"},
                "height_m": {"type": "number"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reasoning": {"type": "string"},
            },
            "required": ["building_type", "height_m", "confidence", "reasoning"],
        }
    },
}


class BedrockClassifier:
    def __init__(
        self,
        output_dir: Path,
        region: str = "us-east-1",
    ) -> None:
        self.output_dir = output_dir
        self._client = boto3.client("bedrock-runtime", region_name=region)
        self._cache_dir = output_dir / ".llm_cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._catalog = AssetCatalog()
        self._review_queue: list[dict[str, Any]] = []

    def classify_building(
        self,
        image_rgb: np.ndarray,
        osm_tags: dict[str, str],
        lat: float,
        lon: float,
    ) -> dict[str, Any]:
        """Classify a building patch. Returns dict with building_type, height_m, confidence."""
        image_b64 = _encode_image(image_rgb)
        prompt = _build_prompt(osm_tags)
        cache_key = _cache_key(image_b64, prompt)

        if cached := self._load_cache(cache_key):
            return cached

        # Tier 1: Haiku (cheap triage)
        result = self._call_model(_HAIKU, image_b64, prompt)

        # Tier 2: escalate to Sonnet if confidence too low
        if result["confidence"] < _HIGH:
            result = self._call_model(_SONNET, image_b64, prompt)

        # Tier 3: escalate to Opus or queue for human review
        if result["confidence"] < _LOW:
            result = self._call_model(_OPUS, image_b64, prompt)

        # Validate virtual path exists in catalog
        fac_path = self._catalog.get_facade(
            result["building_type"], result.get("area_m2", 300.0), lat, lon
        )
        result["fac_path"] = fac_path

        self._save_cache(cache_key, result)

        if result["confidence"] < _REVIEW_THRESHOLD:
            self._queue_for_review(result, image_b64, osm_tags)

        return result

    def flush_review_queue(self, path: Path | None = None) -> Path:
        """Write accumulated review queue items to JSON. Returns the path."""
        out = path or (self.output_dir / "review_queue.json")
        out.write_text(json.dumps(self._review_queue, indent=2), encoding="utf-8")
        return out

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _call_model(self, model_id: str, image_b64: str, prompt: str) -> dict[str, Any]:
        image_bytes = base64.b64decode(image_b64)
        request_kb = (len(image_bytes) + len(prompt.encode())) / 1024

        response = self._client.converse(
            modelId=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "image": {
                                "format": "png",
                                "source": {"bytes": image_bytes},
                            }
                        },
                        {"text": prompt},
                    ],
                }
            ],
            toolConfig={"tools": [{"toolSpec": _TOOL_SPEC}]},
        )

        usage = response.get("usage", {})
        input_tokens = usage.get("inputTokens", "?")
        output_tokens = usage.get("outputTokens", "?")
        console.print(
            f"[dim]  LLM {model_id.split('.')[-1]} | "
            f"request {request_kb:.1f} KB | "
            f"tokens in={input_tokens} out={output_tokens}[/dim]"
        )

        return _parse_tool_response(response)

    def _queue_for_review(
        self,
        result: dict[str, Any],
        image_b64: str,
        osm_tags: dict[str, str],
    ) -> None:
        self._review_queue.append(
            {
                "building_type": result["building_type"],
                "height_m": result["height_m"],
                "confidence": result["confidence"],
                "reasoning": result.get("reasoning", ""),
                "fac_path": result.get("fac_path", ""),
                "osm_tags": osm_tags,
                "thumbnail_b64": image_b64,
                "human_decision": result["building_type"],  # pre-filled with best guess
            }
        )

    def _load_cache(self, key: str) -> dict[str, Any] | None:
        p = self._cache_dir / f"{key}.json"
        if p.exists():
            data: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
            return data
        return None

    def _save_cache(self, key: str, result: dict[str, Any]) -> None:
        p = self._cache_dir / f"{key}.json"
        p.write_text(json.dumps(result), encoding="utf-8")


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #


def _encode_image(image_rgb: np.ndarray) -> str:
    """Encode an H×W×3 uint8 array as base64 PNG."""
    import io

    from PIL import Image

    img = Image.fromarray(image_rgb.astype(np.uint8))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _build_prompt(osm_tags: dict[str, str]) -> str:
    tags_str = ", ".join(f"{k}={v}" for k, v in osm_tags.items())
    return (
        "Classify this building from the satellite image.\n"
        f"OSM tags: {tags_str}\n"
        "Use the classify_building tool. "
        "building_type must be one of: residential, commercial, industrial, "
        "religious, agricultural, generic.\n"
        "Estimate height_m from visible shadow or building type. "
        "Set confidence 0–1 based on image clarity and tag quality."
    )


def _cache_key(image_b64: str, prompt: str) -> str:
    return hashlib.sha256(f"{image_b64}{prompt}".encode()).hexdigest()[:16]


def _parse_tool_response(response: dict[str, Any]) -> dict[str, Any]:
    """Extract classify_building tool call result from Converse API response."""
    for block in response.get("output", {}).get("message", {}).get("content", []):
        if block.get("toolUse", {}).get("name") == "classify_building":
            inp: dict[str, Any] = block["toolUse"]["input"]
            return {
                "building_type": str(inp.get("building_type", "generic")),
                "height_m": float(inp.get("height_m", 8.0)),
                "confidence": float(inp.get("confidence", 0.5)),
                "reasoning": str(inp.get("reasoning", "")),
            }
    # Fallback if tool not called
    return {"building_type": "generic", "height_m": 8.0, "confidence": 0.0, "reasoning": ""}
