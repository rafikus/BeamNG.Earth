# Polish LoD2 roofs (GUGiK 2017), opt-in

GUGiK (Poland's Head Office of Geodesy and Cartography) publishes LoD2 building models (CityGML 2.0, state 2017) for
236 powiats in 10 voivodeships. This adds them as one more source of the measured-roof pipeline the German states,
Switzerland, Estonia and Vienna already use (`tools/build_lod2_roofs.py` reads the CityGML once into a few bytes per
building; `server/lod2roofs.py` joins each record to the footprint it stands in). Each building gets its measured roof
shape, roof height, total height and, for pitched roofs, the ridge's direction. The footprints stay the map's (LOD1,
`docs/POLAND_LOD1.md`, or Overture / OSM).

## Use

Nothing is published yet, so for now the shards are built and read locally:

```powershell
# 1. build (once; ~190 MB of download for three powiats, ~7 min, sequential and gentle with GUGiK)
$env:BNE_LOD2_ROOT = 'G:\...\lod2-pl-work'
$env:BNE_LOD2_PL_POWIATS = '1661,1261,1465'        # Opole, Kraków, Warszawa; unset for all 236
python tools/build_lod2_roofs.py fetch PL 1        # resumable: <root>/out/PL.done, PL.csv.gz
python tools/build_lod2_roofs.py shards G:\...\lod2-pl-data\lod2-pl PL

# 2. play: the server reads the local folder instead of the site (it holds <dir>/lod2-pl/<x>/<y>.npz)
$env:BNE_PL_LOD2 = '1'
$env:BNE_LOD2_DIR = 'G:\...\lod2-pl-data'
```

Without `BNE_PL_LOD2=1` nothing changes: `lod2roofs.SOURCES` is the same four countries, no request is made in Poland.
With it, a map tile inside Poland's box asks for the `lod2-pl` shards (a folder of the site once published, the local
folder with `BNE_LOD2_DIR`). Outside the ten voivodeships' powiats there is simply no record and the roofs are predicted
as everywhere else. `tools/build_lod2_roofs.py` needs the Polish LOD1 index (`server/polandlod1.Manifest`) only to list the
powiats: it takes `BNE_LOD2_PL_INDEX`, else the copy in the server's cache (`~/.cache/beamng-earth/polandlod1/`), else
fetches the pinned one.

## The data

- **Download.** One ZIP per powiat: `https://opendata.geoportal.gov.pl/InneDane/Budynki3D/LOD2/<TERYT>_gml.zip` (TERYT =
  the 4-digit powiat code: Opole 1661 is 12.5 MB, Kraków 1261 60 MB, Warszawa 1465 116 MB). A powiat without a model
  answers 404 (the tool counts it as empty). There is no index file; the bulk `LOD2_2017.zip` is 4 GB and is not used.
  The powiat codes are those of the first four digits of the LOD1 index's file names (433 files, 236 powiats with LoD2
  after the voivodeship filter).
- **Coverage.** The voivodeships with models, by TERYT prefix: 04 kujawsko-pomorskie, 06 lubelskie, 12 małopolskie, 14
  mazowieckie, 16 opolskie, 18 podkarpackie, 20 podlaskie, 24 śląskie, 26 świętokrzyskie, 28 warmińsko-mazurskie.
  **Łódzkie (10) has none**, nor have the other five (dolnośląskie 02, lubuskie 08, pomorskie 22, wielkopolskie 30,
  zachodniopomorskie 32): there the roofs stay predicted.
- **State.** The models describe 2017 (the files date from 2018-2019, the roofs come from airborne laser scanning,
  `zrodloDach` ALS_II). LOD1 is 2024, so a building built after 2017 has no record and a demolished one may still have
  one (it joins nothing).
- **Format.** CityGML 2.0 per map sheet in `Modele_3D/<TERYT>_<sheet>.gml`, a `bldg:Building` with `bldg:roofType`,
  `bldg:lod2Solid` and `GroundSurface` / `WallSurface` / `RoofSurface` thematic surfaces (BDOT10k `buildingId` as a
  `gen:stringAttribute`). No `measuredHeight`: the height is the roof's top minus the ground.
