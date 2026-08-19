"""
Radar imagery client for national weather service WMS endpoints.

Frames come from whichever national service covers a location: the NWS MRMS
mosaic in the US (opengeo.ncep.noaa.gov) and MSC GeoMet in Canada
(geo.weather.gc.ca). Both are OGC WMS with a rolling time dimension, so an
arbitrary past timestamp can be requested directly rather than accumulated over
time. They differ in how that dimension is advertised and in the time format
they accept, which is why each source carries its own settings.

Documentation:
  US:     https://opengeo.ncep.noaa.gov/geoserver/www/index.html
  Canada: https://eccc-msc.github.io/open-data/msc-data/obs_radar/readme_radar_geomet_en/
"""

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()


@dataclass(frozen=True)
class BasemapLayer:
    """
    One styled band of the basemap, fetched and stored separately.

    Splitting the basemap into bands is what makes water and the different
    administrative levels distinguishable: the servers used here publish only
    line styles and reject custom SLD ("Dynamic style usage is forbidden"), so
    the visual hierarchy is applied client-side per band instead.

    Attributes:
        kind: Short identifier, used in the stored filename and served URL
        url: WMS endpoint
        layers: Comma-separated layer names for this band
        extra_params: Additional query parameters the endpoint requires
    """

    kind: str
    url: str
    layers: str
    extra_params: tuple[tuple[str, str], ...] = ()

    def fingerprint(self) -> str:
        """A stable string identifying everything that determines this image."""
        extras = ",".join(f"{k}={v}" for k, v in self.extra_params)
        return f"{self.kind}|{self.url}|{self.layers}|{extras}"


def _basemap_layers() -> tuple[BasemapLayer, ...]:
    """
    Build the basemap bands, bottom to top.

    Water comes from the USGS cached hydrography basemap, which is public
    domain and — despite the name — renders the Great Lakes and Canadian
    shorelines too, so it serves both supported countries. Boundaries come from
    the NWS GeoServer, which carries Canadian provinces alongside US counties
    and states.

    Note the boundaries give thin context inland in Canada: provinces are large
    polygons with no county-level subdivision, so there the water, range rings
    and center marker carry most of the spatial reference.
    """
    bands = []
    if settings.RADAR_HYDRO_WMS_URL:
        bands.append(
            BasemapLayer(
                kind="water",
                url=settings.RADAR_HYDRO_WMS_URL,
                layers="0",
                # This service rejects the request outright without `styles`.
                extra_params=(("styles", ""),),
            )
        )
    bands.append(
        BasemapLayer(
            kind="counties",
            url=settings.RADAR_WMS_BASE_URL,
            layers="nws:us_counties",
        )
    )
    bands.append(
        BasemapLayer(
            kind="admin",
            url=settings.RADAR_WMS_BASE_URL,
            layers="nws:state_boundary,nws:ca_provinces",
        )
    )
    return tuple(bands)


BASEMAP_LAYERS: tuple[BasemapLayer, ...] = _basemap_layers()

# Web Mercator (EPSG:3857) is used rather than EPSG:4326 so that pixels are
# square. A degree-based bounding box renders visibly stretched at mid-latitudes
# because a degree of longitude is much shorter than a degree of latitude.
CRS = "EPSG:3857"

# Web Mercator is defined on a sphere of this radius.
_EARTH_RADIUS_M = 6378137.0

# Bounding box in projected metres: (min_x, min_y, max_x, max_y)
BBox = tuple[float, float, float, float]

# Guard against an absurdly long advertised interval expanding without bound.
_MAX_EXPANDED_FRAMES = 2000


