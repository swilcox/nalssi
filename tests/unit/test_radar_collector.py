"""
Tests for the radar imagery collector.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.models.location import Location
from app.models.radar_frame import RadarFrame
from app.services.collectors import radar_collector
from app.services.collectors.radar_collector import (
    RadarCollector,
    basemap_name,
    frame_name,
    key_for_location,
)
from app.services.imagery.radar import (
    BASEMAP_LAYERS,
    BasemapLayer,
    bbox_for,
    source_for,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

# The real US source, so tests exercise the same object the collector builds.
CONUS = source_for(44.98, -93.27, "US")


@pytest.fixture
def storage(tmp_path, monkeypatch):
    """
    Point radar storage at a temp directory.

    Settings are frozen, so the module-level accessor is patched rather than
    the setting itself.
    """
    monkeypatch.setattr(radar_collector, "storage_root", lambda: tmp_path, raising=True)
    return tmp_path


@pytest.fixture
def us_location(db_session):
    location = Location(
        name="Minneapolis",
        slug="minneapolis",
        latitude=44.98,
        longitude=-93.27,
        country_code="US",
        enabled=True,
    )
    db_session.add(location)
    db_session.commit()
    return location


@pytest.fixture
def foreign_location(db_session):
    location = Location(
        name="London",
        slug="london",
        latitude=51.5,
        longitude=-0.12,
        country_code="GB",
        enabled=True,
    )
    db_session.add(location)
    db_session.commit()
    return location


def make_times(count: int, newest: datetime | None = None) -> list[datetime]:
    """Build `count` frame timestamps two minutes apart, oldest first."""
    newest = newest or datetime.now(UTC).replace(microsecond=0)
    return [newest - timedelta(minutes=2 * i) for i in range(count)][::-1]


def resolve(location: Location):
    """Resolve a location's radar view, asserting it has coverage."""
    resolved = key_for_location(location)
    assert resolved is not None, f"{location.name} has no radar coverage"
    return resolved


async def collect(collector: RadarCollector, db, location: Location) -> int:
    """Run one collection pass for a location's radar view."""
    key, source, bbox = resolve(location)
    return await collector._collect_for_view(db, key, source, bbox, [location])


def view_dir(storage, location: Location):
    """Where a location's imagery lives, keyed by its radar view."""
    return storage / resolve(location)[0]


def make_client(times: list[datetime]) -> AsyncMock:
    client = AsyncMock()
    client.available_times = AsyncMock(return_value=times)
    client.fetch_frame = AsyncMock(return_value=PNG_BYTES)
    client.fetch_basemap_layer = AsyncMock(return_value=PNG_BYTES)
    return client


class TestBackfill:
    async def test_first_run_fetches_the_entire_window(
        self, db_session, storage, us_location
    ):
        times = make_times(60)
        client = make_client(times)
        collector = RadarCollector(client=client)

        stored = await collect(collector, db_session, us_location)
        db_session.commit()

        assert stored == 60
        assert client.fetch_frame.await_count == 60
        assert db_session.query(RadarFrame).count() == 60

    async def test_frames_are_written_to_disk(self, db_session, storage, us_location):
        times = make_times(3)
        collector = RadarCollector(client=make_client(times))

        await collect(collector, db_session, us_location)
        db_session.commit()

        location_files = view_dir(storage, us_location)
        for t in times:
            assert (location_files / frame_name(t)).read_bytes() == PNG_BYTES

    async def test_second_run_fetches_only_new_frames(
        self, db_session, storage, us_location
    ):
        newest = datetime.now(UTC).replace(microsecond=0)
        first = make_times(5, newest=newest)
        collector = RadarCollector(client=make_client(first))
        await collect(collector, db_session, us_location)
        db_session.commit()

        # Two new frames appear upstream
        second = first + [
            newest + timedelta(minutes=2),
            newest + timedelta(minutes=4),
        ]
        client = make_client(second)
        collector = RadarCollector(client=client)

        stored = await collect(collector, db_session, us_location)
        db_session.commit()

        assert stored == 2
        assert client.fetch_frame.await_count == 2
        assert db_session.query(RadarFrame).count() == 7

    async def test_no_new_frames_fetches_nothing(
        self, db_session, storage, us_location
    ):
        times = make_times(4)
        collector = RadarCollector(client=make_client(times))
        await collect(collector, db_session, us_location)
        db_session.commit()

        client = make_client(times)
        collector = RadarCollector(client=client)
        stored = await collect(collector, db_session, us_location)

        assert stored == 0
        assert client.fetch_frame.await_count == 0

    async def test_frames_older_than_retention_are_not_fetched(
        self, db_session, storage, us_location
    ):
        from app.config import settings

        now = datetime.now(UTC).replace(microsecond=0)
        times = [
            now - timedelta(minutes=settings.RADAR_RETENTION_MINUTES + 30),
            now - timedelta(minutes=10),
            now,
        ]
        client = make_client(times)
        collector = RadarCollector(client=client)

        stored = await collect(collector, db_session, us_location)

        assert stored == 2

    async def test_a_failed_frame_does_not_abort_the_rest(
        self, db_session, storage, us_location
    ):
        times = make_times(4)
        client = make_client(times)
        client.fetch_frame = AsyncMock(
            side_effect=[PNG_BYTES, RuntimeError("boom"), PNG_BYTES, PNG_BYTES]
        )
        collector = RadarCollector(client=client)

        stored = await collect(collector, db_session, us_location)
        db_session.commit()

        assert stored == 3
        assert db_session.query(RadarFrame).count() == 3

    async def test_empty_time_dimension_stores_nothing(
        self, db_session, storage, us_location
    ):
        collector = RadarCollector(client=make_client([]))

        stored = await collect(collector, db_session, us_location)

        assert stored == 0


