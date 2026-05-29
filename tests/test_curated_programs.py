"""
Unit tests for the State Curated Programs feature.
Covers: JSON schema, _get_curated helper, pipeline merge, Claude exclusion,
deduplication, non-pilot state isolation, sources_queried, and keyword broadening.
"""

import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import config  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers (same pattern as test_programs_cache.py)
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = {
    "curated_id", "state", "program_name", "agency", "level", "source",
    "description", "eligibility", "how_to_apply", "documents_needed",
    "website", "deadline",
}

_EXPECTED_IDS = {
    "ky-kafc-ailp", "ky-kafc-bfl", "ky-kadf", "ky-kdfwr-hip",
    "oh-aglink", "oh-h2ohio", "oh-odnr-whi",
    "wv-ag-investment", "wv-veterans-ag", "wv-agep", "wv-dnr-pfw",
}


def _make_cache_row(programs, seen_ids=None, age_days=0):
    updated = (datetime.now() - timedelta(days=age_days)).isoformat()
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "programs_json": json.dumps(programs),
        "seen_ids_json": json.dumps(seen_ids or []),
        "updated_at": updated,
    }[k]
    return row


def _make_claude_response(text):
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    return response


def _make_programs(n, id_field="opportunity_id", prefix="opp"):
    result = []
    for i in range(n):
        result.append({
            "title": f"Program {i}",
            id_field: f"{prefix}{i}",
            "agency": "USDA",
            "source": "grants.gov",
            "synopsis": None,
            "close_date": None,
            "award_ceiling": None,
            "opportunity_number": None,
        })
    return result


# ---------------------------------------------------------------------------
# 1. TestCuratedJsonSchema
# ---------------------------------------------------------------------------

class TestCuratedJsonSchema(unittest.TestCase):
    """Validates the structure of static/data/curated_state_programs.json."""

    def setUp(self):
        json_path = config.BASE_DIR / "static" / "data" / "curated_state_programs.json"
        with open(json_path, encoding="utf-8") as fh:
            self.programs = json.load(fh)

    def test_exactly_11_records(self):
        self.assertEqual(len(self.programs), 11)

    def test_all_curated_ids_present(self):
        found_ids = {p["curated_id"] for p in self.programs}
        self.assertEqual(found_ids, _EXPECTED_IDS)

    def test_all_required_fields_present(self):
        for p in self.programs:
            missing = _REQUIRED_FIELDS - p.keys()
            self.assertFalse(missing, f"{p.get('curated_id')} missing fields: {missing}")

    def test_source_is_state_programs(self):
        for p in self.programs:
            self.assertEqual(p["source"], "state-programs", f"{p.get('curated_id')} has wrong source")

    def test_level_is_state(self):
        for p in self.programs:
            self.assertEqual(p["level"], "state", f"{p.get('curated_id')} has wrong level")


# ---------------------------------------------------------------------------
# 2. TestGetCuratedHelper
# ---------------------------------------------------------------------------

class TestGetCuratedHelper(unittest.TestCase):
    """Tests for the _get_curated private helper."""

    def _get_curated(self, state):
        from modules.programs import _get_curated
        return _get_curated(state)

    def test_ky_returns_non_empty(self):
        self.assertTrue(len(self._get_curated("KY")) > 0)

    def test_oh_returns_non_empty(self):
        self.assertTrue(len(self._get_curated("OH")) > 0)

    def test_wv_returns_non_empty(self):
        self.assertTrue(len(self._get_curated("WV")) > 0)

    def test_tx_returns_empty(self):
        self.assertEqual(self._get_curated("TX"), [])

    def test_ca_returns_empty(self):
        self.assertEqual(self._get_curated("CA"), [])

    def test_indiana_returns_empty(self):
        self.assertEqual(self._get_curated("Indiana"), [])

    def test_lowercase_ky_works(self):
        self.assertEqual(self._get_curated("ky"), self._get_curated("KY"))

    def test_ky_count(self):
        self.assertEqual(len(self._get_curated("KY")), 4)

    def test_oh_count(self):
        self.assertEqual(len(self._get_curated("OH")), 3)

    def test_wv_count(self):
        self.assertEqual(len(self._get_curated("WV")), 4)


