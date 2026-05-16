# Asset Catalog

## Overview

`assets/catalog.yaml` maps geospatial features (buildings, land cover) to
X-Plane art assets. The pipeline reads OSM/ESA data, classifies each feature,
then looks up the corresponding X-Plane virtual library path from this catalog.

## Virtual Library Paths

X-Plane uses a **virtual library system** to decouple scenery DSF files from
the physical location of art assets on disk. A DSF references virtual paths
like `lib/buildings/facades/generic/low_modern_01.fac` — these don't exist as
real files at that path.

At load time, X-Plane scans `library.txt` files across all scenery packages.
Each `library.txt` contains EXPORT directives that map virtual paths to real
files:

```
EXPORT lib/buildings/facades/generic/low_modern_01.fac    US/urban_high/objects/ul_modern01.fac
```

This tells X-Plane: when a DSF asks for the virtual path on the left, serve
the real file on the right (relative to the scenery package root).

The real `.fac` and `.for` files live under:
```
Resources/default scenery/1000 autogen/    — facades, autogen objects
Resources/default scenery/900 forests/     — forest definitions
Resources/default scenery/1200 forests/    — XP12 seasonal forests
```

## Facades (.fac)

Facades are extruded building shells. The catalog maps OSM building types and
footprint area to facade virtual paths:

```yaml
facades:
  residential:
    small:   lib/buildings/facades/generic/low_modern_01.fac    # <200 m²
    medium:  lib/buildings/facades/generic/mid_classic_01.fac   # 200–1000 m²
    large:   lib/buildings/facades/generic/mid_modern_01.fac    # >1000 m²
```

The DSF writer places each building as a `BEGIN_POLYGON` referencing the facade
index, with the building height as the parameter and the footprint coordinates
as the winding.

### Available facade categories (X-Plane 12)

| Virtual path prefix | Use case |
|---|---|
| `lib/buildings/facades/generic/low_*` | Small residential/generic |
| `lib/buildings/facades/generic/mid_*` | Medium buildings |
| `lib/buildings/facades/generic/high_*` | Tall buildings |
| `lib/buildings/facades/commercial/low_commercial_*` | Shops, offices |
| `lib/buildings/facades/industrial/warehouse_*` | Industrial, agricultural |

## Forests (.for)

Forest definitions describe vegetation density, tree species mix, and spacing.
The catalog maps ESA WorldCover land classes and Köppen climate zones to forest
virtual paths:

```yaml
forests:
  tree_cover:
    temperate:   broadleaf.for
    continental: broadleaf_cold.for
    polar:       conifer_cold.for
```

Some paths use the `lib/g8/` prefix (shrubs, wetlands) — these are resolved
through the `900 forests/library.txt` and `1200 forests/library.txt` EXPORT
directives. Others (like `broadleaf.for`) are direct filenames in the
`900 forests/` directory, which X-Plane loads implicitly.

### Available forest types (X-Plane 12, 900 forests)

| File | Biome |
|---|---|
| `broadleaf.for` | Temperate deciduous |
| `broadleaf_cold.for` | Cold deciduous |
| `broadleaf_sparse.for` | Open woodland |
| `conifer.for` | Temperate conifer |
| `conifer_cold.for` | Boreal conifer |
| `mixed.for` | Mixed forest / cropland |
| `tropical.for` | Tropical forest |
| `savanna.for` | Savanna / dry grassland |
| `tundra.for` | Arctic / alpine |
| `med_forest.for` | Mediterranean |
| `temp_shrub.for` | Temperate shrubland |

## Climate Zone Classification

The catalog uses a simplified Köppen classification based on latitude:

| Zone | Latitude range | Example |
|---|---|---|
| tropical | 0°–23° | Amazon, Congo |
| arid | 23°–35° | Sahara, Mojave |
| temperate | 35°–55° | Green Bank WV, Paris |
| continental | 55°–66° | Moscow, Edmonton |
| polar | >66° | Svalbard, Antarctica |

The `AssetCatalog.get_forest()` method determines the zone from the tile's
centre latitude and looks up the corresponding path.

## Validating the Catalog

To check that all virtual paths in the catalog resolve against an X-Plane
install:

```bash
uv run xplane-gen catalog validate --xplane-path "/path/to/X-Plane 12"
```

To find valid virtual paths in an X-Plane install, grep the library files:

```bash
# Find all exported .for paths
grep -rh "^EXPORT.*\.for" "/path/to/X-Plane 12/Resources/default scenery" \
    --include="library.txt" | awk '{print $2}' | sort | uniq

# Find all exported .fac paths
grep -rh "^EXPORT.*\.fac" "/path/to/X-Plane 12/Resources/default scenery" \
    --include="library.txt" | grep "lib/" | awk '{print $2}' | sort | uniq
```
