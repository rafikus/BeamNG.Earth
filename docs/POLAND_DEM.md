# Polish terrain (GUGiK NMT): already in, through Mapterhorn

**Result (2026-11-20): no Polish elevation source is added.** Mapterhorn, the project's detailed elevation
(`server/dem.py`), is built for Poland from GUGiK's own terrain model, and its tiles match GUGiK's heights to the
service's 0.1 m rounding in the places checked. A `BNE_PL_DEM` source (GUGiK's WCS) would serve the same heights with
more requests to GUGiK and more code.

## What Mapterhorn holds for Poland

From `https://download.mapterhorn.com/attribution.json` (read 2026-11-20):

| source | name | resolution | producer | licence | accessed |
|---|---|---|---|---|---|
| `pl1` | Numeryczny Model Terenu 1 m | 1.0 m | GUGiK, PZGiK | Open Government Data (Art. 40a geod. i kartogr.) | 2025 |
| `pl5` | Numeryczny Model Terenu 5 m | 5.0 m | GUGiK, PZGiK | as above | 2025 |

Its coverage list (`download_urls.json`, the one `dem.coverage_index` reads) has detailed archives over every z6 tile
of Poland: `6-34-20` (to z17), `6-35-20`, `6-35-21`, `6-35-22`, `6-36-20`, `6-36-21`, `6-36-22` (to z16). The server
reads z16 near the player (`dem.FINE_ZOOM`): 512-pixel tiles, about 0.74 m a pixel at Łódź, finer than the terrain's
2 m lattice.

## The check (Łódź)

Eight points, GUGiK's point service (`https://services.gugik.gov.pl/nmt/?request=GetHbyXY&x=<northing>&y=<easting>`,
EPSG:2180 from `server/pl1992.py`, heights PL-EVRF2007-NH, 0.1 m) against Mapterhorn's z16 Terrarium tile
(`tiles.mapterhorn.com`, bilinear between pixel centres):

| place | lat, lon | GUGiK (m) | Mapterhorn z16 (m) | difference |
|---|---|---|---|---|
| pl. Wolności | 51.77695, 19.45468 | 210.30 | 210.29 | -0.01 |
| Politechnika, Żeromskiego | 51.75330, 19.45200 | 198.90 | 198.85 | -0.05 |
| Manufaktura | 51.78010, 19.44740 | 202.20 | 202.25 | +0.05 |
| Łagiewniki (forest) | 51.83480, 19.47180 | 226.00 | 225.90 | -0.10 |
| Retkinia | 51.74900, 19.39600 | 191.60 | 191.50 | -0.10 |
| Widzew Wschód | 51.75900, 19.52800 | 238.40 | 238.28 | -0.12 |
| Rudzka Góra (slope) | 51.70950, 19.44300 | 207.80 | 207.66 | -0.14 |
| Ner valley | 51.70400, 19.33200 | 193.00 | 193.04 | +0.04 |

Mean -0.05 m, largest 0.14 m: the same model. No vertical offset either: Mapterhorn keeps GUGiK's heights as they are
(PL-EVRF2007's quasi-geoid and EGM2008 differ by centimetres to a few decimetres over Poland, below what the terrain
shows).

## Limits

- Eight points in one city, not a survey of the country.
- Mapterhorn took GUGiK's NMT in 2025: sheets GUGiK updates later reach the game only when Mapterhorn rebuilds.
- Mapterhorn has the terrain model only (NMT), not the surface model (NMPT). Tree heights from NMPT minus NMT
  (planned) still need GUGiK's own data.

## Credit

GUGiK's terms ask for the source to be named. Mapterhorn names its sources at mapterhorn.com/attribution, which the
project's Mapterhorn credit already points to; `CREDITS.md` now also names GUGiK's NMT as the Polish part of it.
