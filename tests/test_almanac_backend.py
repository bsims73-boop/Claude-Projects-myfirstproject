"""
Unit tests for the Farmers Helper Almanac feature.
AC1-14: rename strings, moon phase, frost forecast, Flask routes.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import modules.almanac as almanac  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(json_data, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status = MagicMock()
    return mock


def _make_error_response(status_code=404):
    from requests.exceptions import HTTPError
    mock = MagicMock()
    mock.status_code = status_code
    mock.raise_for_status.side_effect = HTTPError(response=mock)
    return mock


# ---------------------------------------------------------------------------
# Criterion 1 (AC1-3) — Rename: "Farmers Helper" present, "Farm Receipt Manager" absent
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.dirname(__file__))


class TestRename(unittest.TestCase):
    """All 7 rename targets now read 'Farmers Helper', not 'Farm Receipt Manager'."""

    def _check(self, rel_path):
        full = os.path.join(BASE_DIR, rel_path)
        with open(full, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("Farmers Helper", text, msg=f"{rel_path} missing 'Farmers Helper'")
        self.assertNotIn("Farm Receipt Manager", text, msg=f"{rel_path} still contains 'Farm Receipt Manager'")

    def test_base_html_title(self):
        self._check("templates/base.html")

    def test_receipts_html(self):
        self._check("templates/receipts.html")

    def test_summary_html(self):
        self._check("templates/summary.html")

    def test_programs_html(self):
        self._check("templates/programs.html")

    def test_app_py(self):
        self._check("app.py")


# ---------------------------------------------------------------------------
# Criterion 8 (AC3) — start.bat rename
# ---------------------------------------------------------------------------

class TestStartBat(unittest.TestCase):
    """start.bat says 'Farmers Helper', not 'Farm Receipt Manager'."""

    def test_start_bat(self):
        full = os.path.join(BASE_DIR, "start.bat")
        with open(full, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("Farmers Helper", text)
        self.assertNotIn("Farm Receipt Manager", text)


# ---------------------------------------------------------------------------
# Criterion 2 (AC4-6) — get_moon_phase success
# ---------------------------------------------------------------------------

class TestGetMoonPhaseSuccess(unittest.TestCase):
    """get_moon_phase returns correct shape and guidance on success."""

    def test_success_shape_and_guidance(self):
        phases_payload = {
            "phasedata": [
                {"phase": "Waxing Gibbous", "year": 2026, "month": 5, "day": 29, "time": "10:00"},
                {"phase": "Full Moon",       "year": 2026, "month": 5, "day": 31, "time": "08:45"},
                {"phase": "Waning Gibbous",  "year": 2026, "month": 6, "day": 7,  "time": "12:00"},
                {"phase": "Last Quarter",    "year": 2026, "month": 6, "day": 14, "time": "06:00"},
            ]
        }
        oneday_payload = {
            "properties": {
                "data": {
                    "curphase": "Waxing Gibbous",
                    "fracillum": "97%",
                }
            }
        }

        phases_resp = _make_response(phases_payload)
        oneday_resp = _make_response(oneday_payload)

        with patch.object(almanac.requests, "get", side_effect=[phases_resp, oneday_resp]):
            result = almanac.get_moon_phase()

        self.assertIsNone(result["error"])
        self.assertEqual(result["curphase"], "Waxing Gibbous")
        self.assertEqual(result["fracillum"], "97%")
        self.assertIsInstance(result["upcoming"], list)
        self.assertEqual(len(result["upcoming"]), 4)
        self.assertEqual(result["guidance"], almanac.PLANTING_GUIDANCE["Waxing Gibbous"])


# ---------------------------------------------------------------------------
# Criterion 3 (AC7) — get_moon_phase error
# ---------------------------------------------------------------------------

class TestGetMoonPhaseError(unittest.TestCase):
    """get_moon_phase returns error dict when HTTP calls fail."""

    def test_error_dict_on_exception(self):
        with patch.object(almanac.requests, "get", side_effect=Exception("network error")):
            result = almanac.get_moon_phase()

        self.assertIsNotNone(result["error"])
        self.assertTrue(len(result["error"]) > 0)
        self.assertEqual(result["upcoming"], [])
        self.assertIsNone(result["curphase"])


# ---------------------------------------------------------------------------
# Criterion 4 (AC8,9,10) — get_frost_forecast success
# ---------------------------------------------------------------------------

class TestGetFrostForecastSuccess(unittest.TestCase):
    """get_frost_forecast returns correct shape; frost_risk logic is correct."""

    def _run(self):
        geo_payload = {
            "places": [{"place name": "Louisville", "latitude": "38.25", "longitude": "-85.76"}]
        }
        forecast_payload = {
            "timezone": "America/New_York",
            "daily": {
                "time": ["2026-05-29", "2026-05-30", "2026-05-31", "2026-06-01",
                         "2026-06-02", "2026-06-03", "2026-06-04"],
                "temperature_2m_min": [28.0, 40.0, 35.0, 50.0, 55.0, 30.0, 45.0],
            },
        }
        geo_resp = _make_response(geo_payload)
        forecast_resp = _make_response(forecast_payload)

        with patch.object(almanac.requests, "get", side_effect=[geo_resp, forecast_resp]):
            return almanac.get_frost_forecast("40601")

    def test_shape(self):
        result = self._run()
        self.assertIsNone(result["error"])
        self.assertEqual(result["location"], "Louisville")
        self.assertEqual(result["timezone"], "America/New_York")
        self.assertEqual(len(result["forecast"]), 7)

    def test_forecast_item_fields(self):
        result = self._run()
        for item in result["forecast"]:
            self.assertIn("date", item)
            self.assertIn("min_temp_f", item)
            self.assertIn("frost_risk", item)

    def test_frost_risk_true_at_28(self):
        result = self._run()
        day_28 = next(d for d in result["forecast"] if d["min_temp_f"] == 28.0)
        self.assertTrue(day_28["frost_risk"])

    def test_frost_risk_false_at_40(self):
        result = self._run()
        day_40 = next(d for d in result["forecast"] if d["min_temp_f"] == 40.0)
        self.assertFalse(day_40["frost_risk"])


# ---------------------------------------------------------------------------
# Criterion 5 (AC11) — get_frost_forecast bad ZIP
# ---------------------------------------------------------------------------

class TestGetFrostForecastBadZip(unittest.TestCase):
    """get_frost_forecast returns error when ZIP lookup returns 404."""

    def test_bad_zip_returns_error(self):
        from requests.exceptions import HTTPError
        with patch.object(almanac.requests, "get", side_effect=HTTPError("404")):
            result = almanac.get_frost_forecast("00000")

        self.assertIn("error", result)
        self.assertEqual(result["forecast"], [])


# ---------------------------------------------------------------------------
# Criterion 6 (AC13) — get_frost_forecast Open-Meteo failure
# ---------------------------------------------------------------------------

class TestGetFrostForecastOpenMeteoFail(unittest.TestCase):
    """Geocoding succeeds but Open-Meteo fails: error contains 'unavailable', location is set."""

    def test_open_meteo_failure(self):
        geo_payload = {
            "places": [{"place name": "Louisville", "latitude": "38.25", "longitude": "-85.76"}]
        }
        geo_resp = _make_response(geo_payload)

        with patch.object(almanac.requests, "get", side_effect=[geo_resp, Exception("meteo down")]):
            result = almanac.get_frost_forecast("40601")

        self.assertIn("error", result)
        self.assertIn("unavailable", result["error"])
        self.assertIsNotNone(result["location"])
        self.assertEqual(result["forecast"], [])


# ---------------------------------------------------------------------------
# Criterion 7 (AC12, AC14) — Flask routes
# ---------------------------------------------------------------------------

class TestFlaskRoutes(unittest.TestCase):
    """Flask route wiring: /almanac, /api/moon-phase, /api/frost-forecast."""

    def setUp(self):
        import app as flask_app
        flask_app.app.config["TESTING"] = True
        self.client = flask_app.app.test_client()

    def test_almanac_page_returns_200(self):
        resp = self.client.get("/almanac")
        self.assertEqual(resp.status_code, 200)

    def test_api_moon_phase_returns_200(self):
        mock_result = {
            "curphase": "Full Moon", "fracillum": "100%",
            "guidance": "test", "upcoming": [], "error": None,
        }
        with patch("modules.almanac.get_moon_phase", return_value=mock_result):
            resp = self.client.get("/api/moon-phase")
        self.assertEqual(resp.status_code, 200)

    def test_frost_forecast_bad_zip_returns_400(self):
        resp = self.client.post(
            "/api/frost-forecast",
            json={"zip": "12"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_frost_forecast_valid_zip_returns_200(self):
        mock_result = {
            "location": "Louisville", "timezone": "America/New_York",
            "forecast": [], "error": None,
        }
        with patch("modules.almanac.get_frost_forecast", return_value=mock_result):
            resp = self.client.post(
                "/api/frost-forecast",
                json={"zip": "40601"},
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
