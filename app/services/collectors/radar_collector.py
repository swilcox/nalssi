"""
Radar imagery collection service.

Downloads per-location radar frames from the NWS WMS and prunes them on a
rolling retention window. Because the upstream service exposes a time dimension
covering roughly the last two hours, the first collection for a location
backfills its entire history at once rather than accumulating frames over time.
"""

import asyncio
import hashlib
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.location import Location
from app.models.radar_frame import RadarFrame
from app.services.collectors.weather_collector import _run_coro_sync
from app.services.imagery.radar import (
    BASEMAP_LAYERS,
    BasemapLayer,
    BBox,
    RadarClient,
    RadarSource,
    bbox_for,
    bbox_param,
    get_radar_client,
    source_for,
)

logger = structlog.get_logger()


def storage_root() -> Path:
    """Get the configured radar storage root as a Path."""
    return Path(settings.RADAR_STORAGE_DIR)


def radar_key(source: RadarSource, bbox: BBox) -> str:
    """
    Build the storage key identifying a distinct radar view.

    Imagery depends only on the source and the bounding box, never on which
    location asked for it — so several locations sharing coordinates (a common
    way to compare two weather providers for one place) resolve to the same key
    and share a single set of downloads and files.
    """
    fingerprint = f"{source.name}|{bbox_param(bbox)}"
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:16]


def radar_dir(key: str) -> Path:
    """Get the storage directory for a radar view."""
    return storage_root() / key


def key_for_location(location: Location) -> tuple[str, RadarSource, BBox] | None:
    """
    Resolve a location to its radar view key, source and bounding box.

    Returns:
        (key, source, bbox), or None if the location has no radar coverage.
    """
    source = source_for(location.latitude, location.longitude, location.country_code)
    if source is None:
        return None
    bbox = bbox_for(location.latitude, location.longitude, settings.RADAR_VIEW_SPAN_KM)
    return radar_key(source, bbox), source, bbox


def basemap_name(bbox: BBox, layer: BasemapLayer) -> str:
    """
    Build the stored filename for one basemap band.

    The bbox is a pure function of the location's coordinates and the configured
    view span, so each band only ever needs fetching once. The filename embeds a
    hash of everything that determines the image — the bbox *and* the band's
    endpoint and layer list — so changing the view span or the layers produces a
    new name and transparently triggers a refetch, instead of serving a cached
    image that no longer matches what the code would draw.
    """
    fingerprint = f"{bbox_param(bbox)}|{layer.fingerprint()}"
    digest = hashlib.sha256(fingerprint.encode()).hexdigest()[:12]
    return f"basemap-{layer.kind}-{digest}.png"


def frame_name(frame_time: datetime) -> str:
    """Build the frame filename for a timestamp."""
    return f"{int(frame_time.timestamp())}.png"


