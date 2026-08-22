"""
Tests for the NWS radar WMS client.
"""

import math
from datetime import UTC, datetime

import httpx
import pytest

from app.services.imagery.radar import (
    RadarClient,
    RadarSource,
    bbox_for,
    bbox_param,
    source_for,
)

CAPABILITIES = """<?xml version="1.0"?>
<WMS_Capabilities>
  <Layer queryable="1">
    <Name>conus_bref_qcd</Name>
    <Dimension name="time" default="current" units="ISO8601">
      2026-08-17T15:50:17.000Z,2026-08-17T15:52:14.000Z,2026-08-17T15:54:00.000Z
    </Dimension>
  </Layer>
</WMS_Capabilities>
"""

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture
def client():
    return RadarClient()


@pytest.fixture
def us_source():
    """A source shaped like the NWS GeoServer: layer-scoped caps, millis time."""
    return RadarSource(
        name="conus",
        country="US",
        provider="Test NWS",
        wms_url="https://geo.example.test/geoserver/ows",
        layer="conus:conus_bref_qcd",
        min_lat=20.0,
        max_lat=55.0,
        min_lon=-130.0,
        max_lon=-60.0,
        capabilities_url=(
            "https://geo.example.test/geoserver/conus/conus_bref_qcd/ows"
        ),
    )


@pytest.fixture
def ca_source():
    """A source shaped like MSC GeoMet: LAYERS-scoped caps, no fractional secs."""
    return RadarSource(
        name="canada",
        country="CA",
        provider="Test GeoMet",
        wms_url="https://geomet.example.test/geomet",
        layer="RADAR_1KM_RRAI",
        min_lat=41.0,
        max_lat=75.0,
        min_lon=-142.0,
        max_lon=-52.0,
        capabilities_url="https://geomet.example.test/geomet",
        capabilities_layer_param=True,
        time_format="%Y-%m-%dT%H:%M:%SZ",
    )


class TestSourceFor:
    def test_conus_location(self):
        assert source_for(44.98, -93.27).name == "conus"

    def test_alaska_location(self):
        assert source_for(61.2, -149.9).name == "alaska"

    def test_hawaii_location(self):
        assert source_for(21.3, -157.8).name == "hawaii"

    def test_location_outside_coverage_returns_none(self):
        # London has no NWS radar coverage
        assert source_for(51.5, -0.12) is None

    def test_southern_hemisphere_returns_none(self):
        assert source_for(-33.87, 151.21) is None


class TestBboxFor:
    def test_bbox_is_square(self):
        min_x, min_y, max_x, max_y = bbox_for(44.98, -93.27, 240.0)
        assert (max_x - min_x) == pytest.approx(max_y - min_y)

    def test_bbox_is_centered_on_the_location(self):
        min_x, min_y, max_x, max_y = bbox_for(44.98, -93.27, 240.0)
        center_x = math.radians(-93.27) * 6378137.0
        assert (min_x + max_x) / 2 == pytest.approx(center_x, rel=1e-9)

    def test_span_is_corrected_for_latitude(self):
        # Web Mercator inflates distances by 1/cos(lat), so a fixed ground span
        # must produce a wider projected box further from the equator.
        equator = bbox_for(0.0, -90.0, 240.0)
        north = bbox_for(60.0, -90.0, 240.0)
        assert (north[2] - north[0]) > (equator[2] - equator[0])

    def test_bbox_param_formats_four_values(self):
        assert len(bbox_param(bbox_for(44.98, -93.27, 240.0)).split(",")) == 4


class TestParseTimeDimension:
    def test_parses_and_sorts_timestamps(self):
        times = RadarClient._parse_time_dimension(CAPABILITIES, "conus:conus_bref_qcd")
        assert len(times) == 3
        assert times[0] == datetime(2026, 8, 17, 15, 50, 17, tzinfo=UTC)
        assert times[-1] == datetime(2026, 8, 17, 15, 54, 0, tzinfo=UTC)
        assert times == sorted(times)

    def test_missing_dimension_returns_empty(self):
        assert RadarClient._parse_time_dimension("<WMS_Capabilities/>", "x") == []

    def test_unparseable_entries_are_skipped(self):
        xml = (
            '<Dimension name="time">'
            "2026-08-17T15:50:17.000Z,not-a-date,"
            "2026-08-17T15:52:14.000Z</Dimension>"
        )
        assert len(RadarClient._parse_time_dimension(xml, "x")) == 2