class TestBasemap:
    async def test_basemap_is_fetched_once_and_reused(
        self, db_session, storage, us_location
    ):
        times = make_times(2)
        client = make_client(times)
        collector = RadarCollector(client=client)

        await collect(collector, db_session, us_location)
        db_session.commit()
        await collect(collector, db_session, us_location)

        # One fetch per band on the first pass, nothing on the second.
        assert client.fetch_basemap_layer.await_count == len(BASEMAP_LAYERS)

    async def test_basemap_filename_tracks_the_bbox(
        self, db_session, storage, us_location
    ):
        collector = RadarCollector(client=make_client(make_times(1)))
        await collect(collector, db_session, us_location)

        from app.config import settings

        bbox = bbox_for(
            us_location.latitude, us_location.longitude, settings.RADAR_VIEW_SPAN_KM
        )
        for band in BASEMAP_LAYERS:
            expected = view_dir(storage, us_location) / basemap_name(bbox, band)
            assert expected.is_file(), f"missing {band.kind} band"

    def test_changing_the_span_changes_the_basemap_name(self):
        band = BASEMAP_LAYERS[0]
        near = bbox_for(44.98, -93.27, 240.0)
        far = bbox_for(44.98, -93.27, 480.0)
        assert basemap_name(near, band) != basemap_name(far, band)

    def test_each_band_gets_its_own_filename(self):
        bbox = bbox_for(44.98, -93.27, 240.0)
        names = {basemap_name(bbox, band) for band in BASEMAP_LAYERS}
        assert len(names) == len(BASEMAP_LAYERS)


class TestPruning:
    async def test_prune_removes_expired_rows_and_files(
        self, db_session, storage, us_location
    ):
        from app.config import settings

        now = datetime.now(UTC).replace(microsecond=0)
        stale_time = now - timedelta(minutes=settings.RADAR_RETENTION_MINUTES + 30)
        collector = RadarCollector(client=make_client([]))

        target = view_dir(storage, us_location)
        target.mkdir(parents=True, exist_ok=True)
        stale_file = target / frame_name(stale_time)
        stale_file.write_bytes(PNG_BYTES)

        db_session.add(
            RadarFrame(
                location_id=us_location.id,
                frame_time=stale_time,
                file_path=f"{us_location.id}/{frame_name(stale_time)}",
                file_size=len(PNG_BYTES),
            )
        )
        db_session.commit()

        removed = collector._prune_expired_rows(db_session)
        db_session.commit()
        collector._sweep_orphan_files(db_session)

        assert removed == 1
        assert not stale_file.exists()
        assert db_session.query(RadarFrame).count() == 0

    async def test_prune_keeps_fresh_frames(self, db_session, storage, us_location):
        collector = RadarCollector(client=make_client(make_times(3)))
        await collect(collector, db_session, us_location)
        db_session.commit()

        removed = collector._prune_expired_rows(db_session)

        assert removed == 0
        assert db_session.query(RadarFrame).count() == 3

    async def test_prune_tolerates_a_missing_file(
        self, db_session, storage, us_location
    ):
        from app.config import settings

        stale_time = datetime.now(UTC) - timedelta(
            minutes=settings.RADAR_RETENTION_MINUTES + 30
        )
        db_session.add(
            RadarFrame(
                location_id=us_location.id,
                frame_time=stale_time,
                file_path=f"{us_location.id}/gone.png",
                file_size=0,
            )
        )
        db_session.commit()
        collector = RadarCollector(client=make_client([]))

        assert collector._prune_expired_rows(db_session) == 1


