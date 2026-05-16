"""HITL review CLI: interactive terminal review of the classification queue."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

_VALID_TYPES = {
    "residential", "commercial", "industrial", "religious", "agricultural", "generic",
    "deciduous", "conifer", "mixed",
    "asphalt", "gravel", "dirt", "concrete",
}


def run_review(queue_path: str, output_path: str) -> None:
    """Interactively review review_queue.json and write resolved_queue.json."""
    queue_file = Path(queue_path)
    if not queue_file.exists():
        console.print(f"[red]Queue file not found: {queue_file}[/red]")
        return

    items: list[dict[str, Any]] = json.loads(queue_file.read_text(encoding="utf-8"))
    if not items:
        console.print("[green]Review queue is empty — nothing to review.[/green]")
        _write_resolved([], Path(output_path))
        return

    console.print(
        Panel(
            f"[bold]{len(items)} items[/bold] need review.\n"
            "Press [bold]Enter[/bold] to confirm the suggestion, "
            "or type a replacement building type.",
            title="HITL Review",
        )
    )

    resolved = _review_items(items)
    out = Path(output_path)
    _write_resolved(resolved, out)
    console.print(f"\n[green]✓ Resolved {len(resolved)} items → {out}[/green]")


def _review_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Walk through items, grouping similar ones for batch approval."""
    resolved: list[dict[str, Any]] = []
    i = 0
    while i < len(items):
        item = items[i]
        result = item.get("result", item)
        guess = (
            result.get("building_type")
            or result.get("species_mix")
            or result.get("surface_type")
            or "unknown"
        )

        # Find similar items (same classification guess) ahead in queue
        similar_indices = [
            j for j in range(i + 1, len(items))
            if (items[j].get("result", items[j]).get("building_type")
                or items[j].get("result", items[j]).get("species_mix")
                or items[j].get("result", items[j]).get("surface_type")) == guess
        ]

        _show_item(item, i + 1, len(items))

        if similar_indices:
            console.print(
                f"[dim]{len(similar_indices)} similar item(s) also classified as "
                f"[bold]{guess}[/bold]. Apply decision to all? (y/n)[/dim]"
            )
            batch_answer = _prompt(f"  [{guess}] apply to all? (y/n): ").strip().lower()
            apply_to_all = batch_answer in {"y", "yes", ""}
        else:
            apply_to_all = False

        decision = _prompt(f"  classification [{guess}]: ").strip()
        if not decision:
            decision = guess
        decision = _validate_type(decision, guess)

        item = dict(item)
        item["human_decision"] = decision
        resolved.append(item)

        if apply_to_all:
            for j in similar_indices:
                sibling = dict(items[j])
                sibling["human_decision"] = decision
                resolved.append(sibling)
            # Skip the similar items we just batch-resolved
            processed = set(similar_indices)
            remaining = [items[k] for k in range(i + 1, len(items)) if k not in processed]
            items = items[: i + 1] + remaining
        i += 1

    return resolved


def _show_item(item: dict[str, Any], index: int, total: int) -> None:
    result = item.get("result", item)
    tool = item.get("tool", "classify_building")
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_row("[dim]Type[/dim]", tool)
    table.add_row("[dim]Confidence[/dim]", f"{result.get('confidence', 0):.0%}")
    guess = (
        result.get("building_type")
        or result.get("species_mix")
        or result.get("surface_type")
        or "unknown"
    )
    table.add_row("[dim]Suggestion[/dim]", f"[bold]{guess}[/bold]")
    if "height_m" in result:
        table.add_row("[dim]Height[/dim]", f"{result['height_m']:.1f} m")
    if "canopy_density" in result:
        table.add_row("[dim]Density[/dim]", f"{result['canopy_density']:.2f}")
    if "lane_count" in result:
        table.add_row("[dim]Lanes[/dim]", str(result["lane_count"]))

    # Save thumbnail if present
    if thumb := item.get("thumbnail_b64"):
        try:
            import base64

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(base64.b64decode(thumb))
                tmp_name = tmp.name
            table.add_row("[dim]Thumbnail[/dim]", f"[link=file://{tmp_name}]{tmp_name}[/link]")
        except Exception:  # nosec B110 — thumbnail display is optional; any failure is non-fatal
            pass

    console.print(Panel(table, title=f"Item {index}/{total}"))


def _prompt(message: str) -> str:
    """Read a line from stdin; returns empty string on EOF (for testing)."""
    try:
        return input(message)
    except EOFError:
        return ""


def _validate_type(value: str, fallback: str) -> str:
    if value in _VALID_TYPES:
        return value
    console.print(
        f"[yellow]Unknown type '{value}', valid: {', '.join(sorted(_VALID_TYPES))}. "
        f"Using '{fallback}'.[/yellow]"
    )
    return fallback


def _write_resolved(items: list[dict[str, Any]], path: Path) -> None:
    path.write_text(json.dumps(items, indent=2), encoding="utf-8")


def load_resolved_decisions(resolved_path: Path) -> dict[str, str]:
    """Return a mapping of cache_key → human_decision from a resolved queue file.

    Used by the pipeline to apply human decisions without re-calling Bedrock.
    """
    if not resolved_path.exists():
        return {}
    items: list[dict[str, Any]] = json.loads(resolved_path.read_text(encoding="utf-8"))
    return {
        item["thumbnail_b64"][:16]: item["human_decision"]
        for item in items
        if "thumbnail_b64" in item and "human_decision" in item
    }