class TestAvailableTimes:
    async def test_requests_the_layer_scoped_endpoint(
        self, client, us_source, respx_mock
    ):
        route = respx_mock.get(
            "https://geo.example.test/geoserver/conus/conus_bref_qcd/ows"
        ).mock(return_value=httpx.Response(200, text=CAPABILITIES))

        times = await client.available_times(us_source)

        assert route.called
        assert len(times) == 3


class TestFetchFrame:
    async def test_sends_time_parameter_and_returns_bytes(
        self, client, us_source, respx_mock
    ):
        route = respx_mock.get("https://geo.example.test/geoserver/ows").mock(
            return_value=httpx.Response(
                200, content=PNG_BYTES, headers={"content-type": "image/png"}
            )
        )

        frame_time = datetime(2026, 8, 17, 15, 50, 17, tzinfo=UTC)
        data = await client.fetch_frame(us_source, (0.0, 0.0, 1.0, 1.0), frame_time)

        assert data == PNG_BYTES
        params = route.calls[0].request.url.params
        assert params["time"] == "2026-08-17T15:50:17.000Z"
        assert params["layers"] == "conus:conus_bref_qcd"
        assert params["crs"] == "EPSG:3857"
        assert params["transparent"] == "true"

    async def test_naive_time_is_treated_as_utc(self, client, us_source, respx_mock):
        route = respx_mock.get("https://geo.example.test/geoserver/ows").mock(
            return_value=httpx.Response(
                200, content=PNG_BYTES, headers={"content-type": "image/png"}
            )
        )

        await client.fetch_frame(
            us_source,
            (0.0, 0.0, 1.0, 1.0),
            datetime(2026, 8, 17, 15, 50, 17, tzinfo=UTC),
        )
        assert route.calls[0].request.url.params["time"].endswith("Z")

    async def test_xml_service_exception_raises(self, client, us_source, respx_mock):
        # GeoServer reports failures as HTTP 200 with an XML body, so a status
        # check alone would silently store an error document as an image.
        respx_mock.get("https://geo.example.test/geoserver/ows").mock(
            return_value=httpx.Response(
                200,
                text="<ServiceExceptionReport>LayerNotDefined</ServiceExceptionReport>",
                headers={"content-type": "text/xml"},
            )
        )

        with pytest.raises(RuntimeError, match="instead of an image"):
            await client.fetch_frame(us_source, (0.0, 0.0, 1.0, 1.0), datetime.now(UTC))

    async def test_http_error_propagates(self, client, us_source, respx_mock):
        respx_mock.get("https://geo.example.test/geoserver/ows").mock(
            return_value=httpx.Response(503)
        )

        with pytest.raises(httpx.HTTPStatusError):
            await client.fetch_frame(us_source, (0.0, 0.0, 1.0, 1.0), datetime.now(UTC))