@dataclass(frozen=True)
class RadarSource:
    """
    A national radar service and the region it covers.

    Attributes:
        name: Short identifier used in logs and storage
        country: ISO country code, used to prefer a location's own national
            service where coverage areas overlap across a border
        provider: Human-readable attribution shown in the UI
        wms_url: Endpoint for GetMap and GetFeatureInfo
        layer: Fully qualified reflectivity layer name
        capabilities_url: Endpoint for GetCapabilities, which is often a
            layer-scoped path so the document stays small
        capabilities_layer_param: Whether to scope GetCapabilities with a
            LAYERS query parameter instead of a layer-specific path
        time_format: strftime pattern for the WMS time parameter. GeoMet
            rejects the fractional seconds that the NWS server requires, so
            this cannot be shared.
    """

    name: str
    country: str
    provider: str
    wms_url: str
    layer: str
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    capabilities_url: str
    capabilities_layer_param: bool = False
    time_format: str = "%Y-%m-%dT%H:%M:%S.000Z"

    def covers(self, latitude: float, longitude: float) -> bool:
        """Check whether a coordinate falls in this source's area."""
        return (
            self.min_lat <= latitude <= self.max_lat
            and self.min_lon <= longitude <= self.max_lon
        )

    def format_time(self, value: datetime) -> str:
        """Format a timestamp for this source's WMS time parameter."""
        return value.astimezone(UTC).strftime(self.time_format)


def _nws_source(
    name: str, min_lat: float, max_lat: float, min_lon: float, max_lon: float
) -> RadarSource:
    """Build a source for one of the NWS regional mosaics."""
    root = settings.RADAR_WMS_BASE_URL.rstrip("/")
    if root.endswith("/ows"):
        root = root[: -len("/ows")]
    return RadarSource(
        name=name,
        country="US",
        provider="NWS / MRMS",
        wms_url=settings.RADAR_WMS_BASE_URL,
        layer=f"{name}:{name}_bref_qcd",
        min_lat=min_lat,
        max_lat=max_lat,
        min_lon=min_lon,
        max_lon=max_lon,
        # The per-layer endpoint returns a few KB; the server-wide one returns
        # megabytes covering every radar site.
        capabilities_url=f"{root}/{name}/{name}_bref_qcd/ows",
    )


# Ordered US-first so that a location whose country is unknown keeps the
# behaviour it had before Canadian coverage existed.
SOURCES: list[RadarSource] = [
    _nws_source("conus", 20.0, 55.0, -130.0, -60.0),
    _nws_source("alaska", 50.0, 72.0, -180.0, -128.0),
    _nws_source("hawaii", 15.0, 25.0, -165.0, -150.0),
    _nws_source("carib", 15.0, 22.0, -70.0, -63.0),
    _nws_source("guam", 11.0, 17.0, 141.0, 149.0),
    RadarSource(
        name="canada",
        country="CA",
        provider="ECCC / MSC GeoMet",
        wms_url=settings.RADAR_GEOMET_URL,
        layer="RADAR_1KM_RRAI",
        min_lat=41.0,
        max_lat=75.0,
        min_lon=-142.0,
        max_lon=-52.0,
        capabilities_url=settings.RADAR_GEOMET_URL,
        capabilities_layer_param=True,
        # GeoMet returns a service exception for fractional seconds.
        time_format="%Y-%m-%dT%H:%M:%SZ",
    ),
]


def source_for(
    latitude: float, longitude: float, country_code: str | None = None
) -> RadarSource | None:
    """
    Find the radar service covering a coordinate.

    Coverage areas overlap across the Canada/US border — the US mosaic extends
    well into southern Canada — so where several match, a location's own
    national service wins. Without a country code the first match applies,
    which keeps US locations on the NWS mosaic as before.

    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        country_code: Optional ISO country code from the location

    Returns:
        The RadarSource, or None if outside every covered area.
    """
    candidates = [s for s in SOURCES if s.covers(latitude, longitude)]
    if not candidates:
        return None

    if country_code:
        wanted = country_code.upper()
        for source in candidates:
            if source.country == wanted:
                return source

    return candidates[0]


def _to_web_mercator(latitude: float, longitude: float) -> tuple[float, float]:
    """Project a lat/lon coordinate to EPSG:3857 metres."""
    x = math.radians(longitude) * _EARTH_RADIUS_M
    y = math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2)) * _EARTH_RADIUS_M
    return x, y


def bbox_for(latitude: float, longitude: float, span_km: float) -> BBox:
    """
    Build a square EPSG:3857 bounding box centered on a coordinate.

    Web Mercator distances are inflated by 1/cos(latitude), so the requested
    ground span is scaled accordingly to keep the view the intended real-world
    size regardless of latitude.

    Args:
        latitude: Center latitude
        longitude: Center longitude
        span_km: Desired width/height of the view in kilometres

    Returns:
        (min_x, min_y, max_x, max_y) in EPSG:3857 metres
    """
    center_x, center_y = _to_web_mercator(latitude, longitude)
    half = (span_km * 1000.0) / 2.0 / math.cos(math.radians(latitude))
    return (center_x - half, center_y - half, center_x + half, center_y + half)


