# X-Plane 12 Default Library Asset Inventory

Generated from: `Resources/default scenery/*/library.txt`
Total exported virtual paths: **20,539**

## Summary by Asset Type

| Extension | Count | Description |
|-----------|-------|-------------|
| `.ter` | 9,818 | Terrain textures (base mesh, not overlay-usable) |
| `.pol` | 8,351 | Draped polygons (ground textures, pavement) |
| `.obj` | 7,158 | 3D objects (buildings, vehicles, clutter) |
| `.fac` | 4,237 | Facades (extruded building shells) |
| `.for` | 1,385 | Forest/vegetation definitions |
| `.agp` | 631 | Autogen point groups |
| `.ags` | 565 | Autogen string groups |
| `.agb` | 470 | Autogen block groups |
| `.lin` | 437 | Line features (roads, markings, paths) |
| `.dcl` | 211 | Decals |
| `.str` | 58 | String objects (rows of items) |
| `.net` | 8 | Road network definitions |

## Overlay-Usable Asset Categories

These can be placed in overlay DSFs (our use case):

### Facades (.fac) — 4,237 total

**Buildings** (`lib/buildings/facades/`):
- `generic/low_modern_01.fac` through `high_universal_02_flat.fac` — 25 variants
- `commercial/low_commercial_01.fac` through `_08.fac` — 8 variants
- `industrial/warehouse_01_45x45.fac` through `_10_90x90.fac` — 10 variants

**Fencing** (`lib/constructions/fencing/`):
- Brick walls: `fence_Bricks_01.fac` – `_04.fac`
- Hedges: `fence_Hedge_01.fac` – `_04.fac`, `fence_HedgeSmall_01.fac` – `_02.fac`
- Mesh/chain-link: `fence_Mesh_01.fac` – `_04.fac`, `fence_MeshHigh_01.fac` – `_08.fac`
- Metal: `fence_Metal_01.fac` – `_04.fac`, `fence_MetalHigh_01.fac` – `_04.fac`
- Wood: `fence_Wood_01.fac` – `_09.fac`
- Walls: `wall/beige_1.fac`, `bricks_1.fac` – `_4.fac`, `concrete_plates_1.fac`, `stone_1.fac`
- Wooden rural: `wooden/plank_high_1.fac`, `rail_1.fac` – `_4.fac`, `sheep_1.fac`
- Industrial: `fencing_Industrial_1.fac`, `_2.fac`
- Garden: `fencing_Garden_1.fac`

### Forests & Vegetation (.for) — 1,385 total

**Species-specific forests** (`lib/vegetation/forests/`):
- Broadleaves: `cold.for`, `cold_low.for`, `hot.for`, `hot_dry.for`, `temperate.for`, `very_hot.for`, `very_hot_dry.for`, `warm.for`, `warm_dry.for`
- Conifers: `cold.for`, `cold_low.for`, `hot_dry.for`, `temperate.for`, `warm.for`, `warm_dry.for`
- Mixed: `cold.for`, `cold_low.for`, `hot.for`, `hot_dry.for`, `temperate.for`, `very_hot.for`, `very_hot_dry.for`, `warm.for`, `warm_dry.for`

**Individual tree species** (`lib/vegetation/trees/`):
- Deciduous (96): oak, maple, elm, birch, aspen, red_oak, black_locust, shrubs — each in big/medium/small/tall
- Coniferous (12): fir, pine, spruce — each in big/medium/small/tall
- Evergreen (14): cypress, brazil_nut, kapok_tree, banana_plant
- Palm (10): coconut_palm, date_palm, mexican_palm — each in big/medium/small

**Ground cover** (`lib/vegetation/planters/`):
- Ground-level (48): grass_dry, grass_green, mix_hot, rocks_grass, rocks_shrubs, shrubs_green, shrubs_red
- Raised planters (48): same variants

**Autogen vegetation** (`lib/vegetation/`):
- `AG_temp_1.for`, `AG_temp_2.for` — temperate autogen
- `AG_hot_dry_1.for` — hot/dry autogen

### 3D Objects (.obj) — 7,158 total

