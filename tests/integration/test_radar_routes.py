"""
Integration tests for the radar page and image-serving routes.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.routes import radar as radar_routes
from app.database import SessionLocal
from app.main import app
from app.models.location import Location
from app.models.radar_frame import RadarFrame
from app.services.collectors import radar_collector
from app.services.imagery.radar import BASEMAP_LAYERS

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def radar_storage(tmp_path, monkeypatch):
    """
    Point radar storage at a temp dir.

    location_dir() resolves storage_root() through the collector module's
    globals at call time, so patching it there covers both callers; the route
    module imports storage_root by name, so it needs its own patch.
    """
    monkeypatch.setattr(radar_collector, "storage_root", lambda: tmp_path)
    monkeypatch.setattr(radar_routes, "storage_root", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def radar_location(radar_storage):
    """A US location with one stored radar frame on disk."""
    db = SessionLocal()
    slug = f"radar-city-{uuid.uuid4().hex[:8]}"
    location = Location(
        name="Radar City",
        slug=slug,
        latitude=44.98,
        longitude=-93.27,
        country_code="US",
        enabled=True,
    )
    db.add(location)
    db.commit()

    frame_time = datetime.now(UTC).replace(microsecond=0)
    epoch = int(frame_time.timestamp())

    # Imagery lives under the radar view key, shared by any location with the
    # same coordinates.
    key, _source, bbox = radar_collector.key_for_location(location)
    target = radar_storage / key
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{epoch}.png").write_bytes(PNG_BYTES)
    for band in BASEMAP_LAYERS:
        (target / radar_collector.basemap_name(bbox, band)).write_bytes(PNG_BYTES)

    db.add(
        RadarFrame(
            location_id=location.id,
            frame_time=frame_time,
            file_path=f"{key}/{epoch}.png",
            file_size=len(PNG_BYTES),
        )
    )
    db.commit()

    data = {"id": location.id, "slug": slug, "epoch": epoch}
    db.close()

    yield data

    db = SessionLocal()
    db.query(RadarFrame).filter(RadarFrame.location_id == data["id"]).delete()
    db.query(Location).filter(Location.id == data["id"]).delete()
    db.commit()
    db.close()


@pytest.mark.integration
def test_radar_page_renders(client, radar_location):
    """The radar page renders with a viewer for the location."""
    response = client.get("/radar")
    assert response.status_code == 200
    assert "Radar City" in response.text
    assert "radar-stage" in response.text


@pytest.mark.integration
def test_radar_page_returns_partial_for_htmx(client, radar_location):
    """An HX-Request gets the content partial, not the full page."""
    response = client.get("/radar", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "<!DOCTYPE html>" not in response.text
    assert "Radar City" in response.text


@pytest.mark.integration
def test_frame_is_served_with_immutable_cache(client, radar_location):
    """A stored frame is served as an immutable PNG."""
    response = client.get(
        f"/radar/{radar_location['slug']}/frames/{radar_location['epoch']}.png"
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert "immutable" in response.headers["cache-control"]
    assert response.content == PNG_BYTES


@pytest.mark.integration
def test_basemap_is_served(client, radar_location):
    """The location's basemap is served."""
    response = client.get(f"/radar/{radar_location['slug']}/basemap/admin.png")
    assert response.status_code == 200
    assert response.content == PNG_BYTES


@pytest.mark.integration
def test_unknown_location_returns_404(client):
    """An unknown slug is a 404, not a 500."""
    assert client.get("/radar/nope/basemap/admin.png").status_code == 404
    assert client.get("/radar/nope/frames/123.png").status_code == 404


@pytest.mark.integration
def test_missing_frame_returns_404(client, radar_location):
    """A timestamp with no stored file is a 404."""
    response = client.get(f"/radar/{radar_location['slug']}/frames/1.png")
    assert response.status_code == 404


@pytest.mark.integration
def test_location_outside_coverage_has_no_basemap(client, radar_storage):
    """A non-US location reports no radar coverage rather than erroring."""
    db = SessionLocal()
    slug = f"london-{uuid.uuid4().hex[:8]}"
    location = Location(
        name="London",
        slug=slug,
        latitude=51.5,
        longitude=-0.12,
        country_code="GB",
        enabled=True,
    )
    db.add(location)
    db.commit()
    location_id = location.id
    db.close()

    try:
        response = client.get(f"/radar/{slug}/basemap/admin.png")
        assert response.status_code == 404

        page = client.get("/radar")
        assert "Outside NWS radar coverage" in page.text
    finally:
        db = SessionLocal()
        db.query(Location).filter(Location.id == location_id).delete()
        db.commit()
        db.close()


