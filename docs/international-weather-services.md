# International Weather Service Equivalents

Research notes on national weather services outside the US, and how usable each
one is for nalssi. Every endpoint below was probed live on **2026-08-18**;
figures are what the services actually returned, not what their docs claim.

The practical question is not "does this country have a weather agency" — they
all do — but "can we pull radar imagery from it the way we pull from NOAA?"
The answer varies enormously.

## Summary

| Country/Region | Service | Radar access | API key | Status in nalssi |
|---|---|---|---|---|
| United States | NWS / NCEP (MRMS) | OGC WMS, time-enabled | No | **Implemented** |
| Canada | ECCC / MSC GeoMet | OGC WMS, time-enabled | No | **Implemented** |
| Germany | DWD | OGC WMS, time-enabled | No | Viable, not built |
| Japan | JMA | XYZ tiles | No | Viable, more work |
| Korea | KMA | REST image API | **Yes** (free) | Blocked on key |
| Netherlands | KNMI | WMS via ADAGUC | **Yes** (free) | Not investigated deeply |
| UK | Met Office | DataHub | **Yes** | Not investigated deeply |
| France | Météo-France | Open data portal | **Yes** | Not investigated deeply |
| Europe (pan) | EUMETNET OPERA | Restricted / commercial | n/a | Not viable |

## Forecasts vs. radar

These are in very different states, and it's worth keeping them separate.

**Forecasts are largely already solved.** nalssi has an Open-Meteo client, and
Open-Meteo proxies the national models — DWD, KMA, JMA, KNMI, Météo-France,
ECCC. A Canadian or Korean location already gets usable forecast data today
without any new integration.

**Radar imagery is the real gap**, because it is served per-country with no
common aggregator.

## Canada — ECCC / MSC GeoMet (implemented)

`https://geo.weather.gc.ca/geomet`

The closest thing to a drop-in equivalent of the NWS GeoServer. OGC WMS 1.3.0,
no API key, open licence.

- Layers: `RADAR_1KM_RRAI` (rain), `RADAR_1KM_RSNO` (snow), plus URP precip
  products
- **3-hour rolling window at 6-minute steps** (31 frames observed) — more
  history than the NWS mosaic's 1h58m
- Companion `https://api.weather.gc.ca` (OGC API Features) covers observations
  and alerts, paralleling `api.weather.gov`

Two differences from the NWS server had to be handled in code:

1. **Time dimension format.** The NWS advertises an explicit comma-separated
   list of timestamps. GeoMet advertises an ISO interval,
   `2026-08-18T17:06:00Z/2026-08-18T20:06:00Z/PT6M`, which must be expanded.
2. **Time parameter format.** GeoMet returns a `ServiceExceptionReport` for the
   fractional seconds the NWS server requires. `2026-08-18T20:00:00Z` works;
   `2026-08-18T20:00:00.000Z` does not.

GeoMet carries **no boundary layers** — it is purely weather data (37,918
layers). The basemap therefore comes from elsewhere: boundaries from the NWS
GeoServer (which publishes `nws:ca_provinces` alongside its US layers) and
shaded water from the USGS cached hydrography basemap, which despite its name
renders the Great Lakes and Canadian shorelines well.

### Basemap styling is server-limited

Neither GeoServer will accept custom styling — `SLD_BODY` returns *"Dynamic
style usage is forbidden"* — and `nws:us_counties` publishes only two named
styles, both plain line styles. Neither server has a water layer at all.

That is why the basemap is fetched as **separate bands** (water, counties,
admin) and coloured client-side with CSS masks, rather than composited into one
styled image server-side.

### Known limitation: sparse Canadian basemaps

Canada has no county-level equivalent in the NWS boundary layers, so inland
Canadian views are thin — a Winnipeg basemap is nearly blank apart from the US
border. Coastal and Great Lakes locations (Toronto, Vancouver, Halifax) fare
much better because shorelines carry the detail.

Where the basemap is sparse, the range rings and center marker carry most of
the spatial reference. Improving this would mean sourcing Canadian census
division boundaries from somewhere outside the two GeoServers we currently use.

## Germany — DWD (viable, not built)

`https://maps.dwd.de/geoserver/ows`

A GeoServer WMS, no key required — architecturally identical to what we already
support.

- `dwd:RADOLAN-RY` — **24-hour window at 5-minute steps**, far more history
  than either North American source
- Also `dwd:RADOLAN-RW` (hourly totals, 10-minute steps) and several composites
- Raw files additionally at `https://opendata.dwd.de/weather/radar/`

Uses the same ISO interval time dimension as GeoMet, so the parser added for
Canada already handles it. Adding Germany would be mostly a new `RadarSource`
entry plus a basemap source for European boundaries.

## Japan — JMA (viable, more work)

No API key, but a different delivery model: **XYZ tiles, not WMS.**

- Frame list: `https://www.jma.go.jp/bosai/jmatile/data/nowc/targetTimes_N1.json`
  → `basetime` / `validtime` pairs
- Tiles: `.../nowc/{basetime}/none/{validtime}/surf/hrpns/{z}/{x}/{y}.png`
- **3-hour window at 5-minute steps** (37 frames observed)
- Forecast JSON at `https://www.jma.go.jp/bosai/forecast/data/forecast/{area}.json`

Because tiles are addressed by z/x/y rather than an arbitrary bbox, this would
not reuse the existing `bbox_for` path — frames would have to be stitched from
several tiles. Meaningfully more work than Canada or Germany.

The `bosai` JSON endpoints are public and widely used but not formally
documented as a public API, so they carry some stability risk.

## Korea — KMA (blocked on a key)

`https://apihub.kma.go.kr`

Real and reachable, but key-gated: the radar composite endpoint
`/api/typ01/url/rdr_cmp_img.php` returns **401** without credentials.
Registration is free; the portal is largely Korean-language.

There is also a separate National Meteorological Satellite Center open API
(`datasvc.nmsc.kma.go.kr`) for satellite imagery, which requires a separate
application by email.

## Europe more broadly

There is no EU-wide NOAA. **EUMETNET OPERA** produces the pan-European radar
composite, but access is restricted/commercial, so it is not an option here.

In practice it is per-country, and openness varies sharply. DWD is the standout
for being fully open; KNMI, the Met Office, and Météo-France all require free
registration. KNMI serves WMS through ADAGUC (`adaguc.knmi.nl`) and its data
platform returned 401 unauthenticated, as expected.

**MeteoAlarm** (`meteoalarm.org`) aggregates *warnings* across ~38 European
countries and is the closest thing to a continental equivalent on the alerting
side — relevant if alert coverage is ever extended beyond NOAA.

## Adding another source

The radar layer is built around a `RadarSource` (see
`app/services/imagery/radar.py`), so a new country is mostly a data change:

1. Add a `RadarSource` to `SOURCES` with its WMS URL, layer name, geographic
   bounds, country code, and time format.
2. Order matters only where coverage overlaps — `source_for()` prefers a source
   whose `country` matches the location's `country_code`, falling back to the
   first geographic match.
3. If the service advertises times in a form neither handled today (explicit
   list or ISO interval), extend `RadarClient._parse_time_dimension`.

The bbox math, storage, retention, pruning, and viewer are all source-agnostic
and need no changes.