**Street furniture** (`lib/street/`):
- Waste management (59): dumpsters, bins, recycling containers
- Furniture (22): benches, bollards, bike racks
- Streetlights (18): various pole styles
- Various (17): mailboxes, fire hydrants, newspaper boxes

**Vehicles** (`lib/vehicles/static/`):
- Trucks (116): various types and colors
- Lifts (35): forklifts, scissor lifts
- RVs (32): motorhomes, campers
- Caravans (23): travel trailers
- Tower cranes (18)
- Emergency (13): fire trucks, ambulances
- Construction (6): excavators, bulldozers

**Cars** (`lib/cars/`):
- `car_static.obj`, `car_or_truck_static.obj` — generic parked vehicles
- `bus_static.obj`, `taxi_yellow.obj`, `police_car.obj`

**Industrial** (`lib/industrial_area/`):
- Container stacks (10): various heights and arrangements
- Shipping containers: 20ft (29) and 40ft (29) in various colors
- Goods (54): pallets, crates, barrels, lumber
- Construction (65): scaffolding, materials, equipment
- Storage tanks (10): cylindrical tanks
- Cranes (5): container cranes

**Public areas** (`lib/public_area/`):
- Sports (15): basketball hoops, soccer goals, tennis nets, baseball cages, golf holes
- Camping (27): chairs, tables, coolers
- Playground (4): swings, slides

**Garden** (`lib/garden/`):
- Furniture (34): tables, chairs, umbrellas, BBQ grills
- Pools (1)

**Buildings equipment** (`lib/buildings/equipment/`):
- HVAC units, satellite dishes, rooftop equipment (22)

**Solar** (`lib/constructions/solar_plant/`):
- `solar_panel_1.obj`, `solar_panel_2.obj`, `solar_panel_3.obj`
- `solar_panel_1_row.str`, `_2_row.str`, `_3_row.str` (string placement)

**Antennas** (`lib/constructions/antennas/`):
- 33 variants: cell towers, radio masts, satellite dishes

**Ships** (`lib/ships/`):
- Powered vessels (290): cargo ships, ferries, fishing boats by size class
- Sailboats: various sizes

### Draped Polygons (.pol) — usable subset

**Urban ground** (`lib/terrain/urban/`):
- `asphalt_worn_1.pol` through `_6.pol` — parking lots, worn pavement
- `sidewalk_1.pol` — pedestrian areas

**Airport ground** (`lib/airport/ground/terrain/`):
- Various grass, soil, gravel textures (34 variants)

### Line Features (.lin)

**Walkways** (`lib/g10/autogen/walkway/`):
- `dirt.lin`, `concrete.lin`, `asphalt.lin`

**Airport markings** (`lib/airport/lines/`):
- 55 line types for taxiways, hold positions, etc.

### Road Networks (.net)

- `lib/g10/roads.net` — global road network
- `lib/us/roads.net` — US-specific roads
- `lib/g10/roads_EU.net` — European roads

## OSM Tags → Asset Mapping Opportunities

| OSM Tag | Available Assets | Current Status |
|---------|-----------------|----------------|
| `building=*` | 43 facade types | ✅ Using 18 |
| `natural=tree_row` | 96+ individual tree `.for` files | ❌ Not placed |
| `barrier=fence/wall/hedge` | 47 fencing `.fac` types | ❌ Not placed |
| `landuse=industrial` | 204 industrial objects | ❌ Not placed |
| `leisure=pitch` | 15 sports objects | ❌ Not placed |
| `amenity=parking` | `asphalt_worn_*.pol` + car objects | ❌ Not placed |
| `power=tower/line` | `lib/constructions/antennas/` | ❌ Not placed |
| `man_made=antenna` | 33 antenna objects | ❌ Not placed |
| `highway=street_lamp` | 18 streetlight objects | ❌ Not placed |
| `natural=water` | Ship objects for harbors | ❌ Not placed |
| `landuse=solar` | 6 solar panel objects/strings | ❌ Not placed |
| `barrier=gate` | Gate `.fac` types | ❌ Not placed |
| `amenity=bench` | `lib/street/furniture/` | ❌ Not placed |
