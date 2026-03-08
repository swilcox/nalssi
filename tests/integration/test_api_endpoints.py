"""
Integration tests for FastAPI endpoints.

Following TDD: Write tests first, then implement.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """
    Create a test client.

    Uses the app's in-memory database (configured in conftest.py).
    Tables are created by the create_app_tables fixture.
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.integration
def test_health_check(client):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "timestamp" in data


@pytest.mark.integration
def test_create_location(client):
    """Test creating a new location."""
    location_data = {
        "name": "San Francisco, CA",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "timezone": "America/Los_Angeles",
        "country_code": "US",
        "enabled": True,
        "collection_interval": 300,
        "preferred_api": "noaa",
    }

    response = client.post("/api/v1/locations", json=location_data)
    assert response.status_code == 201
    data = response.json()

    assert data["name"] == "San Francisco, CA"
    assert data["latitude"] == 37.7749
    assert data["longitude"] == -122.4194
    assert data["country_code"] == "US"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.integration
def test_create_location_invalid_coordinates(client):
    """Test creating location with invalid coordinates."""
    location_data = {
        "name": "Invalid Location",
        "latitude": 100.0,  # Invalid
        "longitude": 0.0,
        "country_code": "US",
    }

    response = client.post("/api/v1/locations", json=location_data)
    assert response.status_code == 422  # Validation error


@pytest.mark.integration
def test_get_all_locations(client):
    """Test retrieving all locations."""
    # Create a few locations first
    created_names = []
    for i in range(3):
        name = f"Test Location {i}"
        created_names.append(name)
        client.post(
            "/api/v1/locations",
            json={
                "name": name,
                "latitude": 37.0 + i,
                "longitude": -122.0 - i,
                "country_code": "US",
            },
        )

    response = client.get("/api/v1/locations")
    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) >= 3  # At least the ones we created

    # Verify our locations are in the response
    location_names = [loc["name"] for loc in data]
    for name in created_names:
        assert name in location_names


@pytest.mark.integration
def test_get_location_by_id(client):
    """Test retrieving a specific location by ID."""
    # Create a location
    create_response = client.post(
        "/api/v1/locations",
        json={
            "name": "Test Location",
            "latitude": 37.7749,
            "longitude": -122.4194,
            "country_code": "US",
        },
    )
    location_id = create_response.json()["id"]

    # Get the location
    response = client.get(f"/api/v1/locations/{location_id}")
    assert response.status_code == 200
    data = response.json()

    assert data["id"] == location_id
    assert data["name"] == "Test Location"


@pytest.mark.integration
def test_get_nonexistent_location(client):
    """Test getting a location that doesn't exist."""
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response = client.get(f"/api/v1/locations/{fake_uuid}")
    assert response.status_code == 404


@pytest.mark.integration
def test_update_location(client):
    """Test updating a location."""
    # Create a location
    create_response = client.post(
        "/api/v1/locations",
        json={
            "name": "Original Name",
            "latitude": 37.7749,
            "longitude": -122.4194,
            "country_code": "US",
        },
    )
    location_id = create_response.json()["id"]

    # Update the location
    update_data = {"name": "Updated Name", "enabled": False}
    response = client.put(f"/api/v1/locations/{location_id}", json=update_data)
    assert response.status_code == 200
    data = response.json()

    assert data["name"] == "Updated Name"
    assert data["enabled"] is False
    assert data["latitude"] == 37.7749  # Unchanged


@pytest.mark.integration
def test_delete_location(client):
    """Test deleting a location."""
    # Create a location
    create_response = client.post(
        "/api/v1/locations",
        json={
            "name": "To Be Deleted",
            "latitude": 37.7749,
            "longitude": -122.4194,
            "country_code": "US",
        },
    )
    location_id = create_response.json()["id"]

    # Delete the location
    response = client.delete(f"/api/v1/locations/{location_id}")
    assert response.status_code == 204

    # Verify it's gone
    get_response = client.get(f"/api/v1/locations/{location_id}")
    assert get_response.status_code == 404


@pytest.mark.integration
def test_get_current_weather_for_location(client, respx_mock, noaa_responses):
    """Test getting current weather for a location."""
    # Create a location
    create_response = client.post(
        "/api/v1/locations",
        json={
            "name": "San Francisco, CA",
            "latitude": 37.7749,
            "longitude": -122.4194,
            "country_code": "US",
            "preferred_api": "noaa",
        },
    )
    location_id = create_response.json()["id"]

    # Mock NOAA API responses
    import httpx

    respx_mock.get("https://api.weather.gov/points/37.7749,-122.4194").mock(
        return_value=httpx.Response(200, json=noaa_responses["points_response"])
    )
    respx_mock.get("https://api.weather.gov/gridpoints/MTR/90,112/stations").mock(
        return_value=httpx.Response(200, json=noaa_responses["stations_response"])
    )
    respx_mock.get("https://api.weather.gov/stations/KSFO/observations/latest").mock(
        return_value=httpx.Response(200, json=noaa_responses["observation_response"])
    )

    # Get current weather (fresh data from API)
    response = client.get(f"/api/v1/locations/{location_id}/weather/current?fresh=true")
    assert response.status_code == 200
    data = response.json()

    assert data["location_id"] == location_id
    assert data["temperature"] == 18.5
    assert data["source_api"] == "noaa"