# ---------------------------------------------------------------------------
# 3. TestCuratedMergeInPipeline
# ---------------------------------------------------------------------------

class TestCuratedMergeInPipeline(unittest.TestCase):
    """Curated programs appear in result when all API fetchers return empty."""

    def test_curated_programs_returned_when_apis_empty(self):
        with patch("modules.programs.db") as mock_db, \
             patch("modules.api_clients.fetch_grants_gov", return_value=[]), \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]), \
             patch("modules.programs.get_client") as mock_get_client:

            mock_db.get_program_cache.return_value = None

            from modules.programs import research_farm_programs
            result = research_farm_programs("KY", "Dairy", "")

        self.assertTrue(len(result["programs"]) > 0)

    def test_ky_ailp_present(self):
        with patch("modules.programs.db") as mock_db, \
             patch("modules.api_clients.fetch_grants_gov", return_value=[]), \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]), \
             patch("modules.programs.get_client") as mock_get_client:

            mock_db.get_program_cache.return_value = None

            from modules.programs import research_farm_programs
            result = research_farm_programs("KY", "Dairy", "")

        ids = [p.get("curated_id") for p in result["programs"]]
        self.assertIn("ky-kafc-ailp", ids)

    def test_claude_not_called_when_only_curated(self):
        with patch("modules.programs.db") as mock_db, \
             patch("modules.api_clients.fetch_grants_gov", return_value=[]), \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]), \
             patch("modules.programs.get_client") as mock_get_client:

            mock_db.get_program_cache.return_value = None

            from modules.programs import research_farm_programs
            research_farm_programs("KY", "Dairy", "")

        mock_get_client.assert_not_called()


# ---------------------------------------------------------------------------
# 4. TestCuratedNotSentToClaude
# ---------------------------------------------------------------------------

class TestCuratedNotSentToClaude(unittest.TestCase):
    """Curated programs are never included in the prompt sent to Claude."""

    def test_curated_ids_not_in_claude_prompt(self):
        raw = _make_programs(2)
        enriched = [{"program_name": f"Enriched {i}", "agency": "USDA"} for i in range(2)]

        with patch("modules.programs.db") as mock_db, \
             patch("modules.api_clients.fetch_grants_gov", return_value=raw), \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]), \
             patch("modules.programs.get_client") as mock_get_client:

            mock_db.get_program_cache.return_value = None
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(json.dumps(enriched))
            mock_get_client.return_value = mock_client

            from modules.programs import research_farm_programs
            research_farm_programs("KY", "Dairy", "")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        self.assertNotIn("curated_id", user_content)
        self.assertNotIn("ky-kafc-ailp", user_content)


# ---------------------------------------------------------------------------
# 5. TestCuratedNoDuplication
# ---------------------------------------------------------------------------

class TestCuratedNoDuplication(unittest.TestCase):
    """ky-kafc-ailp appears exactly once even after a force_refresh."""

    def test_no_duplication_on_force_refresh(self):
        # First call: no cache, APIs return empty, curated programs are returned
        with patch("modules.programs.db") as mock_db, \
             patch("modules.api_clients.fetch_grants_gov", return_value=[]), \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]):

            mock_db.get_program_cache.return_value = None

            from modules.programs import research_farm_programs
            first = research_farm_programs("KY", "Dairy", "", force_refresh=True)

        # Second call: cache returns programs from first call (including curated)
        all_ids = [p.get("curated_id") for p in first["programs"] if p.get("curated_id")]
        row = _make_cache_row(first["programs"], seen_ids=all_ids, age_days=0)

        with patch("modules.programs.db") as mock_db, \
             patch("modules.api_clients.fetch_grants_gov", return_value=[]), \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]):

            mock_db.get_program_cache.return_value = row

            second = research_farm_programs("KY", "Dairy", "", force_refresh=True)

        ailp_count = sum(
            1 for p in second["programs"] if p.get("curated_id") == "ky-kafc-ailp"
        )
        self.assertEqual(ailp_count, 1)


