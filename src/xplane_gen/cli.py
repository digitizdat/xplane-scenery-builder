"""xplane-gen CLI entry point."""

from __future__ import annotations

import click
from rich.console import Console

console = Console()


@click.group()
def cli() -> None:
    """X-Plane GenAI Scenery Generator."""


@cli.command("spike")
@click.option("--output", default="./spike_output", show_default=True)
@click.option("--dsftool", default=None, help="Path to DSFTool binary.")
def spike(output: str, dsftool: str | None) -> None:
    """Task 1 spike: compile a hardcoded test DSF and verify DSFTool works."""
    from pathlib import Path

    from xplane_gen.dsf import DsfWriter, ExclusionZone, ForestFeature, find_dsftool

    tool = Path(dsftool) if dsftool else find_dsftool()
    console.print(f"[green]DSFTool:[/green] {tool}")

    writer = DsfWriter(tile_west=-123, tile_south=47)
    writer.add_forest(
        ForestFeature(
            resource="lib/g8/trees_decid_cld_wet.for",
            density=0.8,
            coords=[
                (-122.6, 47.6),
                (-122.5, 47.6),
                (-122.5, 47.7),
                (-122.6, 47.7),
                (-122.6, 47.6),
            ],
        )
    )
    writer.add_exclusion(ExclusionZone("for", -123, 47, -122, 48))

    out = Path(output)
    dsf = writer.compile(out, dsftool=tool)
    console.print(f"[green]✓ DSF written:[/green] {dsf}")
    console.print(f"[dim]Size: {dsf.stat().st_size:,} bytes[/dim]")
    console.print(
        "\n[bold]Install in X-Plane:[/bold]\n"
        f"  cp -r {out} '/path/to/X-Plane/Custom Scenery/xplane-gen-spike'"
    )


@cli.command("fetch-osm")
@click.option("--bbox", required=True, help="lat_min,lon_min,lat_max,lon_max")
@click.option("--output", default=".", show_default=True)
def fetch_osm(bbox: str, output: str) -> None:
    """Task 2: Fetch OSM buildings, land use, and roads for a bounding box."""
    from xplane_gen.osm import fetch_tile

    lat_min, lon_min, lat_max, lon_max = map(float, bbox.split(","))
    fetch_tile(lat_min, lon_min, lat_max, lon_max, output)


@cli.command("classify-land")
@click.option("--bbox", required=True, help="lat_min,lon_min,lat_max,lon_max")
@click.option("--output", default=".", show_default=True)
def classify_land(bbox: str, output: str) -> None:
    """Task 3: Fetch ESA WorldCover and classify land cover polygons."""
    from xplane_gen.landcover import classify_tile

    lat_min, lon_min, lat_max, lon_max = map(float, bbox.split(","))
    classify_tile(lat_min, lon_min, lat_max, lon_max, output)


@cli.command("generate")
@click.option("--bbox", default=None, help="lat_min,lon_min,lat_max,lon_max")
@click.option("--placename", default=None, help="Place name to geocode (e.g. 'Green Bank, WV').")
@click.option("--output", default="./output", show_default=True)
@click.option("--dry-run", is_flag=True)
@click.option("--auto", is_flag=True, help="Skip human review, use best-guess.")
@click.option("--dsftool", default=None)
@click.option(
    "--ortho-source",
    type=click.Choice(["sentinel2", "naip"]),
    default=None,
    help="Satellite imagery source for orthophoto ground texture. Omit to skip.",
)
@click.option("--regen", is_flag=True, help="Regenerate from cached data without re-downloading.")
@click.option("--review-all", is_flag=True, help="Force human review of all LLM classifications.")
@click.option("--no-roads", is_flag=True, help="Suppress default road network in ortho areas.")
def generate(
    bbox: str | None,
    placename: str | None,
    output: str,
    dry_run: bool,
    auto: bool,
    dsftool: str | None,
    ortho_source: str | None,
    regen: bool,
    review_all: bool,
    no_roads: bool,
) -> None:
    """Task 8: End-to-end tile generation pipeline."""
    from pathlib import Path

    from xplane_gen.pipeline import TileProcessor

    if bbox and placename:
        raise click.UsageError("--bbox and --placename are mutually exclusive.")
    if not bbox and not placename:
        raise click.UsageError("Either --bbox or --placename is required.")

    if placename:
        from xplane_gen.geocode import placename_to_bbox

        lat_min, lon_min, lat_max, lon_max = placename_to_bbox(placename)
        console.print(
            f"[cyan]Geocoded[/cyan] {placename!r} → "
            f"{lat_min:.4f},{lon_min:.4f},{lat_max:.4f},{lon_max:.4f}"
        )
    else:
        lat_min, lon_min, lat_max, lon_max = map(float, bbox.split(","))  # type: ignore[union-attr]

    proc = TileProcessor(
        lat_min,
        lon_min,
        lat_max,
        lon_max,
        Path(output),
        dry_run=dry_run,
        auto=auto,
        dsftool=Path(dsftool) if dsftool else None,
        ortho_source=ortho_source,
        regen=regen,
        review_all=review_all,
        no_roads=no_roads,
    )
    proc.run()


@cli.command("catalog")
@click.argument("subcommand", type=click.Choice(["validate"]))
@click.option("--xplane-path", default=None)
def catalog(subcommand: str, xplane_path: str | None) -> None:
    """Task 4: Asset catalog operations."""
    from xplane_gen.catalog import AssetCatalog

    cat = AssetCatalog()
    if subcommand == "validate":
        if xplane_path:
            from pathlib import Path

            cat.validate_catalog(Path(xplane_path))
        else:
            console.print("[yellow]No --xplane-path given; skipping file existence check.[/yellow]")
            console.print(
                f"Catalog loaded: {len(cat._facades)} facade entries, "
                f"{len(cat._forests)} forest entries."
            )


@cli.command("review")
@click.option("--queue", default="review_queue.json", show_default=True)
@click.option("--output", default="resolved_queue.json", show_default=True)
def review(queue: str, output: str) -> None:
    """Task 10: HITL review CLI for classification queue."""
    from xplane_gen.review import run_review

    run_review(queue, output)