class TestCollectAll:
    async def test_skips_locations_outside_radar_coverage(
        self, db_session, storage, foreign_location
    ):
        client = make_client(make_times(3))
        collector = RadarCollector(client=client)

        with patch(
            "app.services.collectors.radar_collector.SessionLocal",
            return_value=db_session,
        ):
            stats = await collector.collect_all()

        assert stats["skipped_count"] == 1
        assert stats["success_count"] == 0
        assert client.fetch_frame.await_count == 0

    async def test_collects_covered_locations(
        self, db_session, storage, us_location, foreign_location
    ):
        client = make_client(make_times(3))
        collector = RadarCollector(client=client)

        with patch(
            "app.services.collectors.radar_collector.SessionLocal",
            return_value=db_session,
        ):
            stats = await collector.collect_all()

        assert stats["total_locations"] == 2
        assert stats["skipped_count"] == 1
        assert stats["success_count"] == 1
        assert stats["frames_fetched"] == 3

    async def test_one_location_failing_does_not_stop_others(
        self, db_session, storage, us_location
    ):
        other = Location(
            name="Chicago",
            slug="chicago",
            latitude=41.88,
            longitude=-87.63,
            country_code="US",
            enabled=True,
        )
        db_session.add(other)
        db_session.commit()

        client = make_client(make_times(2))
        client.available_times = AsyncMock(
            side_effect=[RuntimeError("upstream down"), make_times(2)]
        )
        collector = RadarCollector(client=client)

        with patch(
            "app.services.collectors.radar_collector.SessionLocal",
            return_value=db_session,
        ):
            stats = await collector.collect_all()

        assert stats["error_count"] == 1
        assert stats["success_count"] == 1


class TestBasemapCacheInvalidation:
    """
    The basemap filename must change whenever anything that determines the
    image changes, or a cached file silently outlives the config that made it.
    """

    def test_changing_layers_changes_the_name(self):
        """A band's endpoint and layer list are part of its identity."""
        from app.services.imagery.radar import BasemapLayer

        bbox = bbox_for(44.98, -93.27, 240.0)
        original = BasemapLayer(kind="admin", url="http://x/ows", layers="a,b")
        changed = BasemapLayer(kind="admin", url="http://x/ows", layers="a")

        assert basemap_name(bbox, original) != basemap_name(bbox, changed)

    def test_canadian_provinces_are_in_the_basemap(self):
        """Border cities have half their view in Canada."""
        admin = next(b for b in BASEMAP_LAYERS if b.kind == "admin")
        assert "nws:ca_provinces" in admin.layers

    def test_water_and_boundaries_are_separate_bands(self):
        """Separate bands are what allow them to be styled differently."""
        kinds = [b.kind for b in BASEMAP_LAYERS]
        assert "water" in kinds
        assert "counties" in kinds
        assert "admin" in kinds

    async def test_stale_basemap_is_refetched_after_a_layer_change(
        self, db_session, storage, us_location, monkeypatch
    ):
        client = make_client(make_times(1))
        collector = RadarCollector(client=client)
        await collect(collector, db_session, us_location)
        db_session.commit()
        assert client.fetch_basemap_layer.await_count == len(BASEMAP_LAYERS)

        monkeypatch.setattr(
            radar_collector,
            "BASEMAP_LAYERS",
            (BasemapLayer(kind="admin", url="http://x/ows", layers="only"),),
        )
        await collect(collector, db_session, us_location)

        assert client.fetch_basemap_layer.await_count == len(BASEMAP_LAYERS) + 1

    async def test_superseded_basemap_file_is_removed(
        self, db_session, storage, us_location, monkeypatch
    ):
        """A layer/span change shouldn't leave an orphan file behind forever."""
        collector = RadarCollector(client=make_client(make_times(1)))
        await collect(collector, db_session, us_location)
        db_session.commit()

        target = view_dir(storage, us_location)
        original = {p.name for p in target.glob("basemap-*.png")}
        assert len(original) == len(BASEMAP_LAYERS)

        monkeypatch.setattr(
            radar_collector,
            "BASEMAP_LAYERS",
            (BasemapLayer(kind="admin", url="http://x/ows", layers="only"),),
        )
        await collect(collector, db_session, us_location)

        remaining = list(target.glob("basemap-*.png"))
        assert len(remaining) == 1
        assert remaining[0].name != original


