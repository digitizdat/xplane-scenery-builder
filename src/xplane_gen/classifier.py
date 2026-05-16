"""Bedrock LLM classification: buildings, forests, and roads via vision API."""

from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import boto3
import numpy as np
from PIL import Image
from rich.console import Console

console = Console()

# Model IDs — cross-region inference profiles (required for on-demand access)
_HAIKU = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
_SONNET = "us.anthropic.claude-sonnet-4-6"
_OPUS = "us.anthropic.claude-opus-4-7"

# Confidence routing thresholds
_HIGH = 0.85
_LOW = 0.60
_REVIEW_THRESHOLD = 0.75

# ------------------------------------------------------------------ #
# Tool specs for Bedrock Converse API                                  #
# ------------------------------------------------------------------ #

_BUILDING_TOOL: dict[str, Any] = {
    "name": "classify_building",
    "description": "Classify a building from satellite imagery and OSM tags.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "building_type": {
                    "type": "string",
                    "enum": [
                        "residential",
                        "commercial",
                        "industrial",
                        "religious",
                        "agricultural",
                        "generic",
                    ],
                },
                "height_m": {"type": "number"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["building_type", "height_m", "confidence"],
        }
    },
}

_FOREST_TOOL: dict[str, Any] = {
    "name": "classify_forest",
    "description": "Classify forest composition from satellite imagery.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "species_mix": {
                    "type": "string",
                    "enum": ["deciduous", "conifer", "mixed"],
                },
                "canopy_density": {"type": "number", "minimum": 0, "maximum": 1},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["species_mix", "canopy_density", "confidence"],
        }
    },
}

_ROAD_TOOL: dict[str, Any] = {
    "name": "classify_road",
    "description": "Classify road surface and characteristics from satellite imagery.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "surface_type": {
                    "type": "string",
                    "enum": ["asphalt", "gravel", "dirt", "concrete"],
                },
                "lane_count": {"type": "integer", "minimum": 1, "maximum": 6},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["surface_type", "lane_count", "confidence"],
        }
    },
}


# ------------------------------------------------------------------ #
# Classifier                                                           #
# ------------------------------------------------------------------ #


class BedrockClassifier:
    def __init__(
        self,
        output_dir: Path,
        region: str = "us-east-1",
        review_all: bool = False,
    ) -> None:
        self.output_dir = output_dir
        self._client = boto3.client("bedrock-runtime", region_name=region)
        self._cache_dir = output_dir / ".llm_cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._review_queue: list[dict[str, Any]] = []
        self._review_all = review_all

    # ── Public API ────────────────────────────────────────────────────

    def classify_building(self, image: np.ndarray, osm_tags: dict[str, str]) -> dict[str, Any]:
        """Classify a building. Returns {building_type, height_m, confidence}."""
        prompt = (
            "Classify this building from the satellite image.\n"
            f"OSM tags: {_fmt_tags(osm_tags)}\n"
            "Use the classify_building tool."
        )
        return self._classify(
            image,
            prompt,
            _BUILDING_TOOL,
            "classify_building",
            {
                "building_type": "generic",
                "height_m": 8.0,
                "confidence": 0.0,
            },
        )

    def classify_forest(self, image: np.ndarray, esa_label: str, ndvi: float) -> dict[str, Any]:
        """Classify forest composition. Returns {species_mix, canopy_density, confidence}."""
        prompt = (
            "Identify the forest type from this satellite image.\n"
            f"ESA land cover class: {esa_label}\n"
            f"NDVI density: {ndvi:.2f}\n"
            "Use the classify_forest tool."
        )
        return self._classify(
            image,
            prompt,
            _FOREST_TOOL,
            "classify_forest",
            {
                "species_mix": "mixed",
                "canopy_density": ndvi,
                "confidence": 0.0,
            },
        )

    def classify_road(self, image: np.ndarray, osm_tags: dict[str, str]) -> dict[str, Any]:
        """Classify road surface. Returns {surface_type, lane_count, confidence}."""
        prompt = (
            "Identify the road surface type from this satellite image.\n"
            f"OSM tags: {_fmt_tags(osm_tags)}\n"
            "Use the classify_road tool."
        )
        return self._classify(
            image,
            prompt,
            _ROAD_TOOL,
            "classify_road",
            {
                "surface_type": "asphalt",
                "lane_count": 2,
                "confidence": 0.0,
            },
        )

    def flush_review_queue(self, path: Path | None = None) -> Path:
        """Write review queue to JSON. Returns path."""
        out = path or (self.output_dir / "review_queue.json")
        out.write_text(json.dumps(self._review_queue, indent=2), encoding="utf-8")
        return out

    @property
    def review_count(self) -> int:
        return len(self._review_queue)

    # ── Internal ──────────────────────────────────────────────────────

    def _classify(
        self,
        image: np.ndarray,
        prompt: str,
        tool_spec: dict[str, Any],
        tool_name: str,
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        image_b64 = _encode_image(image)
        cache_key = _cache_key(image_b64, prompt)

        if cached := self._load_cache(cache_key):
            return cached

        result = self._tiered_call(image_b64, prompt, tool_spec, tool_name, fallback)
        self._save_cache(cache_key, result)

        if self._review_all or result.get("confidence", 0) < _REVIEW_THRESHOLD:
            self._review_queue.append(
                {
                    "tool": tool_name,
                    "result": result,
                    "prompt": prompt,
                    "thumbnail_b64": image_b64,
                }
            )

        return result

    def _tiered_call(
        self,
        image_b64: str,
        prompt: str,
        tool_spec: dict[str, Any],
        tool_name: str,
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        # Tier 1: Haiku
        result = self._call_model(_HAIKU, image_b64, prompt, tool_spec, tool_name, fallback)
        if result.get("confidence", 0) >= _HIGH:
            return result

        # Tier 2: Sonnet
        result = self._call_model(_SONNET, image_b64, prompt, tool_spec, tool_name, fallback)
        if result.get("confidence", 0) >= _LOW:
            return result

        # Tier 3: Opus
        return self._call_model(_OPUS, image_b64, prompt, tool_spec, tool_name, fallback)

    def _call_model(
        self,
        model_id: str,
        image_b64: str,
        prompt: str,
        tool_spec: dict[str, Any],
        tool_name: str,
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        image_bytes = base64.b64decode(image_b64)
        request_kb = (len(image_bytes) + len(prompt.encode())) / 1024

        response = self._client.converse(
            modelId=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"image": {"format": "png", "source": {"bytes": image_bytes}}},
                        {"text": prompt},
                    ],
                }
            ],
            toolConfig={"tools": [{"toolSpec": tool_spec}]},
        )

        usage = response.get("usage", {})
        # Extract short name: "us.anthropic.claude-haiku-4-5-..." → "haiku-4-5"
        short = model_id.split("claude-")[-1].split("-2025")[0]
        if "claude" not in model_id:
            short = model_id
        console.print(
            f"[dim]    {short} | "
            f"{request_kb:.0f} KB | "
            f"tokens in={usage.get('inputTokens', '?')} out={usage.get('outputTokens', '?')}[/dim]"
        )

        return _parse_tool_response(response, tool_name, fallback)

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
# Image patch utilities                                                #
# ------------------------------------------------------------------ #