- **Coordinates.** `srsName="urn:ogc:def:crs,crs:EPSG::2180,crs:PL-KRON86-NH"`, `<gml:pos>` is E N Z (easting first).
  The tool's `EPSG` regex reads 2180 from it, and for 2180 the positions go through `server/pl1992.py` (the project's
  Polish coordinates, `dnp` maths), never pyproj; the other countries still use pyproj.
- **Heights.** The Z is PL-KRON86-NH (the Kronsztadt 86 normal heights). The pipeline only uses differences (roof top
  minus ground, roof top minus the eaves), so no datum conversion is needed.
- **roofType.** The codes are the CityGML / SIG3D codelist, not the AdV one of the German states, so for Poland (and only
  there: `ROOF_CODES["PL"]`, threaded through `parse` / `row` as `source`) they are mapped:

  | GUGiK | roof | AdV | | GUGiK | roof | AdV |
  |---|---|---|---|---|---|---|
  | 1000 | flat | 1000 | | 1080 | cone (Kegeldach) | 3600 |
  | 1010 | skillion | 2100 | | 1090 | dome | 3700 |
  | 1020 | offset skillion | 2200 | | 1100 | shed | 3800 |
  | 1030 | gabled | 3100 | | 1110 | round | 3900 |
  | 1040 | hipped | 3200 | | 1120 | tower | 4000 |
  | 1050 | half-hipped | 3300 | | 1130 | mixed | 5000 |
  | 1060 | mansard | 3400 | | 1140 | other | 9999 |
  | 1070 | pyramidal | 3500 | | | | |

  A code outside the list counts as no roofType.
- **Mixed and other roofs are read from the faces.** Over half of the buildings (61 % in the Opole sample: 11,746 of
  19,336) are "1130 mixed". For those (and 1140) `tools/lod2_classify.classify_rise` reads the shape from the roof
  faces, as the tool does for models without a roofType; the code stays 5000 only where the classifier finds nothing (or
  itself says mixed). Opole sample, the 11,746 mixed roofs: gabled 6,002 (51 %), hipped 1,549, flat 823, skillion 668,
  half-hipped 537, pyramidal 82, round 51, mansard 48, dome 3, **left mixed 1,983 (17 %)**.
- **Parts.** A building with `BuildingPart`s gives a record per part (`part` column); the server joins the tallest
  record standing in a footprint, as it does elsewhere.

### Build of three powiats (2026-11-20)

| powiat | buildings |
|---|---|
| 1661 Opole | 19,336 |
| 1261 Kraków | 82,881 |
| 1465 Warszawa | 139,279 |

241,496 rows, 241,493 records after the tile-border duplicates, in 10 shards of z10: 1.8 MB, **7.5 bytes a record**
(the ridge byte is included). Final roof codes of all three: flat 52,214, skillion 14,006, gabled 111,730, hipped
26,905, half-hipped 6,749, mansard 634, pyramidal 2,076, dome 81, round 578, mixed 26,523 (11 %). 174,687 records have a
ridge (92 % of the pitched ones). Spot checks: the Palace of Culture and Science in Warsaw is one flat record of 232 m
(spire included), its low wing 66.9 m; a gabled 19.3 m building stands 4 m from the Kraków Rynek point (the square itself is open: one record within 60 m);
the Wawel hill gives a 68 m mixed record, a 33.6 m gabled and a 21 m pyramidal one (not looked at in the game).

## How it joins the map

`lod2roofs.Records.fill` is the same as for the other countries: a record fills the roof shape, roof height and height
the map leaves empty. What differs for Poland:

