"""Analyze X-Plane facade textures with LLM vision to extract physical attributes.

Reads all exported .fac files, extracts their wall texture, sends to Bedrock
Claude for classification, and outputs a facade_attributes.yaml catalog.
"""

from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import boto3
import yaml
from PIL import Image
from rich.console import Console

console = Console()

XP_AUTOGEN = Path(
    "/Users/martin/Library/Application Support/Steam/steamapps/common/"
    "X-Plane 12/Resources/default scenery/1000 autogen"
)

_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

_TOOL: dict[str, Any] = {
    "name": "describe_facade",
    "description": "Describe the physical appearance of a building facade texture.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
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
                "window_shape": {
                    "type": "string",
                    "enum": ["rectangular", "square", "arched", "narrow", "wide", "none"],
                },
                "window_density": {
                    "type": "string",
                    "enum": ["none", "sparse", "moderate", "dense", "curtain_wall"],
                },
                "stories_min": {"type": "integer", "minimum": 1, "maximum": 60},
                "stories_max": {"type": "integer", "minimum": 1, "maximum": 60},
                "roof_type": {
                    "type": "string",
                    "enum": ["flat", "gable", "hip", "gambrel", "shed", "unknown"],
                },
                "roof_color": {
                    "type": "string",
                    "enum": [
                        "gray",
                        "brown",
                        "red",
                        "green",
                        "black",
                        "white",
                        "metal",
                        "unknown",
                    ],
                },
                "style": {
                    "type": "string",
                    "enum": [
                        "modern",
                        "classic",
                        "industrial",
                        "residential",
                        "warehouse",
                        "retail",
                        "highrise",
                    ],
                },
            },
            "required": [
                "wall_material",
                "wall_color",
                "window_shape",
                "window_density",
                "stories_min",
                "stories_max",
                "roof_type",
                "roof_color",
                "style",
            ],
        }
    },
}


def main() -> None:
    client = boto3.client("bedrock-runtime", region_name="us-east-1")

    # Parse library.txt to get vpath → real .fac file mapping
    facades = _parse_exported_facades()
    console.print(f"[cyan]Found {len(facades)} exported facade paths[/cyan]")

    # Extract texture info from each .fac file
    facade_textures = _extract_textures(facades)
    console.print(f"[cyan]{len(facade_textures)} facades with resolvable textures[/cyan]")

    # Deduplicate by texture path (many facades share the same atlas)
    unique_textures: dict[str, list[str]] = {}
    for vpath, tex_path in facade_textures.items():
        unique_textures.setdefault(str(tex_path), []).append(vpath)
    console.print(f"[cyan]{len(unique_textures)} unique texture files to analyze[/cyan]")

    # Classify each unique texture
    results: dict[str, dict[str, Any]] = {}

    def _classify_texture(tex_path: str, vpaths: list[str]) -> tuple[str, dict[str, Any] | None]:
        img = _load_and_resize(Path(tex_path))
        if img is None:
            return tex_path, None
        return tex_path, _call_llm(client, img, vpaths[0])

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(_classify_texture, tp, vps): tp
            for tp, vps in unique_textures.items()
        }
        for i, fut in enumerate(as_completed(futures), 1):
            tex_path, result = fut.result()
            if result:
                results[tex_path] = result
            if i % 5 == 0:
                console.print(f"[dim]  {i}/{len(unique_textures)} textures analyzed[/dim]")

    # Build the output: vpath → attributes
    facade_catalog: dict[str, dict[str, Any]] = {}
    for tex_path, vpaths in unique_textures.items():
        attrs = results.get(tex_path)
        if not attrs:
            continue
        for vpath in vpaths:
            # Merge .fac floor info with LLM visual attributes
            fac_info = facades[vpath]
            entry = dict(attrs)
            if fac_info.get("floors_min"):
                entry["stories_min"] = fac_info["floors_min"]
            if fac_info.get("floors_max"):
                entry["stories_max"] = fac_info["floors_max"]
            facade_catalog[vpath] = entry

    # Write output
    out_path = Path("assets/facade_attributes.yaml")
    out_path.write_text(
        yaml.dump(facade_catalog, default_flow_style=False, sort_keys=True),
        encoding="utf-8",
    )
    console.print(f"[green]Wrote {len(facade_catalog)} facade entries → {out_path}[/green]")