def crop_patch(
    image_dir: Path,
    bbox: tuple[float, float, float, float],
    tile_bbox: tuple[float, float, float, float],
    size: int = 256,
) -> np.ndarray | None:
    """Crop a satellite image patch for the given feature bbox.

    Looks for ortho tiles first, falls back to a blank patch if unavailable.
    Returns an (size, size, 3) uint8 array or None if no imagery.
    """
    ortho_dir = image_dir / "orthophoto"
    if not ortho_dir.exists() or not list(ortho_dir.glob("*.png")):
        return None

    feat_lon_min, feat_lat_min, feat_lon_max, feat_lat_max = bbox
    tile_lon_min, tile_lat_min, tile_lon_max, tile_lat_max = tile_bbox

    # Find the ortho tile that contains the feature centroid
    cx = (feat_lon_min + feat_lon_max) / 2
    cy = (feat_lat_min + feat_lat_max) / 2

    for png in ortho_dir.glob("*.png"):
        # Tiles are named row_col.png; read the matching .pol for geo bounds
        pol = png.with_suffix(".pol")
        if not pol.exists():
            continue
        # Parse LOAD_CENTER from .pol to determine tile coverage
        pol_text = pol.read_text(encoding="utf-8")
        for line in pol_text.splitlines():
            if line.startswith("LOAD_CENTER"):
                parts = line.split()
                if len(parts) >= 5:
                    plat, plon = float(parts[1]), float(parts[2])
                    h_m, w_m = float(parts[3]), float(parts[4])
                    # Approximate degree extent
                    h_deg = h_m / 111_320.0
                    w_deg = w_m / 111_320.0
                    if abs(cy - plat) < h_deg / 2 and abs(cx - plon) < w_deg / 2:
                        img = Image.open(png)
                        # Crop the feature's portion
                        img_w, img_h = img.size
                        # Pixel coords relative to tile
                        px_left = (feat_lon_min - (plon - w_deg / 2)) / w_deg * img_w
                        px_top = ((plat + h_deg / 2) - feat_lat_max) / h_deg * img_h
                        px_right = (feat_lon_max - (plon - w_deg / 2)) / w_deg * img_w
                        px_bottom = ((plat + h_deg / 2) - feat_lat_min) / h_deg * img_h
                        # Clamp and add buffer
                        buf = max(px_right - px_left, px_bottom - px_top) * 0.2
                        crop_box = (
                            max(0, int(px_left - buf)),
                            max(0, int(px_top - buf)),
                            min(img_w, int(px_right + buf)),
                            min(img_h, int(px_bottom + buf)),
                        )
                        patch = img.crop(crop_box).resize((size, size))
                        return np.array(patch)[:, :, :3]

    return None


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #


def _encode_image(image_rgb: np.ndarray) -> str:
    img = Image.fromarray(image_rgb.astype(np.uint8))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _fmt_tags(tags: dict[str, str]) -> str:
    return ", ".join(f"{k}={v}" for k, v in tags.items())


def _cache_key(image_b64: str, prompt: str) -> str:
    return hashlib.sha256(f"{image_b64}{prompt}".encode()).hexdigest()[:16]


def _parse_tool_response(
    response: dict[str, Any], tool_name: str, fallback: dict[str, Any]
) -> dict[str, Any]:
    for block in response.get("output", {}).get("message", {}).get("content", []):
        if block.get("toolUse", {}).get("name") == tool_name:
            inp: dict[str, Any] = block["toolUse"]["input"]
            return inp
    return fallback
