"""
Integration tests for the forecast list and detail pages.

/forecast shows a short outlook per location; /forecast/{slug} shows every
upcoming period.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.forecast import Forecast
from app.models.location import Location


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _make_location(slug=None, name="Forecast City", enabled=True):
    db = SessionLocal()
    slug = slug or f"forecast-city-{uuid.uuid4().hex[:8]}"
    location = Location(
        name=name,
        slug=slug,
        latitude=44.98,
        longitude=-93.27,
        country_code="US",
        enabled=enabled,
    )
    db.add(location)
    db.commit()
    data = {"id": location.id, "slug": slug, "name": name}
    db.close()
    return data


def _add_periods(location_id, count=10, source_api="noaa"):
    """Add `count` alternating day/night periods starting now."""
    db = SessionLocal()
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    for i in range(count):
        db.add(
            Forecast(
                location_id=location_id,
                source_api=source_api,
                start_time=start + timedelta(hours=12 * i),
                end_time=start + timedelta(hours=12 * (i + 1)),
                temperature_fahrenheit=60.0 + i,
                temperature=15.0 + i,
                condition_text=f"Condition {i}",
                is_daytime=(i % 2 == 0),
                precipitation_probability=10 * i,
            )
        )
    db.commit()
    db.close()


def _cleanup(location_id):
    db = SessionLocal()
    db.query(Forecast).filter(Forecast.location_id == location_id).delete()
    db.query(Location).filter(Location.id == location_id).delete()
    db.commit()
    db.close()


@pytest.fixture
def forecast_location():
    loc = _make_location()
    _add_periods(loc["id"], count=10)
    yield loc
    _cleanup(loc["id"])


@pytest.mark.integration
class TestForecastList:
    def test_list_renders(self, client, forecast_location):
        response = client.get("/forecast")
        assert response.status_code == 200
        assert forecast_location["name"] in response.text

    def test_list_links_to_detail(self, client, forecast_location):
        page = client.get("/forecast").text
        assert f'href="/forecast/{forecast_location["slug"]}"' in page

    def test_list_previews_only_a_few_periods(self, client, forecast_location):
        """
        The point of the split: the list must stay compact regardless of how
        far out the provider forecasts.
        """
        page = client.get("/forecast").text

        # The first few conditions appear in the summary...
        assert "Condition 0" in page
        # ...but the far-out ones are detail-only.
        assert "Condition 8" not in page
        assert "Condition 9" not in page

    def test_list_shows_period_count(self, client, forecast_location):
        assert "10 periods" in client.get("/forecast").text

    def test_list_returns_partial_for_htmx(self, client, forecast_location):
        response = client.get("/forecast", headers={"HX-Request": "true"})
        assert response.status_code == 200
        assert "<!DOCTYPE html>" not in response.text
        assert forecast_location["name"] in response.text

    def test_location_without_forecast_still_listed(self, client):
        """
        Previously such locations vanished silently; showing them makes a
        missing collection visible.
        """
        loc = _make_location(name="Empty Forecast City")
        try:
            page = client.get("/forecast").text
            assert "Empty Forecast City" in page
            assert "Awaiting first collection" in page
        finally:
            _cleanup(loc["id"])

    def test_disabled_location_is_not_listed(self, client):
        loc = _make_location(name="Disabled City", enabled=False)
        _add_periods(loc["id"], count=4)
        try:
            assert "Disabled City" not in client.get("/forecast").text
        finally:
            _cleanup(loc["id"])


@pytest.mark.integration
class TestForecastDetail:
    def test_detail_renders_every_period(self, client, forecast_location):
        response = client.get(f"/forecast/{forecast_location['slug']}")
        assert response.status_code == 200
        for i in range(10):
            assert f"Condition {i}" in response.text

    def test_detail_has_back_link(self, client, forecast_location):
        page = client.get(f"/forecast/{forecast_location['slug']}").text
        assert 'href="/forecast"' in page

    def test_detail_returns_partial_for_htmx(self, client, forecast_location):
        response = client.get(
            f"/forecast/{forecast_location['slug']}", headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        assert "<!DOCTYPE html>" not in response.text
        assert forecast_location["name"] in response.text

    def test_unknown_slug_is_404(self, client):
        assert client.get("/forecast/no-such-place").status_code == 404

    def test_non_uuid_slug_is_404_not_500(self, client):
        assert client.get("/forecast/not-a-uuid-at-all").status_code == 404

    def test_detail_for_location_without_forecast(self, client):
        loc = _make_location(name="Bare City")
        try:
            response = client.get(f"/forecast/{loc['slug']}")
            assert response.status_code == 200
            assert "No forecast data yet" in response.text
        finally:
            _cleanup(loc["id"])

    def test_expired_periods_are_excluded(self, client):
        """Only periods still ahead of now should show."""
        loc = _make_location(name="Past City")
        db = SessionLocal()
        now = datetime.now(UTC)
        db.add(
            Forecast(
                location_id=loc["id"],
                source_api="noaa",
                start_time=now - timedelta(days=2),
                end_time=now - timedelta(days=1),
                condition_text="Yesterday Weather",
                temperature_fahrenheit=50.0,
            )
        )
        db.add(
            Forecast(
                location_id=loc["id"],
                source_api="noaa",
                start_time=now + timedelta(hours=1),
                end_time=now + timedelta(hours=13),
                condition_text="Tomorrow Weather",
                temperature_fahrenheit=70.0,
            )
        )
        db.commit()
        db.close()

        try:
            page = client.get(f"/forecast/{loc['slug']}").text
            assert "Tomorrow Weather" in page
            assert "Yesterday Weather" not in page
        finally:
            _cleanup(loc["id"])

    def test_slugless_location_addressable_by_id(self, client):
        db = SessionLocal()
        location = Location(
            name="Slugless Forecast",
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
        _add_periods(location_id, count=2)

        try:
            response = client.get(f"/forecast/{location_id}")
            assert response.status_code == 200
            assert "Slugless Forecast" in response.text
        finally:
            _cleanup(location_id)