def _parse_exported_facades() -> dict[str, dict[str, Any]]:
    """Parse library.txt for EXPORT lines with .fac, return vpath → {real_path, floors}."""
    lib_txt = XP_AUTOGEN / "library.txt"
    facades: dict[str, dict[str, Any]] = {}

    for line in lib_txt.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.startswith("EXPORT ") or ".fac" not in line:
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        vpath = parts[1]
        real_rel = parts[2].replace("\\", "/")
        real_path = XP_AUTOGEN / real_rel
        if real_path.exists():
            info = _parse_fac_floors(real_path)
            info["real_path"] = str(real_path)
            facades[vpath] = info

    return facades


def _parse_fac_floors(fac_path: Path) -> dict[str, Any]:
    """Extract FLOORS_MIN/MAX from a .fac file."""
    info: dict[str, Any] = {}
    for line in fac_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("FLOORS_MIN"):
            info["floors_min"] = int(line.split()[1])
        elif line.startswith("FLOORS_MAX"):
            info["floors_max"] = int(line.split()[1])
    return info


def _extract_textures(facades: dict[str, dict[str, Any]]) -> dict[str, Path]:
    """For each facade, find its wall TEXTURE (albedo) path."""
    result: dict[str, Path] = {}
    for vpath, info in facades.items():
        fac_path = Path(info["real_path"])
        tex_path = _find_wall_texture(fac_path)
        if tex_path and tex_path.exists():
            result[vpath] = tex_path
    return result


def _find_wall_texture(fac_path: Path) -> Path | None:
    """Parse .fac file for the first TEXTURE line after SHADER_WALL."""
    in_wall = False
    for line in fac_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip() == "SHADER_WALL":
            in_wall = True
        elif line.startswith("SHADER_") and in_wall:
            break
        elif in_wall and line.startswith("TEXTURE ") and "NORMAL" not in line and "LIT" not in line:
            tex_rel = line.split(None, 1)[1].strip().replace("\\", "/")
            tex_path = (fac_path.parent / tex_rel).resolve()
            if tex_path.exists():
                return tex_path
            # Try .dds extension (X-Plane ships DDS, .fac references .png)
            dds_path = tex_path.with_suffix(".dds")
            if dds_path.exists():
                return dds_path
            return None
    return None


def _load_and_resize(tex_path: Path, max_size: int = 512) -> bytes | None:
    """Load texture PNG and resize for LLM input."""
    try:
        img = Image.open(tex_path)
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def _call_llm(client: Any, image_bytes: bytes, vpath: str) -> dict[str, Any] | None:
    """Call Bedrock to classify a facade texture."""
    prompt = (
        f"This is a texture atlas for an X-Plane building facade: {vpath}\n"
        "Analyze the wall sections visible in this texture. Describe the physical "
        "appearance: wall material, wall color, window shape and density, "
        "approximate story range this would suit, roof type if visible, "
        "roof color, and overall architectural style.\n"
        "Use the describe_facade tool."
    )

    try:
        response = client.converse(
            modelId=_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"image": {"format": "png", "source": {"bytes": image_bytes}}},
                        {"text": prompt},
                    ],
                }
            ],
            toolConfig={"tools": [{"toolSpec": _TOOL}]},
        )
    except Exception as exc:
        console.print(f"[red]  Error classifying {vpath}: {exc}[/red]")
        return None

    for block in response.get("output", {}).get("message", {}).get("content", []):
        if block.get("toolUse", {}).get("name") == "describe_facade":
            return block["toolUse"]["input"]
    return None


if __name__ == "__main__":
    main()