@pytest.mark.integration
def test_get_alerts_for_location(client, respx_mock, noaa_responses):
    """Test getting weather alerts for a location."""
    # Create a location
    create_response = client.post(
        "/api/v1/locations",
        json={
            "name": "San Francisco, CA",
            "latitude": 37.7749,
            "longitude": -122.4194,
            "country_code": "US",
        },
    )
    location_id = create_response.json()["id"]

    # Mock NOAA alerts API
    import httpx

    respx_mock.get("https://api.weather.gov/points/37.7749,-122.4194").mock(
        return_value=httpx.Response(200, json=noaa_responses["points_response"])
    )
    respx_mock.get("https://api.weather.gov/alerts/active").mock(
        return_value=httpx.Response(200, json=noaa_responses["alerts_response"])
    )

    # Get alerts (fresh data from API)
    response = client.get(f"/api/v1/locations/{location_id}/alerts?fresh=true")
    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) > 0
    assert data[0]["event"] == "High Wind Warning"


@pytest.mark.integration
def test_create_location_auto_generates_slug(client):
    """Test that creating a location auto-generates a slug from name."""
    response = client.post(
        "/api/v1/locations",
        json={
            "name": "Spring Hill, FL",
            "latitude": 28.4772,
            "longitude": -82.5302,
            "country_code": "US",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["slug"] == "spring_hill_fl"


@pytest.mark.integration
def test_create_location_with_custom_slug(client):
    """Test that a custom slug is preserved."""
    response = client.post(
        "/api/v1/locations",
        json={
            "name": "My Custom Place",
            "slug": "custom_slug",
            "latitude": 40.0,
            "longitude": -74.0,
            "country_code": "US",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["slug"] == "custom_slug"


@pytest.mark.integration
def test_update_location_slug(client):
    """Test updating a location's slug."""
    create_response = client.post(
        "/api/v1/locations",
        json={
            "name": "Test Slug Update",
            "latitude": 37.0,
            "longitude": -122.0,
            "country_code": "US",
        },
    )
    location_id = create_response.json()["id"]

    response = client.put(
        f"/api/v1/locations/{location_id}",
        json={"slug": "new_custom_slug"},
    )
    assert response.status_code == 200
    assert response.json()["slug"] == "new_custom_slug"


@pytest.mark.integration
def test_create_backend_config(client, sample_backend_config_data):
    """Test creating a backend configuration."""
    response = client.post("/api/v1/config/backends", json=sample_backend_config_data)
    assert response.status_code == 201
    data = response.json()

    assert data["name"] == "Test Redis"
    assert data["backend_type"] == "redis"
    assert data["enabled"] is True
    assert data["connection_config"]["url"] == "redis://localhost:6379/0"
    assert data["format_type"] == "kurokku"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.integration
def test_get_backend_configs(client, sample_backend_config_data):
    """Test listing backend configurations."""
    # Create a config first
    client.post("/api/v1/config/backends", json=sample_backend_config_data)

    response = client.get("/api/v1/config/backends")
    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.integration
def test_get_backend_config_by_id(client, sample_backend_config_data):
    """Test getting a specific backend config."""
    create_response = client.post(
        "/api/v1/config/backends", json=sample_backend_config_data
    )
    config_id = create_response.json()["id"]

    response = client.get(f"/api/v1/config/backends/{config_id}")
    assert response.status_code == 200
    assert response.json()["id"] == config_id


@pytest.mark.integration
def test_get_nonexistent_backend_config(client):
    """Test getting a backend config that doesn't exist."""
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response = client.get(f"/api/v1/config/backends/{fake_uuid}")
    assert response.status_code == 404


@pytest.mark.integration
def test_update_backend_config(client, sample_backend_config_data):
    """Test updating a backend configuration."""
    create_response = client.post(
        "/api/v1/config/backends", json=sample_backend_config_data
    )
    config_id = create_response.json()["id"]

    response = client.put(
        f"/api/v1/config/backends/{config_id}",
        json={"name": "Updated Redis", "enabled": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Redis"
    assert data["enabled"] is False
    assert data["backend_type"] == "redis"  # Unchanged


@pytest.mark.integration
def test_delete_backend_config(client, sample_backend_config_data):
    """Test deleting a backend configuration."""
    create_response = client.post(
        "/api/v1/config/backends", json=sample_backend_config_data
    )
    config_id = create_response.json()["id"]

    response = client.delete(f"/api/v1/config/backends/{config_id}")
    assert response.status_code == 204

    # Verify it's gone
    get_response = client.get(f"/api/v1/config/backends/{config_id}")
    assert get_response.status_code == 404


@pytest.mark.integration
def test_update_backend_config_json_fields(client, sample_backend_config_data):
    """Test updating JSON fields on a backend config."""
    create_response = client.post(
        "/api/v1/config/backends", json=sample_backend_config_data
    )
    config_id = create_response.json()["id"]

    response = client.put(
        f"/api/v1/config/backends/{config_id}",
        json={
            "connection_config": {"url": "redis://other:6379/1"},
            "location_filter": {"include": ["spring_hill"]},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["connection_config"]["url"] == "redis://other:6379/1"
    assert data["location_filter"]["include"] == ["spring_hill"]


@pytest.mark.integration
def test_openapi_docs_available(client):
    """Test that OpenAPI docs are available."""
    response = client.get("/docs")
    assert response.status_code == 200

    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert "paths" in data