class RadarCollector:
    """
    Collects radar frames for enabled locations and stores them on disk.
    """

    def __init__(self, client: RadarClient | None = None):
        """Initialize the radar collector."""
        self.client = client or get_radar_client()
        logger.info("Radar collector initialized")

    async def collect_all(self) -> dict[str, int]:
        """
        Collect radar frames for all enabled locations.

        Returns:
            Dictionary with collection statistics
        """
        logger.info("Starting radar collection cycle")
        stats = {
            "total_locations": 0,
            "success_count": 0,
            "error_count": 0,
            "skipped_count": 0,
            "frames_fetched": 0,
            "frames_pruned": 0,
            "files_removed": 0,
            "dirs_removed": 0,
            "view_count": 0,
            "shared_views": 0,
        }

        db = SessionLocal()
        try:
            locations = db.query(Location).filter(Location.enabled.is_(True)).all()
            stats["total_locations"] = len(locations)

            # Group locations by radar view. Several locations often share
            # coordinates — a common way to compare two weather providers for
            # one place — and they must not each download the same imagery.
            groups: dict[str, tuple[RadarSource, BBox, list[Location]]] = {}
            for location in locations:
                resolved = key_for_location(location)
                if resolved is None:
                    stats["skipped_count"] += 1
                    logger.debug(
                        "Skipping radar for location outside coverage",
                        location_name=location.name,
                        location_id=str(location.id),
                    )
                    continue
                key, source, bbox = resolved
                if key in groups:
                    groups[key][2].append(location)
                else:
                    groups[key] = (source, bbox, [location])

            stats["view_count"] = len(groups)
            stats["shared_views"] = sum(
                1 for _, _, members in groups.values() if len(members) > 1
            )

            for key, (source, bbox, members) in groups.items():
                try:
                    fetched = await self._collect_for_view(
                        db, key, source, bbox, members
                    )
                    stats["frames_fetched"] += fetched
                    stats["success_count"] += len(members)
                except Exception:
                    stats["error_count"] += len(members)
                    logger.exception(
                        "Failed to collect radar view",
                        radar_key=key,
                        locations=[loc.name for loc in members],
                    )

            # Prune regardless of fetch outcome so retention holds even while
            # an upstream service is unavailable.
            try:
                stats["frames_pruned"] = self._prune_expired_rows(db)
            except Exception:
                logger.exception("Failed to prune radar frames")

            db.commit()

            try:
                stats["files_removed"] = self._sweep_orphan_files(db)
                stats["dirs_removed"] = self._prune_orphaned_dirs(set(groups))
            except Exception:
                logger.exception("Failed to prune orphaned radar storage")

            logger.info(
                "Radar collection cycle completed",
                total=stats["total_locations"],
                views=stats["view_count"],
                shared_views=stats["shared_views"],
                success=stats["success_count"],
                skipped=stats["skipped_count"],
                errors=stats["error_count"],
                frames_fetched=stats["frames_fetched"],
                frames_pruned=stats["frames_pruned"],
                files_removed=stats["files_removed"],
                dirs_removed=stats["dirs_removed"],
            )
        except Exception:
            logger.exception("Critical error during radar collection")
            db.rollback()
        finally:
            db.close()

        return stats

    async def _collect_for_view(
        self,
        db: Session,
        key: str,
        source: RadarSource,
        bbox: BBox,
        locations: list[Location],
    ) -> int:
        """
        Fetch any frames for a radar view that aren't stored yet.

        Imagery is downloaded and stored once per view, then referenced by a
        row for each location sharing it, so locations at identical coordinates
        cost one download between them while each keeps its own retention and
        cascade-delete behaviour.

        Args:
            db: Database session
            key: Storage key for this view
            source: Radar service covering the view
            bbox: EPSG:3857 bounding box
            locations: Every enabled location sharing this view

        Returns:
            Number of new frames downloaded (not rows written)
        """
        target_dir = radar_dir(key)
        target_dir.mkdir(parents=True, exist_ok=True)

        await self._ensure_basemap(target_dir, bbox)

        available = await self.client.available_times(source)
        if not available:
            logger.warning(
                "Radar service advertised no frames",
                radar_key=key,
                source=source.name,
            )
            return 0

        cutoff = datetime.now(UTC) - timedelta(minutes=settings.RADAR_RETENTION_MINUTES)
        wanted = [t for t in available if t >= cutoff]

        # Existing rows across every location sharing this view.
        held: dict[uuid.UUID, set[datetime]] = {loc.id: set() for loc in locations}
        for row in (
            db.query(RadarFrame)
            .filter(RadarFrame.location_id.in_([loc.id for loc in locations]))
            .all()
        ):
            held.setdefault(row.location_id, set()).add(row.frame_time_utc)

        # A frame only needs downloading if no location already has it on disk.
        on_disk = set().union(*held.values()) if held else set()
        missing = [t for t in wanted if t not in on_disk]

        stored = 0
        if missing:
            logger.info(
                "Fetching radar frames",
                radar_key=key,
                source=source.name,
                locations=[loc.name for loc in locations],
                missing=len(missing),
                backfill=not on_disk,
            )

            semaphore = asyncio.Semaphore(settings.RADAR_MAX_CONCURRENT_FETCHES)

            async def fetch(frame_time: datetime) -> tuple[datetime, bytes] | None:
                async with semaphore:
                    try:
                        data = await self.client.fetch_frame(source, bbox, frame_time)
                        return frame_time, data
                    except Exception:
                        logger.warning(
                            "Failed to fetch radar frame",
                            radar_key=key,
                            frame_time=frame_time.isoformat(),
                            exc_info=True,
                        )
                        return None

            for result in await asyncio.gather(*(fetch(t) for t in missing)):
                if result is None:
                    continue
                frame_time, data = result
                # Write the file before any row so an interrupted run leaves an
                # orphaned file (swept later) rather than a row pointing at a
                # file that doesn't exist.
                (target_dir / frame_name(frame_time)).write_bytes(data)
                on_disk.add(frame_time)
                stored += 1
        else:
            logger.debug(
                "Radar already up to date",
                radar_key=key,
                frames_held=len(on_disk),
            )

        # Give every location a row for each frame present for this view, so a
        # location added later picks up the existing history immediately.
        for location in locations:
            for frame_time in sorted(on_disk):
                if frame_time in held[location.id]:
                    continue
                path = target_dir / frame_name(frame_time)
                if not path.exists():
                    continue
                db.add(
                    RadarFrame(
                        location_id=location.id,
                        frame_time=frame_time,
                        file_path=f"{key}/{frame_name(frame_time)}",
                        file_size=path.stat().st_size,
                    )
                )

        return stored

    async def _ensure_basemap(self, target_dir: Path, bbox: BBox) -> None:
        """
        Fetch each basemap band for a location if it isn't cached yet.

        Bands produced under an older view span or layer set are removed, so a
        changed setting doesn't leave orphaned files behind for every change.
        """
        current = set()
        for layer in BASEMAP_LAYERS:
            name = basemap_name(bbox, layer)
            current.add(name)
            path = target_dir / name
            if path.exists():
                continue

            try:
                data = await self.client.fetch_basemap_layer(layer, bbox)
            except Exception:
                # A missing band degrades the map but shouldn't stop frames
                # from being collected.
                logger.warning(
                    "Failed to fetch basemap band",
                    kind=layer.kind,
                    exc_info=True,
                )
                continue

            path.write_bytes(data)
            logger.info(
                "Stored radar basemap band",
                kind=layer.kind,
                path=str(path),
                bytes=len(data),
            )

        # Runs every cycle, not just after a fetch: a band superseded while the
        # process was down would otherwise never be cleaned up, since the
        # replacement already exists by the time we look.
        for stale in target_dir.glob("basemap-*.png"):
            if stale.name in current:
                continue
            try:
                stale.unlink()
                logger.info("Removed superseded radar basemap", path=str(stale))
            except OSError:
                logger.warning("Could not delete radar basemap", path=str(stale))

    def _prune_expired_rows(self, db: Session) -> int:
        """
        Delete radar frame rows older than the retention window.

        Files are left alone here; they are swept separately once no row of any
        location still references them.

        Returns:
            Number of rows removed
        """
        cutoff = datetime.now(UTC) - timedelta(minutes=settings.RADAR_RETENTION_MINUTES)
        stale = db.query(RadarFrame).filter(RadarFrame.frame_time < cutoff).all()
        for frame in stale:
            db.delete(frame)
        return len(stale)

    def _sweep_orphan_files(self, db: Session) -> int:
        """
        Delete frame files no location references any more.

        Because several locations can share one view's files, a file is only
        safe to remove once no row at all points at it — deleting per location
        would break the others.

        Returns:
            Number of files removed
        """
        root = storage_root()
        if not root.is_dir():
            return 0

        referenced = {row[0] for row in db.query(RadarFrame.file_path).all()}
        removed = 0
        for view_dir in root.iterdir():
            if not view_dir.is_dir():
                continue
            for path in view_dir.glob("*.png"):
                if path.name.startswith("basemap-"):
                    continue
                if f"{view_dir.name}/{path.name}" in referenced:
                    continue
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    logger.warning("Could not delete radar frame", path=str(path))

        return removed

    def _prune_orphaned_dirs(self, active_keys: set[str]) -> int:
        """
        Remove storage directories for radar views nothing needs any more.

        Args:
            active_keys: Keys of the views collected this cycle

        Returns:
            Number of directories removed
        """
        root = storage_root()
        if not root.is_dir():
            return 0

        removed = 0
        for entry in root.iterdir():
            if not entry.is_dir() or entry.name in active_keys:
                continue
            try:
                shutil.rmtree(entry)
                removed += 1
                logger.info("Removed unused radar storage", path=str(entry))
            except OSError:
                logger.warning("Could not remove radar directory", path=str(entry))

        return removed

    def collect_all_sync(self) -> dict[str, int]:
        """Synchronous wrapper for collect_all() for use with APScheduler."""
        return _run_coro_sync(self.collect_all())


# Global collector instance
_radar_collector: RadarCollector | None = None


def get_radar_collector() -> RadarCollector:
    """
    Get or create the global radar collector instance.

    Returns:
        RadarCollector instance
    """
    global _radar_collector
    if _radar_collector is None:
        _radar_collector = RadarCollector()
    return _radar_collector