class TestPrecipAt:
    """
    Precipitation state is read from whichever shape the provider answers in.

    NOAA exposes no numeric data (the ArcGIS `identify` endpoint returns NoData
    even over confirmed echoes, and the layer's color ramp is unpublished), so
    the rendered pixel's alpha channel is the only assumption-free signal.
    GeoMet returns the precipitation rate itself and never sends an alpha band,
    which is why reading alpha alone reported every Canadian location as dry.

    The payloads below are the shapes the live services actually return.
    """

    def _response(self, properties):
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "properties": properties},
                ],
            },
        )

    async def test_noaa_opaque_pixel_means_precipitation(
        self, client, us_source, respx_mock
    ):
        respx_mock.get("https://geo.example.test/geoserver/ows").mock(
            return_value=self._response(
                {"RED_BAND": 92, "GREEN_BAND": 181, "BLUE_BAND": 198, "ALPHA_BAND": 255}
            )
        )

        assert await client.precip_at(39.5, -79.5, us_source) is True

    async def test_noaa_transparent_pixel_means_no_precipitation(
        self, client, us_source, respx_mock
    ):
        respx_mock.get("https://geo.example.test/geoserver/ows").mock(
            return_value=self._response(
                {"RED_BAND": 0, "GREEN_BAND": 0, "BLUE_BAND": 0, "ALPHA_BAND": 0}
            )
        )

        assert await client.precip_at(37.77, -122.42, us_source) is False

    async def test_empty_feature_list_means_no_precipitation(
        self, client, us_source, respx_mock
    ):
        respx_mock.get("https://geo.example.test/geoserver/ows").mock(
            return_value=httpx.Response(
                200, json={"type": "FeatureCollection", "features": []}
            )
        )

        assert await client.precip_at(37.77, -122.42, us_source) is False

    async def test_queries_the_point_with_the_right_parameters(
        self, client, us_source, respx_mock
    ):
        route = respx_mock.get("https://geo.example.test/geoserver/ows").mock(
            return_value=self._response({"ALPHA_BAND": 0})
        )

        await client.precip_at(39.5, -79.5, us_source)

        params = route.calls[0].request.url.params
        assert params["request"] == "GetFeatureInfo"
        assert params["query_layers"] == "conus:conus_bref_qcd"
        # WMS 1.3.0 with EPSG:4326 takes bbox in lat,lon order
        assert params["bbox"] == "39.48,-79.52,39.52,-79.48"
        # The queried pixel must be the center of the requested grid
        assert params["i"] == "10"
        assert params["j"] == "10"
        assert params["width"] == "21"
        assert params["height"] == "21"

    async def test_geomet_rate_means_precipitation(self, client, ca_source, respx_mock):
        """A non-zero rate is a return, even though no alpha band is present."""
        respx_mock.get("https://geomet.example.test/geomet").mock(
            return_value=self._response(
                {
                    "value": 0.42107189,
                    "class": "0.1 - 1.0 (mm/h)",
                    "title_en": "Radar precipitation rate for rain [mm/h]",
                }
            )
        )

        assert await client.precip_at(43.65, -79.38, ca_source) is True

    async def test_geomet_zero_rate_means_no_precipitation(
        self, client, ca_source, respx_mock
    ):
        respx_mock.get("https://geomet.example.test/geomet").mock(
            return_value=self._response(
                {
                    "value": 0,
                    "class": "Undetected",
                    "title_en": "Radar precipitation rate for rain [mm/h]",
                }
            )
        )

        assert await client.precip_at(43.65, -79.38, ca_source) is False

    async def test_geomet_falls_back_to_the_class_label(
        self, client, ca_source, respx_mock
    ):
        """A null rate leaves the class as the only signal."""
        respx_mock.get("https://geomet.example.test/geomet").mock(
            return_value=self._response({"value": None, "class": "1.0 - 2.5 (mm/h)"})
        )

        assert await client.precip_at(43.65, -79.38, ca_source) is True

    async def test_geomet_undetected_class_means_no_precipitation(
        self, client, ca_source, respx_mock
    ):
        respx_mock.get("https://geomet.example.test/geomet").mock(
            return_value=self._response({"value": None, "class": "Undetected"})
        )

        assert await client.precip_at(43.65, -79.38, ca_source) is False

    async def test_unrecognised_payload_raises_rather_than_reporting_dry(
        self, client, ca_source, respx_mock
    ):
        """
        Reporting False for a shape nobody parsed is what hid the GeoMet bug:
        every Canadian location read as dry indefinitely. Raising surfaces it as
        unknown instead, so backends leave the existing state alone.
        """
        respx_mock.get("https://geomet.example.test/geomet").mock(
            return_value=self._response({"GRAY_INDEX": 17.5, "unexpected": "shape"})
        )

        with pytest.raises(RuntimeError, match="Unrecognised GetFeatureInfo"):
            await client.precip_at(43.65, -79.38, ca_source)

    async def test_http_error_propagates(self, client, us_source, respx_mock):
        respx_mock.get("https://geo.example.test/geoserver/ows").mock(
            return_value=httpx.Response(500)
        )

        with pytest.raises(httpx.HTTPStatusError):
            await client.precip_at(39.5, -79.5, us_source)