class TestOrphanCleanup:
    """Storage shouldn't accumulate files for config or locations that are gone."""

    async def test_orphan_basemap_cleaned_even_without_a_new_fetch(
        self, db_session, storage, us_location
    ):
        """
        The replacement may already exist — e.g. the layer set changed while
        the process was down — so cleanup can't be conditional on fetching.
        """
        collector = RadarCollector(client=make_client(make_times(1)))
        await collect(collector, db_session, us_location)
        db_session.commit()

        target = view_dir(storage, us_location)
        current = {p.name for p in target.glob("basemap-*.png")}
        orphan = target / "basemap-admin-deadbeef0000.png"
        orphan.write_bytes(PNG_BYTES)
        assert len(list(target.glob("basemap-*.png"))) == len(current) + 1

        await collect(collector, db_session, us_location)

        remaining = {p.name for p in target.glob("basemap-*.png")}
        assert remaining == current

    async def test_directory_for_deleted_location_is_removed(
        self, db_session, storage, us_location
    ):
        collector = RadarCollector(client=make_client(make_times(1)))
        await collect(collector, db_session, us_location)
        db_session.commit()

        ghost = storage / "11111111-2222-3333-4444-555555555555"
        ghost.mkdir()
        (ghost / "1.png").write_bytes(PNG_BYTES)

        removed = collector._prune_orphaned_dirs({resolve(us_location)[0]})

        assert removed == 1
        assert not ghost.exists()
        assert (view_dir(storage, us_location)).is_dir()

    async def test_disabled_location_keeps_its_directory(
        self, db_session, storage, us_location
    ):
        """Disabled is not deleted — the row still exists and may come back."""
        collector = RadarCollector(client=make_client(make_times(1)))
        await collect(collector, db_session, us_location)
        db_session.commit()

        us_location.enabled = False
        db_session.commit()

        assert collector._prune_orphaned_dirs({resolve(us_location)[0]}) == 0
        assert (view_dir(storage, us_location)).is_dir()

    def test_missing_storage_root_is_not_an_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(radar_collector, "storage_root", lambda: tmp_path / "nope")
        collector = RadarCollector(client=make_client([]))

        assert collector._prune_orphaned_dirs(set()) == 0


