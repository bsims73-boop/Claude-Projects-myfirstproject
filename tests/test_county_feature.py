import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import patch, MagicMock
import app as flask_app


@pytest.fixture
def client():
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as client:
        yield client


# Criterion 1: County field appears on Farm Programs page when page loads
def test_county_dropdown_present_in_html(client):
    response = client.get("/programs")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert 'id="countySelect"' in html
    assert "disabled" in html


# Criterion 5 (part 1): GET /api/counties/<state> returns sorted list for known state
def test_counties_api_returns_list_for_known_state(client):
    response = client.get("/api/counties/Iowa")
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert "Polk" in data
    assert "Story" in data
    assert data == sorted(data)


# Criterion 6: GET /api/counties/<unknown_state> returns 404
def test_counties_api_returns_404_for_unknown_state(client):
    response = client.get("/api/counties/Narnia")
    assert response.status_code == 404


# Criterion 2: Search with county passes county to research_farm_programs
def test_programs_search_with_county_passes_county_to_service(client):
    with patch("modules.programs.research_farm_programs", return_value=[]) as mock_fn:
        response = client.post(
            "/api/programs",
            json={"state": "Iowa", "farm_type": "Dairy", "county": "Polk"},
        )
        assert response.status_code == 200
        mock_fn.assert_called_once_with("Iowa", "Dairy", "Polk", 1)


# Criterion 3: Search without county works and passes empty county
def test_programs_search_without_county_works(client):
    with patch("modules.programs.research_farm_programs", return_value=[]) as mock_fn:
        response = client.post(
            "/api/programs",
            json={"state": "Iowa", "farm_type": "Dairy"},
        )
        assert response.status_code == 200
        args = mock_fn.call_args
        # Accept either ("Iowa", "Dairy", "") or ("Iowa", "Dairy") — both mean no county
        positional = args[0]
        assert positional[0] == "Iowa"
        assert positional[1] == "Dairy"
        if len(positional) > 2:
            assert positional[2] == ""


# Criterion 4: Invalid county is silently dropped (treated as no county)
def test_programs_search_with_invalid_county_drops_it(client):
    with patch("modules.programs.research_farm_programs", return_value=[]) as mock_fn:
        response = client.post(
            "/api/programs",
            json={"state": "Iowa", "farm_type": "Dairy", "county": "FakeCounty123"},
        )
        assert response.status_code == 200
        mock_fn.assert_called_once_with("Iowa", "Dairy", "", 1)


# Criterion 5 (Alaska): Alaska borough names stored without modification
def test_alaska_counties_present(client):
    response = client.get("/api/counties/Alaska")
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert "Fairbanks North Star Borough" in data


# Criterion 5 (Louisiana): Louisiana parish names have Parish suffix stripped
def test_louisiana_counties_stripped(client):
    response = client.get("/api/counties/Louisiana")
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert "East Baton Rouge" in data
