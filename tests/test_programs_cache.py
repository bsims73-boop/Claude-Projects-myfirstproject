"""
Unit tests for the Programs Page Caching feature.
Criteria 1-11: cache hit/miss/expiry, incremental enrichment, force_refresh, Flask route wiring.
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
# Helpers
# ---------------------------------------------------------------------------

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
# Criterion 1 — Cache hit returns cached data without API calls
# ---------------------------------------------------------------------------

class TestCacheHit(unittest.TestCase):
    """Cache hit (age < 30 days) returns stored data without calling any API or Claude."""

    def test_cache_hit_returns_cached_programs(self):
        cached = [{"program_name": "Cached Program", "agency": "USDA"}]
        row = _make_cache_row(cached, age_days=0)

        with patch("modules.programs.db") as mock_db, \
             patch("modules.api_clients.fetch_grants_gov") as mock_grants, \
             patch("modules.api_clients.fetch_sam_gov") as mock_sam, \
             patch("modules.api_clients.fetch_simpler_grants") as mock_simpler, \
             patch("modules.programs.get_client") as mock_get_client:

            mock_db.get_program_cache.return_value = row

            from modules.programs import research_farm_programs
            result = research_farm_programs("Iowa", "Dairy", "", False)

        mock_grants.assert_not_called()
        mock_sam.assert_not_called()
        mock_simpler.assert_not_called()
        mock_get_client.assert_not_called()
        self.assertEqual(result["programs"], cached)
        self.assertEqual(result["cached_at"], row["updated_at"])


# ---------------------------------------------------------------------------
# Criterion 2 — Cache miss triggers live fetch and saves to cache
# ---------------------------------------------------------------------------

class TestCacheMiss(unittest.TestCase):
    """Cache miss: live fetch runs, Claude enriches, result saved to cache."""

    def test_cache_miss_triggers_fetch_and_upsert(self):
        raw = _make_programs(3)
        enriched = [{"program_name": f"Enriched {i}", "agency": "USDA"} for i in range(3)]

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
            result = research_farm_programs("Iowa", "Dairy", "", False)

        mock_db.upsert_program_cache.assert_called_once()
        self.assertEqual(result["programs"], enriched)


# ---------------------------------------------------------------------------
# Criterion 3 — Expired cache (>30 days) triggers fresh fetch
# ---------------------------------------------------------------------------

class TestExpiredCache(unittest.TestCase):
    """Cache row older than 30 days is treated as expired; live fetch runs."""

    def test_expired_cache_triggers_live_fetch(self):
        old_cached = [{"program_name": "Old Program"}]
        row = _make_cache_row(old_cached, age_days=31)
        raw = _make_programs(2)
        enriched = [{"program_name": "Fresh Program", "agency": "USDA"}]

        with patch("modules.programs.db") as mock_db, \
             patch("modules.api_clients.fetch_grants_gov", return_value=raw), \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]), \
             patch("modules.programs.get_client") as mock_get_client:

            # First call (cache check) returns expired row; second call (incremental) returns same
            mock_db.get_program_cache.return_value = row
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(json.dumps(enriched))
            mock_get_client.return_value = mock_client

            from modules.programs import research_farm_programs
            result = research_farm_programs("Iowa", "Dairy", "", False)

        mock_db.upsert_program_cache.assert_called_once()


# ---------------------------------------------------------------------------
# Criterion 4 — force_refresh=True bypasses valid cache
# ---------------------------------------------------------------------------

class TestForceRefresh(unittest.TestCase):
    """force_refresh=True skips cache read and goes straight to live fetch."""

    def test_force_refresh_bypasses_valid_cache(self):
        cached = [{"program_name": "Cached"}]
        row = _make_cache_row(cached, age_days=0)
        raw = _make_programs(2)
        enriched = [{"program_name": "Fresh", "agency": "USDA"}]

        with patch("modules.programs.db") as mock_db, \
             patch("modules.api_clients.fetch_grants_gov", return_value=raw) as mock_grants, \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]), \
             patch("modules.programs.get_client") as mock_get_client:

            mock_db.get_program_cache.return_value = row
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(json.dumps(enriched))
            mock_get_client.return_value = mock_client

            from modules.programs import research_farm_programs
            result = research_farm_programs("Iowa", "Dairy", "", True)

        mock_grants.assert_called_once()


# ---------------------------------------------------------------------------
# Criterion 5 — Incremental enrichment: only new IDs sent to Claude
# ---------------------------------------------------------------------------

class TestIncrementalEnrichment(unittest.TestCase):
    """Only programs with IDs not in seen_ids are sent to Claude."""

    def test_only_new_ids_sent_to_claude(self):
        cached_programs = [
            {"program_name": "Prog 0", "agency": "USDA"},
            {"program_name": "Prog 1", "agency": "USDA"},
        ]
        row = _make_cache_row(cached_programs, seen_ids=["opp0", "opp1"], age_days=0)

        # API returns opp0, opp1 (already seen) plus opp2 (new)
        raw = _make_programs(3)  # opp0, opp1, opp2

        new_enriched = [{"program_name": "Prog 2 enriched", "agency": "USDA"}]

        with patch("modules.programs.db") as mock_db, \
             patch("modules.api_clients.fetch_grants_gov", return_value=raw), \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]), \
             patch("modules.programs.get_client") as mock_get_client:

            # First call returns None (force_refresh bypasses), second call for incremental check
            mock_db.get_program_cache.return_value = row
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(json.dumps(new_enriched))
            mock_get_client.return_value = mock_client

            from modules.programs import research_farm_programs
            result = research_farm_programs("Iowa", "Dairy", "", True)

        # Claude should be called with only opp2's data
        call_kwargs = mock_client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        self.assertIn("opp2", user_content)
        self.assertNotIn("opp0", user_content)
        self.assertNotIn("opp1", user_content)

        # Result should be 2 cached + 1 newly enriched = 3 total
        self.assertEqual(len(result["programs"]), 3)
        self.assertEqual(result["programs"][0]["program_name"], "Prog 0")
        self.assertEqual(result["programs"][1]["program_name"], "Prog 1")
        self.assertEqual(result["programs"][2]["program_name"], "Prog 2 enriched")


# ---------------------------------------------------------------------------
# Criterion 6 — No Claude call when no new IDs; timestamp still updates
# ---------------------------------------------------------------------------

class TestNoNewIds(unittest.TestCase):
    """When all API results are already in seen_ids, Claude is not called."""

    def test_no_claude_call_when_no_new_ids(self):
        cached_programs = [{"program_name": "Prog 0"}, {"program_name": "Prog 1"}]
        row = _make_cache_row(cached_programs, seen_ids=["opp0", "opp1"], age_days=0)
        raw = _make_programs(2)  # opp0, opp1 — all already seen

        with patch("modules.programs.db") as mock_db, \
             patch("modules.api_clients.fetch_grants_gov", return_value=raw), \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]), \
             patch("modules.programs.get_client") as mock_get_client:

            mock_db.get_program_cache.return_value = row
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            from modules.programs import research_farm_programs
            result = research_farm_programs("Iowa", "Dairy", "", True)

        mock_get_client.assert_not_called()
        mock_db.update_program_cache_timestamp.assert_called_once()
        self.assertEqual(result["programs"], cached_programs)


# ---------------------------------------------------------------------------
# Criterion 7 — Empty API result not cached
# ---------------------------------------------------------------------------

class TestEmptyApiResult(unittest.TestCase):
    """When all APIs return empty, upsert_program_cache is NOT called."""

    def test_empty_api_result_not_cached(self):
        with patch("modules.programs.db") as mock_db, \
             patch("modules.api_clients.fetch_grants_gov", return_value=[]), \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]):

            mock_db.get_program_cache.return_value = None

            from modules.programs import research_farm_programs
            result = research_farm_programs("Iowa", "Dairy", "", False)

        mock_db.upsert_program_cache.assert_not_called()
        self.assertEqual(result["programs"], [])
        self.assertIsNone(result["cached_at"])


# ---------------------------------------------------------------------------
# Criterion 8 — Exception does not corrupt cache
# ---------------------------------------------------------------------------

class TestExceptionSafety(unittest.TestCase):
    """On exception, cache is not written and an error card is returned."""

    def test_exception_does_not_corrupt_cache(self):
        with patch("modules.programs.db") as mock_db, \
             patch("modules.api_clients.fetch_grants_gov", side_effect=RuntimeError("network failure")), \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]):

            mock_db.get_program_cache.return_value = None

            from modules.programs import research_farm_programs
            result = research_farm_programs("Iowa", "Dairy", "", False)

        mock_db.upsert_program_cache.assert_not_called()
        self.assertIsInstance(result["programs"], list)
        self.assertGreater(len(result["programs"]), 0)
        self.assertEqual(result["programs"][0]["program_name"], "Error Retrieving Programs")


# ---------------------------------------------------------------------------
# Criterion 9 — force_refresh param wired through Flask route
# ---------------------------------------------------------------------------

class TestFlaskForceRefreshWiring(unittest.TestCase):
    """Flask route passes force_refresh=True correctly to research_farm_programs."""

    def setUp(self):
        import app as flask_app
        flask_app.app.config["TESTING"] = True
        self.client = flask_app.app.test_client()

    def test_force_refresh_true_wired_through(self):
        with patch("modules.programs.research_farm_programs") as mock_fn:
            mock_fn.return_value = {"programs": [], "sources_queried": [], "cached_at": None}
            self.client.post(
                "/api/programs",
                json={"state": "Iowa", "farm_type": "Dairy", "force_refresh": True},
                content_type="application/json",
            )
        args = mock_fn.call_args.args
        self.assertEqual(args[3], True)


# ---------------------------------------------------------------------------
# Criterion 10 — force_refresh defaults to False in route
# ---------------------------------------------------------------------------

class TestFlaskForceRefreshDefault(unittest.TestCase):
    """Flask route defaults force_refresh to False when not in request body."""

    def setUp(self):
        import app as flask_app
        flask_app.app.config["TESTING"] = True
        self.client = flask_app.app.test_client()

    def test_force_refresh_defaults_to_false(self):
        with patch("modules.programs.research_farm_programs") as mock_fn:
            mock_fn.return_value = {"programs": [], "sources_queried": [], "cached_at": None}
            self.client.post(
                "/api/programs",
                json={"state": "Iowa", "farm_type": "Dairy"},
                content_type="application/json",
            )
        args = mock_fn.call_args.args
        self.assertEqual(args[3], False)


# ---------------------------------------------------------------------------
# Criterion 11 — Response includes cached_at, excludes has_more and page
# ---------------------------------------------------------------------------

class TestResponseShape(unittest.TestCase):
    """Response JSON has cached_at; has_more and page must not be present."""

    def setUp(self):
        import app as flask_app
        flask_app.app.config["TESTING"] = True
        self.client = flask_app.app.test_client()

    def test_response_has_cached_at_not_has_more_or_page(self):
        with patch("modules.programs.research_farm_programs") as mock_fn:
            mock_fn.return_value = {
                "programs": [],
                "sources_queried": [],
                "cached_at": "2026-01-01T00:00:00",
            }
            resp = self.client.post(
                "/api/programs",
                json={"state": "Iowa", "farm_type": "Dairy"},
                content_type="application/json",
            )
        data = resp.get_json()
        self.assertIn("cached_at", data)
        self.assertNotIn("has_more", data)
        self.assertNotIn("page", data)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