@pytest.mark.integration
def test_list_reports_when_no_frames_collected_yet(client, radar_storage):
    """A covered location with no frames yet shows a waiting message."""
    db = SessionLocal()
    slug = f"fresh-{uuid.uuid4().hex[:8]}"
    location = Location(
        name="Fresh City",
        slug=slug,
        latitude=41.88,
        longitude=-87.63,
        country_code="US",
        enabled=True,
    )
    db.add(location)
    db.commit()
    location_id = location.id
    db.close()

    try:
        page = client.get("/radar")
        assert "Awaiting first collection" in page.text
    finally:
        db = SessionLocal()
        db.query(Location).filter(Location.id == location_id).delete()
        db.commit()
        db.close()


@pytest.mark.integration
def test_frames_are_ordered_oldest_first(client, radar_storage):
    """Frame URLs are emitted in playback order."""
    db = SessionLocal()
    slug = f"ordered-{uuid.uuid4().hex[:8]}"
    location = Location(
        name="Ordered City",
        slug=slug,
        latitude=44.98,
        longitude=-93.27,
        country_code="US",
        enabled=True,
    )
    db.add(location)
    db.commit()
    location_id = location.id

    now = datetime.now(UTC).replace(microsecond=0)
    times = [now - timedelta(minutes=2 * i) for i in range(3)]
    for t in times:
        db.add(
            RadarFrame(
                location_id=location_id,
                frame_time=t,
                file_path=f"{location_id}/{int(t.timestamp())}.png",
                file_size=1,
            )
        )
    db.commit()
    db.close()

    try:
        from app.api.routes.pages.radar import build_radar_detail

        db = SessionLocal()
        detail = build_radar_detail(db, slug)
        db.close()

        stamps = [f["timestamp"] for f in detail["frames"]]
        assert stamps == sorted(stamps)
    finally:
        db = SessionLocal()
        db.query(RadarFrame).filter(RadarFrame.location_id == location_id).delete()
        db.query(Location).filter(Location.id == location_id).delete()
        db.commit()
        db.close()