def bbox_param(bbox: BBox) -> str:
    """Format a bounding box for a WMS bbox parameter."""
    return ",".join(f"{v:.3f}" for v in bbox)


class RadarClient:
    """
    Client for national radar WMS services.

    No API key required for any configured source; all serve public domain or
    open-licensed government data.
    """

    def __init__(self):
        """Initialize the radar client."""
        self.timeout = httpx.Timeout(60.0, connect=10.0)

    def _get_headers(self) -> dict:
        """Get HTTP headers identifying this application to the provider."""
        return {
            "User-Agent": (
                f"{settings.APP_NAME}/{settings.APP_VERSION} "
                "(Weather Data Collection Service)"
            ),
        }

    async def available_times(self, source: RadarSource) -> list[datetime]:
        """
        List the frame timestamps a source currently offers.

        Args:
            source: Radar source to query

        Returns:
            Sorted list of UTC datetimes, oldest first. Empty if the server
            advertises no time dimension.
        """
        params = {
            "service": "WMS",
            "version": "1.3.0",
            "request": "GetCapabilities",
        }
        if source.capabilities_layer_param:
            # GeoMet scopes its 38k-layer document with a LAYERS parameter.
            params["LAYERS"] = source.layer

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                source.capabilities_url, params=params, headers=self._get_headers()
            )
            response.raise_for_status()
            return self._parse_time_dimension(response.text, source.layer)

    @staticmethod
    def _parse_duration(value: str) -> timedelta | None:
        """
        Parse an ISO 8601 duration of the forms this context produces.

        Handles the day/hour/minute/second components that radar services use
        for frame cadence (PT5M, PT6M, PT10M, P1D). Returns None for anything
        unrecognised or zero-length.
        """
        match = re.fullmatch(
            r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?",
            value.strip(),
        )
        if not match:
            return None
        days, hours, minutes, seconds = (int(g or 0) for g in match.groups())
        delta = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        return delta or None

    @classmethod
    def _parse_time_dimension(cls, xml: str, layer: str) -> list[datetime]:
        """
        Parse the time dimension out of a WMS capabilities document.

        Services advertise this in two forms, both of which appear among the
        sources here: an explicit comma-separated list of timestamps (NWS), or
        ISO 8601 ``start/end/period`` intervals that must be expanded (GeoMet,
        and European services such as DWD). Both may be mixed in one value.

        Args:
            xml: Raw capabilities XML
            layer: Qualified layer name (used only for logging context)

        Returns:
            Sorted list of UTC datetimes, oldest first.
        """
        match = re.search(
            r'<Dimension[^>]*name="time"[^>]*>(.*?)</Dimension>',
            xml,
            re.DOTALL,
        )
        if not match:
            logger.warning("No time dimension advertised for radar layer %s", layer)
            return []

        times: list[datetime] = []
        for raw in match.group(1).split(","):
            value = raw.strip()
            if not value:
                continue
            if "/" in value:
                times.extend(cls._expand_interval(value, layer))
            else:
                parsed = cls._parse_timestamp(value, layer)
                if parsed:
                    times.append(parsed)

        return sorted(set(times))

    @classmethod
    def _expand_interval(cls, value: str, layer: str) -> list[datetime]:
        """Expand an ISO ``start/end/period`` interval into timestamps."""
        parts = value.split("/")
        if len(parts) != 3:
            logger.warning("Unparseable radar time interval: %r", value)
            return []

        start = cls._parse_timestamp(parts[0], layer)
        end = cls._parse_timestamp(parts[1], layer)
        step = cls._parse_duration(parts[2])
        if start is None or end is None or step is None or end < start:
            logger.warning("Unparseable radar time interval: %r", value)
            return []

        times: list[datetime] = []
        current = start
        while current <= end and len(times) < _MAX_EXPANDED_FRAMES:
            times.append(current)
            current += step

        if len(times) >= _MAX_EXPANDED_FRAMES:
            logger.warning(
                "Radar time interval for %s exceeded %d frames, truncating",
                layer,
                _MAX_EXPANDED_FRAMES,
            )

        return times

    @staticmethod
    def _parse_timestamp(value: str, layer: str) -> datetime | None:
        """Parse a single ISO timestamp to UTC, or None if malformed."""
        try:
            return datetime.fromisoformat(
                value.strip().replace("Z", "+00:00")
            ).astimezone(UTC)
        except ValueError:
            logger.warning("Unparseable radar frame timestamp for %s: %r", layer, value)
            return None

    async def fetch_frame(
        self, source: RadarSource, bbox: BBox, frame_time: datetime
    ) -> bytes:
        """
        Fetch a single radar reflectivity frame as a transparent PNG.

        Only the radar layer is drawn; the basemap is fetched separately and
        stored once per location since it never changes.

        Args:
            source: Radar source to fetch from
            bbox: EPSG:3857 bounding box
            frame_time: Timestamp to request (server snaps to the nearest frame)

        Returns:
            PNG image bytes
        """
        params = self._map_params(source.layer, bbox)
        params["time"] = source.format_time(frame_time)
        return await self._get_map(source.wms_url, params)

    async def fetch_basemap_layer(self, layer: BasemapLayer, bbox: BBox) -> bytes:
        """
        Fetch one band of the basemap for a bounding box.

        Args:
            layer: Basemap band to fetch
            bbox: EPSG:3857 bounding box

        Returns:
            PNG image bytes
        """
        params = self._map_params(layer.layers, bbox)
        params.update(layer.extra_params)
        return await self._get_map(layer.url, params)

    async def precip_at(
        self, latitude: float, longitude: float, source: RadarSource
    ) -> bool:
        """
        Check whether precipitation is currently falling at a coordinate.

        Queries the rendered radar pixel covering the point and reports whether
        it is painted at all. Only the alpha channel is used: these services
        render a mosaic rather than exposing a data raster, so no numeric
        reflectivity is available. Alpha alone needs no assumptions about how a
        provider styles its layer and cannot drift if that styling changes.

        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            source: Radar source covering the coordinate

        Returns:
            True if the radar shows a return at this point.

        Raises:
            Exception: If the request fails or returns an unexpected payload.
        """
        # A small box queried at its center pixel. WMS 1.3.0 with EPSG:4326
        # takes bbox coordinates in lat,lon order.
        delta = 0.02
        params = {
            "service": "WMS",
            "version": "1.3.0",
            "request": "GetFeatureInfo",
            "layers": source.layer,
            "query_layers": source.layer,
            "crs": "EPSG:4326",
            "bbox": (
                f"{latitude - delta},{longitude - delta},"
                f"{latitude + delta},{longitude + delta}"
            ),
            "width": "21",
            "height": "21",
            "i": "10",
            "j": "10",
            "info_format": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                source.wms_url, params=params, headers=self._get_headers()
            )
            response.raise_for_status()
            payload = response.json()

        features = payload.get("features") or []
        if not features:
            # No feature at all means nothing is painted here.
            return False

        properties = features[0].get("properties", {})
        # Providers name the alpha band differently; any non-zero alpha counts.
        for key in ("ALPHA_BAND", "alpha_band", "BAND_4", "band_4"):
            if key in properties:
                return bool(properties[key])
        return False

    def _map_params(self, layers: str, bbox: BBox) -> dict:
        """Build the common GetMap query parameters."""
        size = settings.RADAR_IMAGE_SIZE
        return {
            "service": "WMS",
            "version": "1.3.0",
            "request": "GetMap",
            "layers": layers,
            "crs": CRS,
            "bbox": bbox_param(bbox),
            "width": str(size),
            "height": str(size),
            "format": "image/png",
            "transparent": "true",
        }

    async def _get_map(self, url: str, params: dict) -> bytes:
        """
        Issue a WMS GetMap request and return the image bytes.

        WMS servers signal failure with a 200 response carrying an XML service
        exception, so the content type is checked rather than the status alone.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=params, headers=self._get_headers())
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "image" not in content_type:
                raise RuntimeError(
                    f"WMS returned {content_type or 'unknown content type'} "
                    f"instead of an image: {response.text[:300]}"
                )

            return response.content


_client: RadarClient | None = None


def get_radar_client() -> RadarClient:
    """
    Get or create the global radar client instance.

    Returns:
        RadarClient instance
    """
    global _client
    if _client is None:
        _client = RadarClient()
    return _client
