"""
Unit tests for the output manager.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.outputs.manager import (
    OutputManager,
    _create_backend,
    _location_matches_filter,
    _parse_json_field,
)


def _make_location(slug="spring_hill", name="Spring Hill", location_id="loc-123"):
    loc = MagicMock()
    loc.slug = slug
    loc.name = name
    loc.id = location_id
    return loc


def _make_backend_config(
    name="test_redis",
    backend_type="redis",
    enabled=True,
    connection_config='{"url": "redis://localhost:6379/0"}',
    format_type="kurokku",
    format_config=None,
    location_filter=None,
):
    config = MagicMock()
    config.name = name
    config.backend_type = backend_type
    config.enabled = enabled
    config.connection_config = connection_config
    config.format_type = format_type
    config.format_config = format_config
    config.location_filter = location_filter
    return config


@pytest.mark.unit
class TestParseJsonField:
    def test_none(self):
        assert _parse_json_field(None) is None

    def test_empty_string(self):
        assert _parse_json_field("") is None

    def test_valid_json(self):
        assert _parse_json_field('{"key": "value"}') == {"key": "value"}

    def test_json_array(self):
        assert _parse_json_field('["a", "b"]') == ["a", "b"]


@pytest.mark.unit
class TestLocationMatchesFilter:
    def test_none_filter_matches_all(self):
        location = _make_location()
        assert _location_matches_filter(location, None) is True

    def test_include_by_slug(self):
        location = _make_location(slug="spring_hill")
        assert _location_matches_filter(location, {"include": ["spring_hill"]}) is True
        assert _location_matches_filter(location, {"include": ["other"]}) is False

    def test_include_by_id(self):
        location = _make_location(location_id="abc-123")
        assert _location_matches_filter(location, {"include": ["abc-123"]}) is True

    def test_exclude_by_slug(self):
        location = _make_location(slug="excluded")
        assert _location_matches_filter(location, {"exclude": ["excluded"]}) is False
        assert _location_matches_filter(location, {"exclude": ["other"]}) is True

    def test_exclude_by_id(self):
        location = _make_location(location_id="abc-123")
        assert _location_matches_filter(location, {"exclude": ["abc-123"]}) is False

    def test_empty_include_excludes_all(self):
        location = _make_location()
        assert _location_matches_filter(location, {"include": []}) is False

    def test_empty_exclude_includes_all(self):
        location = _make_location()
        assert _location_matches_filter(location, {"exclude": []}) is True

    def test_no_slug_uses_empty_string(self):
        location = _make_location(slug=None)
        assert _location_matches_filter(location, {"include": [""]}) is True

    def test_unknown_filter_key_includes_all(self):
        location = _make_location()
        assert _location_matches_filter(location, {"unknown": []}) is True


@pytest.mark.unit
class TestCreateBackend:
    def test_creates_redis_backend(self):
        config = _make_backend_config()
        backend = _create_backend(config)
        assert backend is not None
        assert backend.name == "test_redis"

    def test_unsupported_type_returns_none(self):
        config = _make_backend_config(backend_type="unknown")
        assert _create_backend(config) is None

    def test_passes_format_config(self):
        config = _make_backend_config(
            format_config='{"temp_ttl": 1800}',
        )
        backend = _create_backend(config)
        assert backend.transform is not None
        assert backend.transform.temp_ttl == 1800


@pytest.mark.unit
class TestOutputManager:
    @pytest.mark.asyncio
    async def test_distribute_no_configs(self):
        """When no backend configs exist, returns empty results."""
        manager = OutputManager()
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []

        results = await manager.distribute(db, _make_location(), None, [])
        assert results == []

    @pytest.mark.asyncio
    async def test_distribute_skips_filtered_locations(self):
        """Backend with include filter should skip non-matching locations."""
        manager = OutputManager()
        db = MagicMock()

        config = _make_backend_config(
            location_filter=json.dumps({"include": ["other_location"]})
        )
        db.query.return_value.filter.return_value.all.return_value = [config]

        location = _make_location(slug="spring_hill")
        results = await manager.distribute(db, location, None, [])
        assert results == []

    @pytest.mark.asyncio
    async def test_distribute_calls_write(self):
        """Backend matching location should have write() called."""
        manager = OutputManager()
        db = MagicMock()

        config = _make_backend_config(location_filter=None)
        db.query.return_value.filter.return_value.all.return_value = [config]

        from app.services.outputs.base import WriteResult

        mock_result = WriteResult(success=True, backend_name="test", keys_written=1)

        with patch("app.services.outputs.manager._create_backend") as mock_create:
            mock_backend = AsyncMock()
            mock_backend.write.return_value = mock_result
            mock_create.return_value = mock_backend

            location = _make_location()
            results = await manager.distribute(db, location, None, [])

            assert len(results) == 1
            assert results[0].success is True
            mock_backend.write.assert_called_once()
            mock_backend.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_distribute_catches_backend_errors(self):
        """One backend failing should not affect others."""
        manager = OutputManager()
        db = MagicMock()

        config = _make_backend_config(location_filter=None)
        db.query.return_value.filter.return_value.all.return_value = [config]

        with patch("app.services.outputs.manager._create_backend") as mock_create:
            mock_backend = AsyncMock()
            mock_backend.write.side_effect = Exception("Connection refused")
            mock_create.return_value = mock_backend

            location = _make_location()
            results = await manager.distribute(db, location, None, [])

            assert len(results) == 1
            assert results[0].success is False
            assert "Connection refused" in results[0].errors[0]