@pytest.mark.integration
class TestListAndDetailSplit:
    """
    /radar lists one still per location; /radar/{slug} holds the animated loop.
    """

    def test_list_shows_only_the_latest_frame(self, client, radar_storage):
        """
        The whole point of the split: the list must not embed a full loop, or
        it degrades as retention grows.
        """
        db = SessionLocal()
        slug = f"many-{uuid.uuid4().hex[:8]}"
        location = Location(
            name="Many Frames",
            slug=slug,
            latitude=44.98,
            longitude=-93.27,
            country_code="US",
            enabled=True,
        )
        db.add(location)
        db.commit()
        location_id = location.id

        now = datetime.now(UTC).replace(microsecond=0)
        times = [now - timedelta(minutes=2 * i) for i in range(30)]
        for t in times:
            db.add(
                RadarFrame(
                    location_id=location_id,
                    frame_time=t,
                    file_path=f"{location_id}/{int(t.timestamp())}.png",
                    file_size=1,
                )
            )
        db.commit()
        db.close()

        try:
            page = client.get("/radar").text
            newest_url = f"/radar/{slug}/frames/{int(max(times).timestamp())}.png"
            oldest_url = f"/radar/{slug}/frames/{int(min(times).timestamp())}.png"

            assert newest_url in page
            assert oldest_url not in page
            assert "30 frames" in page

            # ...while the detail view has the whole loop
            detail = client.get(f"/radar/{slug}").text
            assert newest_url in detail
            assert oldest_url in detail
        finally:
            db = SessionLocal()
            db.query(RadarFrame).filter(RadarFrame.location_id == location_id).delete()
            db.query(Location).filter(Location.id == location_id).delete()
            db.commit()
            db.close()

    def test_list_links_to_each_detail_view(self, client, radar_location):
        page = client.get("/radar").text
        assert f'href="/radar/{radar_location["slug"]}"' in page

    def test_detail_page_renders(self, client, radar_location):
        response = client.get(f"/radar/{radar_location['slug']}")
        assert response.status_code == 200
        assert "Radar City" in response.text
        assert "radar-detail-stage" in response.text
        assert 'href="/radar"' in response.text  # back link

    def test_detail_returns_partial_for_htmx(self, client, radar_location):
        response = client.get(
            f"/radar/{radar_location['slug']}", headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        assert "<!DOCTYPE html>" not in response.text
        assert "Radar City" in response.text

    def test_unknown_slug_is_404(self, client):
        assert client.get("/radar/no-such-place").status_code == 404

    def test_detail_route_does_not_shadow_the_image_routes(
        self, client, radar_location
    ):
        """
        /radar/{slug} sits directly above /radar/{slug}/basemap.png, so a
        greedy match here would break every image on the page.
        """
        slug = radar_location["slug"]

        assert (
            client.get(f"/radar/{slug}").headers["content-type"].startswith("text/html")
        )
        assert (
            client.get(f"/radar/{slug}/basemap/admin.png").headers["content-type"]
            == "image/png"
        )
        assert (
            client.get(f"/radar/{slug}/frames/{radar_location['epoch']}.png").headers[
                "content-type"
            ]
            == "image/png"
        )

    def test_uncovered_location_detail_explains_itself(self, client, radar_storage):
        db = SessionLocal()
        slug = f"paris-{uuid.uuid4().hex[:8]}"
        location = Location(
            name="Paris",
            slug=slug,
            latitude=48.86,
            longitude=2.35,
            country_code="FR",
            enabled=True,
        )
        db.add(location)
        db.commit()
        location_id = location.id
        db.close()

        try:
            page = client.get(f"/radar/{slug}")
            assert page.status_code == 200
            assert "outside NWS radar coverage" in page.text
        finally:
            db = SessionLocal()
            db.query(Location).filter(Location.id == location_id).delete()
            db.commit()
            db.close()


@pytest.mark.integration
def test_slugless_location_is_addressable_by_id(client, radar_storage):
    """The list links slugless locations by id, so detail must accept that."""
    db = SessionLocal()
    location = Location(
        name="Slugless Place",
        slug=None,
        latitude=44.98,
        longitude=-93.27,
        country_code="US",
        enabled=True,
    )
    db.add(location)
    db.commit()
    location_id = location.id
    db.close()

    try:
        response = client.get(f"/radar/{location_id}")
        assert response.status_code == 200
        assert "Slugless Place" in response.text
    finally:
        db = SessionLocal()
        db.query(Location).filter(Location.id == location_id).delete()
        db.commit()
        db.close()


@pytest.mark.integration
def test_non_uuid_unknown_slug_is_404_not_500(client):
    """A junk slug must not blow up the UUID parse."""
    assert client.get("/radar/not-a-uuid-at-all").status_code == 404


@pytest.mark.integration
def test_detail_attributes_the_correct_provider(client, radar_storage):
    """
    A Canadian location is served by GeoMet, not the NWS, and the page must say
    so rather than crediting whichever provider happened to be first.
    """
    db = SessionLocal()
    us_slug = f"us-{uuid.uuid4().hex[:8]}"
    ca_slug = f"ca-{uuid.uuid4().hex[:8]}"
    db.add(
        Location(
            name="US Town",
            slug=us_slug,
            latitude=44.98,
            longitude=-93.27,
            country_code="US",
            enabled=True,
        )
    )
    db.add(
        Location(
            name="CA Town",
            slug=ca_slug,
            latitude=43.65,
            longitude=-79.38,
            country_code="CA",
            enabled=True,
        )
    )
    db.commit()
    ids = [
        row.id
        for row in db.query(Location)
        .filter(Location.slug.in_([us_slug, ca_slug]))
        .all()
    ]
    db.close()

    try:
        assert "NWS / MRMS" in client.get(f"/radar/{us_slug}").text
        assert "ECCC / MSC GeoMet" in client.get(f"/radar/{ca_slug}").text
    finally:
        db = SessionLocal()
        for lid in ids:
            db.query(Location).filter(Location.id == lid).delete()
        db.commit()
        db.close()


@pytest.mark.integration
class TestBasemapBands:
    """
    The basemap is split into separately-served bands so water and each
    administrative level can be styled differently client-side — the upstream
    servers publish only line styles and reject custom SLD.
    """

    def test_every_band_is_served(self, client, radar_location):
        for band in BASEMAP_LAYERS:
            response = client.get(
                f"/radar/{radar_location['slug']}/basemap/{band.kind}.png"
            )
            assert response.status_code == 200, f"{band.kind} band missing"
            assert response.headers["content-type"] == "image/png"

    def test_unknown_band_is_404(self, client, radar_location):
        response = client.get(f"/radar/{radar_location['slug']}/basemap/nonsense.png")
        assert response.status_code == 404

    def test_bands_have_distinct_urls(self, client, radar_location):
        page = client.get(f"/radar/{radar_location['slug']}").text
        for band in BASEMAP_LAYERS:
            assert f"/radar/{radar_location['slug']}/basemap/{band.kind}.png" in page

    def test_list_thumbnails_include_the_bands(self, client, radar_location):
        page = client.get("/radar").text
        assert f"/radar/{radar_location['slug']}/basemap/water.png" in page

    def test_band_traversal_is_rejected(self, client, radar_location):
        """The kind segment must not escape the storage directory."""
        response = client.get(
            f"/radar/{radar_location['slug']}/basemap/..%2F..%2Fsecret.png"
        )
        assert response.status_code == 404