class TestRangeRings:
    """
    Range rings rely on the location being the exact center of every frame,
    which holds because the bbox is computed around its coordinates.
    """

    def test_ring_radius_is_proportional_to_span(self):
        from app.api.routes.pages.radar import build_range_rings

        rings = {r["km"]: r["radius"] for r in build_range_rings(240.0)}
        # A 50 km ring across a 240 km view spans 100/240 of the width
        assert rings[50.0] == pytest.approx(100.0 * 50 / 240)
        assert rings[100.0] == pytest.approx(100.0 * 100 / 240)

    def test_rings_wider_than_half_the_span_are_dropped(self):
        from app.api.routes.pages.radar import build_range_rings

        # With a 120 km view, a 100 km ring would fall outside the image
        kms = [r["km"] for r in build_range_rings(120.0)]
        assert 50.0 in kms
        assert 100.0 not in kms

    def test_rings_are_nearest_first(self):
        from app.api.routes.pages.radar import build_range_rings

        radii = [r["radius"] for r in build_range_rings(400.0)]
        assert radii == sorted(radii)


class TestRangeRingSetting:
    def test_parses_comma_separated_distances(self, monkeypatch):
        from app.config import Settings

        s = Settings(RADAR_RANGE_RINGS_KM="25, 50,100")
        assert s.radar_range_rings == [25.0, 50.0, 100.0]

    def test_empty_disables_rings(self):
        from app.config import Settings

        assert Settings(RADAR_RANGE_RINGS_KM="").radar_range_rings == []

    def test_malformed_entries_are_dropped_not_fatal(self):
        from app.config import Settings

        assert Settings(RADAR_RANGE_RINGS_KM="50,abc,,100,-5").radar_range_rings == [
            50.0,
            100.0,
        ]

    def test_duplicates_collapse(self):
        from app.config import Settings

        assert Settings(RADAR_RANGE_RINGS_KM="50,50,100").radar_range_rings == [
            50.0,
            100.0,
        ]


class TestSourceSelection:
    """
    Coverage areas overlap across the Canada/US border, so a location's own
    national service should win.
    """

    def test_us_location_uses_the_nws_mosaic(self):
        assert source_for(41.26, -95.94, "US").name == "conus"

    def test_canadian_location_prefers_canadian_radar(self):
        """Toronto sits inside the US mosaic's bounds but should use GeoMet."""
        assert source_for(43.65, -79.38, "CA").name == "canada"

    def test_canadian_location_deep_in_the_overlap(self):
        assert source_for(49.90, -97.14, "CA").name == "canada"

    def test_canada_beyond_us_coverage(self):
        """Yellowknife is outside every US region."""
        assert source_for(62.45, -114.37, "CA").name == "canada"

    def test_country_code_is_case_insensitive(self):
        assert source_for(43.65, -79.38, "ca").name == "canada"

    def test_unknown_country_keeps_the_previous_behaviour(self):
        """Without a country code the first matching source wins, as before."""
        assert source_for(43.65, -79.38, None).name == "conus"

    def test_unrelated_country_code_falls_back_to_coverage(self):
        assert source_for(43.65, -79.38, "FR").name == "conus"

    def test_uncovered_location_is_none_regardless_of_country(self):
        assert source_for(51.51, -0.12, "GB") is None
        assert source_for(51.51, -0.12, "CA") is None


