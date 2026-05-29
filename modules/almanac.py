import logging
from datetime import date

import requests

logger = logging.getLogger(__name__)

PLANTING_GUIDANCE = {
    "New Moon":        "New moon: rest the soil and focus on soil preparation and amendments.",
    "Waxing Crescent": "Waxing phase: ideal for planting above-ground crops — leafy greens, grains, and herbs.",
    "First Quarter":   "Waxing phase: ideal for planting above-ground crops — leafy greens, grains, and herbs.",
    "Waxing Gibbous":  "Waxing phase: ideal for planting above-ground crops — leafy greens, grains, and herbs.",
    "Full Moon":       "Full moon: great time for harvesting and preserving — sap flow is at its peak.",
    "Waning Gibbous":  "Waning phase: focus on root crops, bulbs, and pruning.",
    "Last Quarter":    "Waning phase: focus on root crops, bulbs, and pruning.",
    "Waning Crescent": "Waning phase: focus on root crops, bulbs, and pruning.",
}


def get_moon_phase():
    """Return current moon phase, illumination, planting guidance, and upcoming phases."""
    today = date.today().strftime("%Y-%m-%d")
    try:
        phases_resp = requests.get(
            f"https://aa.usno.navy.mil/api/moon/phases/date?date={today}&nump=4",
            timeout=10,
        )
        phases_resp.raise_for_status()

        oneday_resp = requests.get(
            f"https://aa.usno.navy.mil/api/rstt/oneday?date={today}&coords=38.0,-97.0&tz=-5",
            timeout=10,
        )
        oneday_resp.raise_for_status()

        phases_data = phases_resp.json()
        oneday_data = oneday_resp.json()

        curphase = oneday_data["properties"]["data"]["curphase"]
        fracillum = oneday_data["properties"]["data"]["fracillum"]
        upcoming = phases_data["phasedata"]

        return {
            "curphase": curphase,
            "fracillum": fracillum,
            "guidance": PLANTING_GUIDANCE.get(curphase, "No guidance available."),
            "upcoming": upcoming,
            "error": None,
        }
    except Exception as e:
        logger.warning("USNO fetch failed: %s", e)
        return {
            "error": "Moon phase data temporarily unavailable.",
            "curphase": None,
            "fracillum": None,
            "guidance": None,
            "upcoming": [],
        }


def get_frost_forecast(zip_code):
    """Return 7-day frost forecast for the given ZIP code."""
    try:
        geo_resp = requests.get(
            f"https://api.zippopotam.us/us/{zip_code}",
            timeout=10,
        )
        geo_resp.raise_for_status()
        geo_data = geo_resp.json()
        location_name = geo_data["places"][0]["place name"]
        lat = geo_data["places"][0]["latitude"]
        lon = geo_data["places"][0]["longitude"]
    except Exception as e:
        logger.warning("Zippopotam fetch failed: %s", e)
        return {"error": f"ZIP code {zip_code} not found.", "location": None, "timezone": None, "forecast": []}

    try:
        forecast_resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_min",
                "forecast_days": 7,
                "timezone": "auto",
                "temperature_unit": "fahrenheit",
            },
            timeout=10,
        )
        forecast_resp.raise_for_status()
        forecast_data = forecast_resp.json()

        timezone = forecast_data["timezone"]
        dates = forecast_data["daily"]["time"]
        min_temps = forecast_data["daily"]["temperature_2m_min"]

        forecast = [
            {
                "date": dates[i],
                "min_temp_f": min_temps[i],
                "frost_risk": min_temps[i] <= 32,
            }
            for i in range(len(dates))
        ]

        return {
            "location": location_name,
            "timezone": timezone,
            "forecast": forecast,
            "error": None,
        }
    except Exception as e:
        logger.warning("Open-Meteo fetch failed: %s", e)
        return {
            "error": "Forecast data temporarily unavailable.",
            "location": location_name,
            "timezone": None,
            "forecast": [],
        }
