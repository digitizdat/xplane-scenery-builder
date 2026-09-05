"""Bedrock LLM classification: buildings, forests, and roads via vision API."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Any

import boto3
import numpy as np
from PIL import Image, ImageDraw
from rich.console import Console

console = Console()

# Model IDs — cross-region inference profiles (required for on-demand access)
_HAIKU = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
_SONNET = "us.anthropic.claude-sonnet-4-6"
_OPUS = "us.anthropic.claude-opus-4-6-v1"

# Models the classify stage depends on, in tier order.
_REQUIRED_MODELS = (_HAIKU, _SONNET, _OPUS)

# Confidence routing thresholds
_HIGH = 0.85
_LOW = 0.60
_REVIEW_THRESHOLD = 0.75


class BedrockPreflightError(RuntimeError):
    """Raised when a required Bedrock model cannot be invoked."""


class BedrockCredentialsError(RuntimeError):
    """Raised when AWS credentials are missing or expired (no usable session)."""


def _make_bedrock_client(region: str) -> Any:
    """Create a bedrock-runtime client, mapping credential problems to a clean error."""
    try:
        return boto3.client("bedrock-runtime", region_name=region)
    except Exception as exc:  # noqa: BLE001
        raise BedrockCredentialsError(
            "AWS credentials unavailable or expired. Reauthenticate "
            "(aws sso login) or source session-environment.sh, then retry.\n"
            f"  ({type(exc).__name__}: {exc})"
        ) from exc


def check_bedrock_access(region: str = "us-east-1") -> dict[str, str | None]:
    """Verify each required model can be invoked via the Converse API.

    Sends a tiny 1x1 image + minimal prompt to each model — the same call path
    the classifier uses — so region, access, and inference-profile problems all
    surface here rather than mid-run. Returns a mapping of ``model_id -> None``
    (ok) or ``model_id -> error message``.

    Raises BedrockCredentialsError if no usable AWS session exists (a single
    upfront failure, distinct from per-model invocation errors). Otherwise does
    not raise; callers decide policy on per-model failures.
    """
    import io as _io

    from PIL import Image as _Image

    client = _make_bedrock_client(region)
    buf = _io.BytesIO()
    _Image.new("RGB", (1, 1)).save(buf, format="PNG")
    png = buf.getvalue()

    results: dict[str, str | None] = {}
    for model_id in _REQUIRED_MODELS:
        try:
            client.converse(
                modelId=model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"image": {"format": "png", "source": {"bytes": png}}},
                            {"text": "Reply with OK."},
                        ],
                    }
                ],
                inferenceConfig={"maxTokens": 8},
            )
            results[model_id] = None
        except Exception as exc:  # noqa: BLE001 — report any failure to the caller
            # A credential error surfacing on the first call is a session problem,
            # not a model problem — raise it clearly rather than per-model.
            if _is_credential_error(exc):
                raise BedrockCredentialsError(
                    "AWS credentials unavailable or expired. Reauthenticate "
                    "(aws sso login) or source session-environment.sh, then retry.\n"
                    f"  ({type(exc).__name__}: {exc})"
                ) from exc
            results[model_id] = f"{type(exc).__name__}: {exc}"
    return results


def _is_credential_error(exc: Exception) -> bool:
    name = type(exc).__name__
    text = f"{name}: {exc}"
    markers = (
        "LoginTokenLoadError",
        "NoCredentialsError",
        "CredentialRetrievalError",
        "TokenRetrievalError",
        "UnauthorizedSSOTokenError",
        "ExpiredToken",
        "reauthenticate",
    )
    return any(m in text for m in markers)


def require_bedrock_access(region: str = "us-east-1") -> None:
    """Run the preflight check and raise BedrockPreflightError on any failure."""
    results = check_bedrock_access(region)
    failures = {m: msg for m, msg in results.items() if msg is not None}
    if failures:
        lines = "\n".join(f"  ✗ {m}\n      {msg}" for m, msg in failures.items())
        raise BedrockPreflightError(
            "Bedrock preflight failed — cannot invoke required model(s):\n"
            f"{lines}\n"
            "Check AWS credentials (aws sso login / source session-environment.sh), "
            "region (us-east-1), and Bedrock model access."
        )


# ------------------------------------------------------------------ #
# Tool specs for Bedrock Converse API                                  #
# ------------------------------------------------------------------ #

_BUILDING_TOOL: dict[str, Any] = {
    "name": "classify_building",
    "description": "Describe a building's physical appearance from satellite imagery.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "stories": {"type": "integer", "minimum": 1, "maximum": 50},
                "wall_material": {
                    "type": "string",
                    "enum": [
                        "brick",
                        "wood",
                        "concrete",
                        "glass",
                        "metal",
                        "stone",
                        "stucco",
                        "mixed",
                    ],
                },
                "wall_color": {
                    "type": "string",
                    "enum": [
                        "white",
                        "beige",
                        "tan",
                        "brown",
                        "gray",
                        "red",
                        "blue",
                        "green",
                        "dark",
                    ],
                },
                "window_density": {
                    "type": "string",
                    "enum": [
                        "none",
                        "sparse",
                        "moderate",
                        "dense",
                        "curtain_wall",
                    ],
                },
                "roof_type": {
                    "type": "string",
                    "enum": ["flat", "gable", "hip", "gambrel", "shed", "metal", "unknown"],
                },
                "height_m": {"type": "number"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": [
                "stories",
                "wall_material",
                "wall_color",
                "window_density",
                "roof_type",
                "height_m",
                "confidence",
            ],
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
        import threading

        self.output_dir = output_dir
        self._client = boto3.client("bedrock-runtime", region_name=region)
        self._cache_dir = output_dir / ".llm_cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._review_queue: list[dict[str, Any]] = []
        self._review_all = review_all
        self._lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────

    def classify_building(self, image: np.ndarray, osm_tags: dict[str, str]) -> dict[str, Any]:
        """Classify a building's physical appearance from satellite imagery."""
        prompt = (
            "The building to classify is outlined with a red rectangle; the rest is context.\n"
            "Describe this building's physical appearance from the satellite image.\n"
            "Determine: number of stories, wall material, wall color, "
            "window density (none/sparse/moderate/dense/curtain_wall), "
            "roof type (flat/gable/hip/gambrel/shed/metal), and height in meters.\n"
            f"OSM tags: {_fmt_tags(osm_tags)}\n"
            "Use the classify_building tool."
        )
        return self._classify(
            image,
            prompt,
            _BUILDING_TOOL,
            "classify_building",
            {
                "stories": 2,
                "wall_material": "mixed",
                "wall_color": "beige",
                "window_density": "moderate",
                "roof_type": "gable",
                "height_m": 8.0,
                "confidence": 0.0,
            },
        )

    def classify_forest(self, image: np.ndarray, esa_label: str, ndvi: float) -> dict[str, Any]:
        """Classify forest composition. Returns {species_mix, canopy_density, confidence}."""
        prompt = (
            "The area to classify is outlined with a red rectangle; the rest is context.\n"
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
            "The road to classify is outlined with a red rectangle; the rest is context.\n"
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
            item_id = hashlib.sha256(image_b64.encode()).hexdigest()[:8]
            with self._lock:
                self._review_queue.append(
                    {
                        "id": item_id,
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
        best = result

        # Tier 2: Sonnet
        result = self._call_model(_SONNET, image_b64, prompt, tool_spec, tool_name, fallback)
        if result.get("confidence", 0) >= _LOW:
            return result
        if result.get("confidence", 0) > best.get("confidence", 0):
            best = result

        # Tier 3: Opus — if unavailable, return best seen so far rather than
        # the zero-confidence fallback, so the Sonnet result is used instead of
        # always queuing for review.
        opus = self._call_model(_OPUS, image_b64, prompt, tool_spec, tool_name, fallback)
        if opus is fallback:
            return best
        return opus

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

        try:
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
        except Exception as exc:  # noqa: BLE001
            exc_str = f"{type(exc).__name__}: {exc}"
            if any(s in exc_str for s in ("AccessDenied", "ValidationException")):
                console.print(f"[yellow]    ⚠ {model_id} not available — skipping tier[/yellow]")
                return fallback
            raise

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
    tile_bbox: tuple[float, float, float, float],  # noqa: ARG001 — kept for API compatibility
    size: int = 384,
    context_m: float = 80.0,
) -> np.ndarray | None:
    """Crop a satellite patch with surrounding context and mark the feature.

    Crops at least ``context_m`` metres square centred on the feature (larger for
    big features) so the model and the human reviewer see the surroundings, then
    outlines the feature with a red rectangle. Geo-referencing uses the .pol
    SCALE (true metre extent) and cos(lat) longitude scaling, matching how the
    ortho is placed in the DSF. Returns an (size, size, 3) uint8 array, or None
    if no ortho imagery covers the feature.
    """
    ortho_dir = image_dir / "orthophoto"
    if not ortho_dir.exists() or not list(ortho_dir.glob("*.png")):
        return None

    feat_lon_min, feat_lat_min, feat_lon_max, feat_lat_max = bbox
    cx = (feat_lon_min + feat_lon_max) / 2
    cy = (feat_lat_min + feat_lat_max) / 2

    for png in ortho_dir.glob("*.png"):
        pol = png.with_suffix(".pol")
        if not pol.exists():
            continue
        plat = plon = w_m = h_m = None
        for line in pol.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if line.startswith("SCALE") and len(parts) >= 3:
                w_m, h_m = float(parts[1]), float(parts[2])
            elif line.startswith("LOAD_CENTER") and len(parts) >= 3:
                plat, plon = float(parts[1]), float(parts[2])
        if plat is None or plon is None or w_m is None or h_m is None:
            continue

        # Tile geographic extent (matches build_overlay's ortho placement)
        w_deg = w_m / (111_320.0 * math.cos(math.radians(plat)))
        h_deg = h_m / 111_320.0
        if abs(cy - plat) >= h_deg / 2 or abs(cx - plon) >= w_deg / 2:
            continue

        img = Image.open(png).convert("RGB")
        img_w, img_h = img.size
        west = plon - w_deg / 2
        north = plat + h_deg / 2
        px_left = (feat_lon_min - west) / w_deg * img_w
        px_right = (feat_lon_max - west) / w_deg * img_w
        px_top = (north - feat_lat_max) / h_deg * img_h
        px_bottom = (north - feat_lat_min) / h_deg * img_h

        # Context window: at least context_m square, and at least 1.4x the feature.
        win_x = max(context_m * img_w / w_m, (px_right - px_left) * 1.4)
        win_y = max(context_m * img_h / h_m, (px_bottom - px_top) * 1.4)
        mid_x = (px_left + px_right) / 2
        mid_y = (px_top + px_bottom) / 2
        left = max(0, int(mid_x - win_x / 2))
        top = max(0, int(mid_y - win_y / 2))
        right = min(img_w, int(mid_x + win_x / 2))
        bottom = min(img_h, int(mid_y + win_y / 2))
        if right - left < 2 or bottom - top < 2:
            return None

        patch = img.crop((left, top, right, bottom)).resize((size, size))

        # Outline the feature with a red rectangle in the resized frame.
        sx = size / (right - left)
        sy = size / (bottom - top)
        rx0, ry0 = (px_left - left) * sx, (px_top - top) * sy
        rx1, ry1 = (px_right - left) * sx, (px_bottom - top) * sy
        ImageDraw.Draw(patch).rectangle([rx0, ry0, rx1, ry1], outline=(255, 0, 0), width=3)
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