class TestSharedViews:
    """
    Several locations often share coordinates — a common way to compare two
    weather providers for one place — and must not each download the same
    imagery.
    """

    @pytest.fixture
    def twin_locations(self, db_session):
        """Two locations at identical coordinates, different providers."""
        pair = []
        for slug, api in (("mpls_noaa", "noaa"), ("mpls_owm", "openweather")):
            location = Location(
                name=f"Minneapolis ({api})",
                slug=slug,
                latitude=44.98,
                longitude=-93.27,
                country_code="US",
                preferred_api=api,
                enabled=True,
            )
            db_session.add(location)
            pair.append(location)
        db_session.commit()
        return pair

    def test_identical_coordinates_share_a_key(self, twin_locations):
        first, second = twin_locations
        assert resolve(first)[0] == resolve(second)[0]

    def test_different_coordinates_do_not_share_a_key(self, db_session):
        a = Location(name="A", latitude=44.98, longitude=-93.27, country_code="US")
        b = Location(name="B", latitude=41.26, longitude=-95.94, country_code="US")
        assert resolve(a)[0] != resolve(b)[0]

    async def test_shared_view_downloads_frames_once(
        self, db_session, storage, twin_locations
    ):
        times = make_times(5)
        client = make_client(times)
        collector = RadarCollector(client=client)

        key, source, bbox = resolve(twin_locations[0])
        stored = await collector._collect_for_view(
            db_session, key, source, bbox, twin_locations
        )
        db_session.commit()

        # Downloaded once...
        assert stored == 5
        assert client.fetch_frame.await_count == 5
        # ...and the basemap too
        assert client.fetch_basemap_layer.await_count == len(BASEMAP_LAYERS)
        # ...but both locations can show it
        assert db_session.query(RadarFrame).count() == 10

    async def test_shared_view_stores_one_copy_on_disk(
        self, db_session, storage, twin_locations
    ):
        collector = RadarCollector(client=make_client(make_times(5)))
        key, source, bbox = resolve(twin_locations[0])
        await collector._collect_for_view(db_session, key, source, bbox, twin_locations)
        db_session.commit()

        frames = list((storage / key).glob("[0-9]*.png"))
        assert len(frames) == 5
        assert len(list(storage.iterdir())) == 1

    async def test_both_locations_reference_the_same_files(
        self, db_session, storage, twin_locations
    ):
        collector = RadarCollector(client=make_client(make_times(3)))
        key, source, bbox = resolve(twin_locations[0])
        await collector._collect_for_view(db_session, key, source, bbox, twin_locations)
        db_session.commit()

        paths = {
            loc.id: {
                row.file_path
                for row in db_session.query(RadarFrame)
                .filter(RadarFrame.location_id == loc.id)
                .all()
            }
            for loc in twin_locations
        }
        first, second = twin_locations
        assert paths[first.id] == paths[second.id]

    async def test_a_second_location_joining_reuses_existing_frames(
        self, db_session, storage, twin_locations
    ):
        """Adding a twin later shouldn't re-download the history."""
        first, second = twin_locations
        key, source, bbox = resolve(first)
        # Pin the frame list: the upstream window must look identical across
        # both passes for this to test reuse rather than drift.
        times = make_times(4)

        collector = RadarCollector(client=make_client(times))
        await collector._collect_for_view(db_session, key, source, bbox, [first])
        db_session.commit()

        client = make_client(times)
        collector = RadarCollector(client=client)
        await collector._collect_for_view(
            db_session, key, source, bbox, [first, second]
        )
        db_session.commit()

        assert client.fetch_frame.await_count == 0
        assert (
            db_session.query(RadarFrame)
            .filter(RadarFrame.location_id == second.id)
            .count()
            == 4
        )

    async def test_files_survive_until_the_last_reference_goes(
        self, db_session, storage, twin_locations
    ):
        """
        Deleting one location's rows must not delete imagery the other still
        references.
        """
        first, second = twin_locations
        key, source, bbox = resolve(first)
        collector = RadarCollector(client=make_client(make_times(3)))
        await collector._collect_for_view(db_session, key, source, bbox, twin_locations)
        db_session.commit()

        db_session.query(RadarFrame).filter(RadarFrame.location_id == first.id).delete()
        db_session.commit()

        assert collector._sweep_orphan_files(db_session) == 0
        assert len(list((storage / key).glob("[0-9]*.png"))) == 3

        # Now the last reference goes.
        db_session.query(RadarFrame).filter(
            RadarFrame.location_id == second.id
        ).delete()
        db_session.commit()

        assert collector._sweep_orphan_files(db_session) == 3
        assert list((storage / key).glob("[0-9]*.png")) == []

    async def test_sweep_leaves_basemap_bands_alone(
        self, db_session, storage, us_location
    ):
        """Basemaps have no rows, so the sweep must not treat them as orphans."""
        collector = RadarCollector(client=make_client(make_times(2)))
        await collect(collector, db_session, us_location)
        db_session.commit()

        collector._sweep_orphan_files(db_session)

        bands = list(view_dir(storage, us_location).glob("basemap-*.png"))
        assert len(bands) == len(BASEMAP_LAYERS)


class TestCollectAllDeduplication:
    async def test_twin_locations_counted_as_one_view(self, db_session, storage):
        for slug in ("twin_a", "twin_b"):
            db_session.add(
                Location(
                    name=slug,
                    slug=slug,
                    latitude=44.98,
                    longitude=-93.27,
                    country_code="US",
                    enabled=True,
                )
            )
        db_session.commit()

        client = make_client(make_times(3))
        collector = RadarCollector(client=client)
        with patch(
            "app.services.collectors.radar_collector.SessionLocal",
            return_value=db_session,
        ):
            stats = await collector.collect_all()

        assert stats["total_locations"] == 2
        assert stats["view_count"] == 1
        assert stats["shared_views"] == 1
        assert stats["frames_fetched"] == 3
        assert client.fetch_frame.await_count == 3