class TestIntervalTimeDimension:
    """
    GeoMet and European services advertise an ISO start/end/period interval
    rather than the NWS's explicit list of timestamps.
    """

    def test_expands_an_interval(self):
        xml = (
            '<Dimension name="time">'
            "2026-08-18T17:06:00Z/2026-08-18T17:30:00Z/PT6M"
            "</Dimension>"
        )
        times = RadarClient._parse_time_dimension(xml, "RADAR_1KM_RRAI")

        assert times == [
            datetime(2026, 8, 18, 17, 6, tzinfo=UTC),
            datetime(2026, 8, 18, 17, 12, tzinfo=UTC),
            datetime(2026, 8, 18, 17, 18, tzinfo=UTC),
            datetime(2026, 8, 18, 17, 24, tzinfo=UTC),
            datetime(2026, 8, 18, 17, 30, tzinfo=UTC),
        ]

    def test_expands_hour_and_day_periods(self):
        xml = (
            '<Dimension name="time">'
            "2026-08-16T00:00:00Z/2026-08-18T00:00:00Z/P1D"
            "</Dimension>"
        )
        assert len(RadarClient._parse_time_dimension(xml, "x")) == 3

    def test_handles_fractional_seconds_in_interval_bounds(self):
        """DWD advertises millisecond precision on its interval bounds."""
        xml = (
            '<Dimension name="time">'
            "2026-08-18T20:00:00.000Z/2026-08-18T20:15:00.000Z/PT5M"
            "</Dimension>"
        )
        assert len(RadarClient._parse_time_dimension(xml, "x")) == 4

    def test_mixed_list_and_interval(self):
        xml = (
            '<Dimension name="time">'
            "2026-08-18T10:00:00Z,"
            "2026-08-18T17:06:00Z/2026-08-18T17:18:00Z/PT6M"
            "</Dimension>"
        )
        times = RadarClient._parse_time_dimension(xml, "x")
        assert len(times) == 4
        assert times == sorted(times)

    def test_malformed_interval_is_dropped(self):
        xml = '<Dimension name="time">not/an/interval</Dimension>'
        assert RadarClient._parse_time_dimension(xml, "x") == []

    def test_backwards_interval_is_dropped(self):
        xml = (
            '<Dimension name="time">'
            "2026-08-18T18:00:00Z/2026-08-18T17:00:00Z/PT6M"
            "</Dimension>"
        )
        assert RadarClient._parse_time_dimension(xml, "x") == []

    def test_runaway_interval_is_capped(self):
        """A tiny period over a long span must not expand without bound."""
        xml = (
            '<Dimension name="time">'
            "2020-01-01T00:00:00Z/2026-01-01T00:00:00Z/PT1S"
            "</Dimension>"
        )
        times = RadarClient._parse_time_dimension(xml, "x")
        assert len(times) <= 2000

    def test_duration_parser_rejects_junk(self):
        assert RadarClient._parse_duration("PT0M") is None
        assert RadarClient._parse_duration("banana") is None
        assert RadarClient._parse_duration("PT6M").total_seconds() == 360


class TestCanadianSourceRequests:
    """GeoMet differs from the NWS server in two request details."""

    async def test_capabilities_scoped_by_layers_param(self, client, ca_source):
        import httpx as _httpx
        import respx as _respx

        with _respx.mock(assert_all_called=False) as mock:
            route = mock.get("https://geomet.example.test/geomet").mock(
                return_value=_httpx.Response(
                    200,
                    text=(
                        '<Dimension name="time">'
                        "2026-08-18T17:06:00Z/2026-08-18T17:12:00Z/PT6M"
                        "</Dimension>"
                    ),
                )
            )
            times = await client.available_times(ca_source)

        assert len(times) == 2
        assert route.calls[0].request.url.params["LAYERS"] == "RADAR_1KM_RRAI"

    async def test_time_parameter_omits_fractional_seconds(self, client, ca_source):
        """GeoMet returns a service exception for the NWS millisecond format."""
        import httpx as _httpx
        import respx as _respx

        with _respx.mock(assert_all_called=False) as mock:
            route = mock.get("https://geomet.example.test/geomet").mock(
                return_value=_httpx.Response(
                    200, content=PNG_BYTES, headers={"content-type": "image/png"}
                )
            )
            await client.fetch_frame(
                ca_source,
                (0.0, 0.0, 1.0, 1.0),
                datetime(2026, 8, 18, 17, 6, 0, tzinfo=UTC),
            )

        params = route.calls[0].request.url.params
        assert params["time"] == "2026-08-18T17:06:00Z"
        assert params["layers"] == "RADAR_1KM_RRAI"