# ---------------------------------------------------------------------------
# 6. TestNonPilotStateNoCurated
# ---------------------------------------------------------------------------

class TestNonPilotStateNoCurated(unittest.TestCase):
    """Non-pilot state (TX) never receives curated programs."""

    def test_tx_returns_no_programs_when_apis_empty(self):
        with patch("modules.programs.db") as mock_db, \
             patch("modules.api_clients.fetch_grants_gov", return_value=[]), \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]):

            mock_db.get_program_cache.return_value = None

            from modules.programs import research_farm_programs
            result = research_farm_programs("TX", "Dairy", "")

        self.assertEqual(result["programs"], [])


# ---------------------------------------------------------------------------
# 7. TestSourcesQueriedIncludesStatePrograms
# ---------------------------------------------------------------------------

class TestSourcesQueriedIncludesStatePrograms(unittest.TestCase):
    """state-programs is in sources_queried for pilot states."""

    def test_ky_has_state_programs_in_sources(self):
        with patch("modules.programs.db") as mock_db, \
             patch("modules.api_clients.fetch_grants_gov", return_value=[]), \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]):

            mock_db.get_program_cache.return_value = None

            from modules.programs import research_farm_programs
            result = research_farm_programs("KY", "Dairy", "")

        self.assertIn("state-programs", result["sources_queried"])


# ---------------------------------------------------------------------------
# 8. TestSourcesQueriedNonPilot
# ---------------------------------------------------------------------------

class TestSourcesQueriedNonPilot(unittest.TestCase):
    """state-programs is NOT in sources_queried for non-pilot states."""

    def test_tx_does_not_have_state_programs_in_sources(self):
        with patch("modules.programs.db") as mock_db, \
             patch("modules.api_clients.fetch_grants_gov", return_value=[]), \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]):

            mock_db.get_program_cache.return_value = None

            from modules.programs import research_farm_programs
            result = research_farm_programs("TX", "Dairy", "")

        self.assertNotIn("state-programs", result["sources_queried"])


# ---------------------------------------------------------------------------
# 9. TestCacheHitSourcesQueried
# ---------------------------------------------------------------------------

class TestCacheHitSourcesQueried(unittest.TestCase):
    """Cache-hit path returns computed sources_queried, not empty list (Change D)."""

    def test_cache_hit_includes_state_programs_for_ky(self):
        cached = [{"program_name": "Cached Program", "agency": "USDA"}]
        row = _make_cache_row(cached, age_days=0)

        with patch("modules.programs.db") as mock_db:
            mock_db.get_program_cache.return_value = row

            from modules.programs import research_farm_programs
            result = research_farm_programs("KY", "Dairy", "", False)

        self.assertIn("state-programs", result["sources_queried"])

    def test_cache_hit_excludes_state_programs_for_tx(self):
        cached = [{"program_name": "Cached Program", "agency": "USDA"}]
        row = _make_cache_row(cached, age_days=0)

        with patch("modules.programs.db") as mock_db:
            mock_db.get_program_cache.return_value = row

            from modules.programs import research_farm_programs
            result = research_farm_programs("TX", "Dairy", "", False)

        self.assertNotIn("state-programs", result["sources_queried"])


# ---------------------------------------------------------------------------
# 10. TestGrantsGovKeywordBroadened
# ---------------------------------------------------------------------------

class TestGrantsGovKeywordBroadened(unittest.TestCase):
    """Grants.gov POST body keyword contains conservation, loan, and habitat."""

    def test_keyword_contains_broadened_terms(self):
        try:
            import requests as req_module
        except ImportError:
            self.skipTest("requests not installed")

        captured = {}

        def fake_post(url, json=None, timeout=None, **kwargs):
            captured["json"] = json
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            resp.json.return_value = {"data": {"oppHits": []}}
            return resp

        with patch("modules.api_clients.requests") as mock_requests:
            mock_requests.post.side_effect = fake_post

            from modules.api_clients import fetch_grants_gov
            fetch_grants_gov("KY", "Dairy")

        keyword = captured["json"]["keyword"]
        self.assertIn("conservation", keyword)
        self.assertIn("loan", keyword)
        self.assertIn("habitat", keyword)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