- **Height.** For a record of the Polish source standing in a **LOD1 building** (`src_dataset == "GUGiK LOD1 2024"`,
  `polandlod1.DATASET`, which `buildings.tile_buildings` now hands to `fill` in the building's attributes) the LoD2 height
  **replaces** the LOD1 height (the product owner's decision: the roof's own measured top wins over the 2024 LOD1
  height). For any other building (Overture, OSM) the map's own height stays, as for every country. Where no record
  stands in a footprint, LOD1's height is the building's.
- **Ridge direction.** The shards now carry an optional `ridge` byte for every source built from now on: the azimuth of
  the roof's longest level top edge, 0..179 degrees clockwise from **true** north (255: none; flat roofs have none).
  The CityGML gives grid azimuths, so the tool turns them to true north with a second point 10 m along the ridge
  transformed through the CRS (for EPSG:2180 that is the meridian convergence, about (lon - 19) * sin(lat): up to 2.5
  degrees at the eastern border; it is also right for every other CRS). Shards published without the field decode as
  before (`ridge` is NaN). Where a building has no `roof_direction` and the record has a ridge and a gabled, hipped,
  half-hipped, mansard or round roof, `roof_direction = (ridge + 90) % 360`: `buildings.ridge_frame` reads it as the
  compass direction a slope faces, and the ridge runs across that. **Not** for a skillion: there the direction also picks
  the high side and a ridge does not say which one it is (the record would have to carry the side), so the plan keeps its
  own; not for pyramids, which have no ridge to follow.
- **Per folder retry.** `Source.down_at` is now per folder: a `lod2-pl` folder that is not on the site (not published yet,
  or down) waits its `RETRY_S` alone and no longer stops the German, Swiss, Estonian and Viennese roofs.
- **Credit.** `roof:lod2-pl`, "Roofs: GUGiK (Źródło: GUGiK ... LoD2 3D building models 2017, CC BY 4.0)", in `credits.py`,
  `CREDITS.md` and `SOURCES.md`.

## Limits

- Łódź and the other six voivodeships have no LoD2 (see Coverage); newer buildings have no record.
- Only parametric roofs: the record is a shape, a roof height and a direction, drawn by the project's own roof builder.
  The LoD2 mesh itself (dormers, chimneys, the exact eaves) is not used.
- A record joins by the point it stands at (inside the footprint, LOD1 or the map's), not by an id: a LoD2 building whose
  point falls outside the mapped footprint (a different outline, a split building) joins nothing or its neighbour.
- A tiny `1130` mixed roof may be misread (the classifier is the German states' one, 17 % stay mixed): the height is still
  right.

## Questions for maalos

1. Could the LOD1 `.bld` files carry the BDOT10k `buildingId` (the LoD2 models have it as `gen:stringAttribute buildingId`; the LOD1
   models are BDOT10k buildings too, so the id should exist there)? Then LoD2 could be joined by id instead of by point-in-footprint, which would be exact.
2. Would you want roof shape and ridge in a future GBLD / `.bld` version (the pipeline gives a 1-byte AdV code, a roof
   height and a 1-byte ridge azimuth per building), or do you prefer they stay separate shards (`lod2-pl`, read by
   `server/lod2roofs.py`)?
3. Hosting: should the shards live in your repository (next to the `.bld` files, one pinned commit like LOD1) or in the
   BeamNG.Earth-data site (`lod2-pl/` beside the German folders: 1.8 MB for three powiats at 7.5 bytes a record; the ten
   voivodeships will be tens of MB)?
4. Licence wording: Geoportal's information panel for the models says "Licencja CC BY 4.0", GUGiK's site says free for any
   use (art. 40a ust. 2 pkt 1 of the Prawo geodezyjne i kartograficzne). Which should the attribution and the repository's
   LICENSE rely on? Currently "Źródło: GUGiK" with both named.

## Files

- `tools/build_lod2_roofs.py`: source `PL` (`pl_jobs`, `PL_ROOF`, `ROOF_CODES`, `READ_FACES`, `lonlat` / `true_azimuth`,
  `NO_RIDGE`, the `ridge` field of `RECORD`).
- `server/lod2roofs.py`: `PL_ON` / `SOURCES`, `decode` (ridge), `Records.fill` (`_replaces`, `RIDGED`), per-folder `down_at`.
- `server/buildings.py`: `src_dataset` in the attributes handed to `Records.fill`.
- `server/tests/test_pl_lod2.py` (the tool: codes, faces, EPSG, pl1992, ridge, round trip) and `server/tests/test_lod2roofs.py`
  (the switch, heights, direction, old shards, folders).
