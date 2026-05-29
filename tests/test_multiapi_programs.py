"""
Acceptance tests for the multi-API farm programs feature.
Criteria 1-12: unit/integration tests for modules/api_clients.py and modules/programs.py.
Criteria 13: Flask route tests via test client.
Criteria 14-15: static file content checks.
"""

import json
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch, call

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import config  # noqa: E402 – must come after sys.path fixup


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(json_data, status_code=200):
    """Build a minimal mock that mimics requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


def _make_claude_response(text):
    """Build a minimal mock for an Anthropic messages.create response."""
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    return response


def _make_programs(n, source="grants.gov", id_field="opportunity_id", prefix="opp"):
    """Return a list of n minimal program dicts."""
    result = []
    for i in range(n):
        result.append({
            "title": f"Program {i}",
            id_field: f"{prefix}{i}",
            "agency": "USDA",
            "source": source,
            "synopsis": None,
            "close_date": None,
            "award_ceiling": None,
            "opportunity_number": None,
        })
    return result


# ---------------------------------------------------------------------------
# Criterion 1 – Grants.gov always queried (no key required)
# ---------------------------------------------------------------------------

class TestGrantsGovAlwaysQueried(unittest.TestCase):
    """Criterion 1: fetch_grants_gov is called on every search regardless of keys."""

    def test_fetch_grants_gov_called_when_no_other_keys_set(self):
        """grants.gov is fetched even when SAM and Simpler keys are absent."""
        from modules import api_clients

        # Ensure neither optional key is set
        with patch.object(config, "SAM_GOV_API_KEY", ""), \
             patch.object(config, "SIMPLER_GRANTS_API_KEY", ""), \
             patch("modules.api_clients.requests") as mock_req, \
             patch("modules.programs.get_client") as mock_get_client:

            # Grants.gov POST returns empty hit list
            mock_req.post.return_value = _mock_response({"data": {"oppHits": []}})
            mock_req.get.return_value = _mock_response({})  # SAM / Simpler never reached

            # Claude mock for fallback path
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response("[]")
            mock_get_client.return_value = mock_client

            from modules.programs import research_farm_programs
            research_farm_programs("Iowa", "Dairy")

        # requests.post must have been called (grants.gov uses POST)
        mock_req.post.assert_called_once()
        call_args = mock_req.post.call_args
        self.assertIn("grants.gov", call_args[0][0])

    def test_fetch_grants_gov_returns_list(self):
        """fetch_grants_gov returns a list even on empty results."""
        from modules import api_clients

        with patch("modules.api_clients.requests") as mock_req:
            mock_req.post.return_value = _mock_response({"data": {"oppHits": []}})
            result = api_clients.fetch_grants_gov("Iowa", "Dairy")

        self.assertIsInstance(result, list)
        mock_req.post.assert_called_once()


# ---------------------------------------------------------------------------
# Criterion 2 – SAM.gov skipped when key absent
# ---------------------------------------------------------------------------

class TestSamGovSkippedWhenKeyAbsent(unittest.TestCase):
    """Criterion 2: fetch_sam_gov returns [] immediately when SAM_GOV_API_KEY is empty."""

    def test_returns_empty_list_when_key_missing(self):
        from modules import api_clients

        with patch.object(config, "SAM_GOV_API_KEY", ""), \
             patch("modules.api_clients.requests") as mock_req:
            result = api_clients.fetch_sam_gov("Iowa", "Dairy")

        self.assertEqual(result, [])
        mock_req.get.assert_not_called()

    def test_makes_request_when_key_present(self):
        from modules import api_clients

        with patch.object(config, "SAM_GOV_API_KEY", "test_key"), \
             patch("modules.api_clients.requests") as mock_req:
            mock_req.get.return_value = _mock_response({"assistanceListingsData": []})
            result = api_clients.fetch_sam_gov("Iowa", "Dairy")

        mock_req.get.assert_called_once()
        self.assertIsInstance(result, list)


# ---------------------------------------------------------------------------
# Criterion 3 – Simpler.Grants.gov skipped when key absent
# ---------------------------------------------------------------------------

class TestSimplerGrantsSkippedWhenKeyAbsent(unittest.TestCase):
    """Criterion 3: fetch_simpler_grants returns [] immediately when key is empty."""

    def test_returns_empty_list_when_key_missing(self):
        from modules import api_clients

        with patch.object(config, "SIMPLER_GRANTS_API_KEY", ""), \
             patch("modules.api_clients.requests") as mock_req:
            result = api_clients.fetch_simpler_grants("Iowa", "Dairy")

        self.assertEqual(result, [])
        mock_req.get.assert_not_called()

    def test_makes_request_when_key_present(self):
        from modules import api_clients

        with patch.object(config, "SIMPLER_GRANTS_API_KEY", "test_key"), \
             patch("modules.api_clients.requests") as mock_req:
            mock_req.post.return_value = _mock_response({"data": []})
            result = api_clients.fetch_simpler_grants("Iowa", "Dairy")

        mock_req.post.assert_called_once()
        self.assertIsInstance(result, list)


# ---------------------------------------------------------------------------
# Criterion 4 – Parallel fetch via ThreadPoolExecutor
# ---------------------------------------------------------------------------

class TestParallelFetch(unittest.TestCase):
    """Criterion 4: all three sources are submitted concurrently."""

    def test_all_three_fetches_submitted(self):
        """All three api_clients fetch functions are called in every search."""
        with patch("modules.api_clients.fetch_grants_gov", return_value=[]) as mock_grants, \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]) as mock_sam, \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]) as mock_simpler, \
             patch("modules.programs.get_client") as mock_get_client:

            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response("[]")
            mock_get_client.return_value = mock_client

            from modules.programs import research_farm_programs
            research_farm_programs("Iowa", "Dairy")

        mock_grants.assert_called_once()
        mock_sam.assert_called_once()
        mock_simpler.assert_called_once()

    def test_threadpoolexecutor_used(self):
        """ThreadPoolExecutor.submit is used (parallel submission)."""
        submitted_fns = []

        class FakeExecutor:
            def __init__(self, max_workers=None):
                self._futures = []

            def submit(self, fn, *args, **kwargs):
                submitted_fns.append(fn.__name__)
                f = MagicMock()
                f.result.return_value = []
                return f

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        with patch("modules.programs.concurrent.futures.ThreadPoolExecutor", FakeExecutor), \
             patch("modules.programs.get_client") as mock_get_client:

            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response("[]")
            mock_get_client.return_value = mock_client

            from modules.programs import research_farm_programs
            research_farm_programs("Iowa", "Dairy")

        self.assertIn("fetch_grants_gov", submitted_fns)
        self.assertIn("fetch_sam_gov", submitted_fns)
        self.assertIn("fetch_simpler_grants", submitted_fns)


# ---------------------------------------------------------------------------
# Criterion 5 – Deduplication by stable ID
# ---------------------------------------------------------------------------

class TestDeduplicationByStableId(unittest.TestCase):
    """Criterion 5: two records with same opportunity_id collapse to one richer record."""

    def test_same_opportunity_id_deduped(self):
        from modules.api_clients import deduplicate

        records = [
            {
                "title": "Program A",
                "opportunity_id": "42",
                "agency": "FSA",
                "synopsis": None,
                "source": "grants.gov",
            },
            {
                "title": "Program A",
                "opportunity_id": "42",
                "agency": "FSA",
                "synopsis": "A richer description",
                "close_date": "2026-12-31",
                "source": "simpler.grants.gov",
            },
        ]
        result = deduplicate(records)
        self.assertEqual(len(result), 1)

    def test_richer_record_kept_by_stable_id(self):
        from modules.api_clients import deduplicate

        sparse = {
            "title": "Program A",
            "opportunity_id": "42",
            "agency": None,
            "synopsis": None,
            "source": "grants.gov",
        }
        rich = {
            "title": "Program A",
            "opportunity_id": "42",
            "agency": "USDA-FSA",
            "synopsis": "Details here",
            "close_date": "2026-06-30",
            "source": "simpler.grants.gov",
        }
        result = deduplicate([sparse, rich])
        self.assertEqual(len(result), 1)
        # The rich record has more non-None values
        self.assertEqual(result[0]["synopsis"], "Details here")

    def test_different_ids_not_deduped(self):
        from modules.api_clients import deduplicate

        records = [
            {"title": "Program A", "opportunity_id": "1", "agency": "FSA", "source": "grants.gov"},
            {"title": "Program B", "opportunity_id": "2", "agency": "FSA", "source": "grants.gov"},
        ]
        result = deduplicate(records)
        self.assertEqual(len(result), 2)


# ---------------------------------------------------------------------------
# Criterion 6 – Deduplication by name+agency (case-insensitive)
# ---------------------------------------------------------------------------

class TestDeduplicationByNameAgency(unittest.TestCase):
    """Criterion 6: records with same title+agency (case-insensitive) collapse to one."""

    def test_same_name_agency_deduped(self):
        from modules.api_clients import deduplicate

        records = [
            {"title": "Farm Loan Program", "agency": "USDA FSA", "source": "grants.gov"},
            {"title": "FARM LOAN PROGRAM", "agency": "usda fsa", "source": "sam.gov"},
        ]
        result = deduplicate(records)
        self.assertEqual(len(result), 1)

    def test_different_name_agency_not_deduped(self):
        from modules.api_clients import deduplicate

        records = [
            {"title": "Farm Loan Program", "agency": "USDA FSA", "source": "grants.gov"},
            {"title": "Farm Storage Program", "agency": "USDA FSA", "source": "grants.gov"},
        ]
        result = deduplicate(records)
        self.assertEqual(len(result), 2)

    def test_same_name_different_agency_not_deduped(self):
        from modules.api_clients import deduplicate

        records = [
            {"title": "Farm Program", "agency": "USDA FSA", "source": "grants.gov"},
            {"title": "Farm Program", "agency": "USDA NRCS", "source": "grants.gov"},
        ]
        result = deduplicate(records)
        self.assertEqual(len(result), 2)


# ---------------------------------------------------------------------------
# Criterion 7 – 75-record cap
# ---------------------------------------------------------------------------

class TestDeduplicationCap(unittest.TestCase):
    """Criterion 7: deduplicate returns at most 75 records."""

    def test_cap_at_75(self):
        from modules.api_clients import deduplicate

        programs = _make_programs(100)
        result = deduplicate(programs)
        self.assertLessEqual(len(result), 75)

    def test_exactly_75_when_100_unique_given(self):
        from modules.api_clients import deduplicate

        programs = _make_programs(100)
        result = deduplicate(programs)
        self.assertEqual(len(result), 75)

    def test_fewer_than_75_returned_when_fewer_given(self):
        from modules.api_clients import deduplicate

        programs = _make_programs(10)
        result = deduplicate(programs)
        self.assertEqual(len(result), 10)


# ---------------------------------------------------------------------------
# Criterion 8 – has_more logic
# ---------------------------------------------------------------------------

class TestHasMoreLogic(unittest.TestCase):
    """Criterion 8: has_more is True when any source returns exactly 25; False otherwise."""

    def _run_with_results(self, grants_n, sam_n, simpler_n):
        """Helper: mock the three fetchers and return the result dict."""
        with patch("modules.api_clients.fetch_grants_gov",
                   return_value=_make_programs(grants_n, source="grants.gov")) as _g, \
             patch("modules.api_clients.fetch_sam_gov",
                   return_value=_make_programs(sam_n, source="sam.gov",
                                               id_field="assistance_listing_id",
                                               prefix="sam")) as _s, \
             patch("modules.api_clients.fetch_simpler_grants",
                   return_value=_make_programs(simpler_n, source="simpler.grants.gov",
                                               prefix="sg")) as _sg, \
             patch("modules.programs.get_client") as mock_get_client:

            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(
                json.dumps([{"program_name": "X", "agency": "Y", "level": "federal",
                             "description": "d", "eligibility": "e", "how_to_apply": "h",
                             "documents_needed": [], "website": None, "deadline": None}])
            )
            mock_get_client.return_value = mock_client

            from modules.programs import research_farm_programs
            # Reload to pick up patched fetchers cleanly
            return research_farm_programs("Iowa", "Dairy")

    def test_has_more_true_when_grants_returns_25(self):
        result = self._run_with_results(25, 0, 0)
        self.assertTrue(result["has_more"])

    def test_has_more_true_when_sam_returns_25(self):
        result = self._run_with_results(0, 25, 0)
        self.assertTrue(result["has_more"])

    def test_has_more_true_when_simpler_returns_25(self):
        result = self._run_with_results(0, 0, 25)
        self.assertTrue(result["has_more"])

    def test_has_more_false_when_all_return_less_than_25(self):
        result = self._run_with_results(5, 3, 7)
        self.assertFalse(result["has_more"])

    def test_has_more_false_when_all_return_zero(self):
        # When all return 0, fallback Claude path runs; has_more must be False
        result = self._run_with_results(0, 0, 0)
        self.assertFalse(result["has_more"])


# ---------------------------------------------------------------------------
# Criterion 9 – Fallback to Claude when APIs return nothing
# ---------------------------------------------------------------------------

class TestFallbackToClaude(unittest.TestCase):
    """Criterion 9: when raw_deduped is empty, Claude is called with training-data prompt."""

    def test_fallback_uses_agricultural_policy_expert_system_prompt(self):
        with patch("modules.api_clients.fetch_grants_gov", return_value=[]), \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]), \
             patch("modules.programs.get_client") as mock_get_client:

            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response("[]")
            mock_get_client.return_value = mock_client

            from modules.programs import research_farm_programs
            research_farm_programs("Iowa", "Dairy")

        mock_client.messages.create.assert_called_once()
        kwargs = mock_client.messages.create.call_args.kwargs
        self.assertIn("agricultural policy expert", kwargs.get("system", ""))

    def test_fallback_returns_programs_list(self):
        programs_data = [{"program_name": "Test Program", "agency": "USDA",
                          "level": "federal", "description": "desc",
                          "eligibility": "all", "how_to_apply": "apply",
                          "documents_needed": [], "website": None, "deadline": None}]

        with patch("modules.api_clients.fetch_grants_gov", return_value=[]), \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]), \
             patch("modules.programs.get_client") as mock_get_client:

            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(
                json.dumps(programs_data)
            )
            mock_get_client.return_value = mock_client

            from modules.programs import research_farm_programs
            result = research_farm_programs("Iowa", "Dairy")

        self.assertIsInstance(result["programs"], list)
        self.assertEqual(len(result["programs"]), 1)
        self.assertEqual(result["programs"][0]["program_name"], "Test Program")


# ---------------------------------------------------------------------------
# Criterion 10 – Enrichment path when APIs return data
# ---------------------------------------------------------------------------

class TestEnrichmentPath(unittest.TestCase):
    """Criterion 10: when raw_deduped is non-empty, Claude is called with enrichment prompt."""

    def _api_programs(self, n=3):
        return _make_programs(n, source="grants.gov")

    def test_enrichment_uses_agricultural_program_specialist_system_prompt(self):
        raw = self._api_programs(3)

        with patch("modules.api_clients.fetch_grants_gov", return_value=raw), \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]), \
             patch("modules.programs.get_client") as mock_get_client:

            enriched = [{"program_name": f"Program {i}", "agency": "USDA",
                         "level": "federal", "description": "desc",
                         "eligibility": "all", "how_to_apply": "apply",
                         "documents_needed": [], "website": None, "deadline": None}
                        for i in range(3)]

            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(
                json.dumps(enriched)
            )
            mock_get_client.return_value = mock_client

            from modules.programs import research_farm_programs
            research_farm_programs("Iowa", "Dairy")

        mock_client.messages.create.assert_called_once()
        kwargs = mock_client.messages.create.call_args.kwargs
        self.assertIn("agricultural program specialist", kwargs.get("system", ""))

    def test_enrichment_prompt_contains_raw_data(self):
        raw = self._api_programs(2)

        with patch("modules.api_clients.fetch_grants_gov", return_value=raw), \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]), \
             patch("modules.programs.get_client") as mock_get_client:

            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response("[]")
            mock_get_client.return_value = mock_client

            from modules.programs import research_farm_programs
            research_farm_programs("Iowa", "Dairy")

        kwargs = mock_client.messages.create.call_args.kwargs
        messages = kwargs.get("messages", [])
        user_content = messages[0]["content"] if messages else ""
        # The enrichment prompt embeds the raw JSON in the user message
        self.assertIn("Program 0", user_content)


# ---------------------------------------------------------------------------
# Criterion 11 – Return shape
# ---------------------------------------------------------------------------

class TestReturnShape(unittest.TestCase):
    """Criterion 11: research_farm_programs always returns dict with required keys."""

    REQUIRED_KEYS = {"programs", "has_more", "page", "sources_queried"}

    def _call(self, grants=None, sam=None, simpler=None, claude_text="[]"):
        with patch("modules.api_clients.fetch_grants_gov", return_value=grants or []), \
             patch("modules.api_clients.fetch_sam_gov", return_value=sam or []), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=simpler or []), \
             patch("modules.programs.get_client") as mock_get_client:

            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(claude_text)
            mock_get_client.return_value = mock_client

            from modules.programs import research_farm_programs
            return research_farm_programs("Iowa", "Dairy", page=2)

    def test_fallback_path_return_shape(self):
        result = self._call()
        self.assertIsInstance(result, dict)
        for key in self.REQUIRED_KEYS:
            self.assertIn(key, result, f"Missing key: {key}")
        self.assertIsInstance(result["programs"], list)
        self.assertIsInstance(result["has_more"], bool)
        self.assertIsInstance(result["page"], int)
        self.assertIsInstance(result["sources_queried"], list)

    def test_enrichment_path_return_shape(self):
        enriched = [{"program_name": "P", "agency": "A", "level": "federal",
                     "description": "d", "eligibility": "e", "how_to_apply": "h",
                     "documents_needed": [], "website": None, "deadline": None}]
        result = self._call(
            grants=_make_programs(3),
            claude_text=json.dumps(enriched),
        )
        self.assertIsInstance(result, dict)
        for key in self.REQUIRED_KEYS:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_page_is_passed_through(self):
        result = self._call()
        self.assertEqual(result["page"], 2)

    def test_sources_queried_always_includes_grants_gov(self):
        result = self._call()
        self.assertIn("grants.gov", result["sources_queried"])

    def test_sources_queried_includes_sam_when_key_set(self):
        with patch.object(config, "SAM_GOV_API_KEY", "key123"), \
             patch.object(config, "SIMPLER_GRANTS_API_KEY", ""):
            result = self._call()
        self.assertIn("sam.gov", result["sources_queried"])

    def test_sources_queried_excludes_sam_when_key_absent(self):
        with patch.object(config, "SAM_GOV_API_KEY", ""), \
             patch.object(config, "SIMPLER_GRANTS_API_KEY", ""):
            result = self._call()
        self.assertNotIn("sam.gov", result["sources_queried"])


# ---------------------------------------------------------------------------
# Criterion 12 – Error card wrapped correctly
# ---------------------------------------------------------------------------

class TestErrorCardWrapping(unittest.TestCase):
    """Criterion 12: on exception, the result is a dict (not a bare list/card)."""

    def _call_with_error(self, exc):
        with patch("modules.api_clients.fetch_grants_gov", side_effect=exc), \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]):
            from modules.programs import research_farm_programs
            return research_farm_programs("Iowa", "Dairy")

    def test_exception_returns_dict_not_bare_list(self):
        result = self._call_with_error(RuntimeError("network failure"))
        self.assertIsInstance(result, dict)

    def test_exception_result_has_programs_key(self):
        result = self._call_with_error(RuntimeError("network failure"))
        self.assertIn("programs", result)

    def test_exception_result_has_has_more_key(self):
        result = self._call_with_error(RuntimeError("network failure"))
        self.assertIn("has_more", result)

    def test_exception_programs_is_list(self):
        result = self._call_with_error(RuntimeError("network failure"))
        self.assertIsInstance(result["programs"], list)

    def test_exception_programs_contains_error_card(self):
        result = self._call_with_error(RuntimeError("boom"))
        cards = result["programs"]
        self.assertGreater(len(cards), 0)
        self.assertEqual(cards[0]["program_name"], "Error Retrieving Programs")
        self.assertIn("boom", cards[0]["description"])

    def test_rate_limit_error_wrapped_in_dict(self):
        import anthropic
        result = self._call_with_error(
            anthropic.RateLimitError(
                message="rate limited",
                response=MagicMock(status_code=429, headers={}),
                body={},
            )
        )
        self.assertIsInstance(result, dict)
        self.assertIn("programs", result)

    def test_json_decode_error_wrapped_in_dict(self):
        """JSONDecodeError from Claude response is also wrapped correctly."""
        with patch("modules.api_clients.fetch_grants_gov", return_value=[]), \
             patch("modules.api_clients.fetch_sam_gov", return_value=[]), \
             patch("modules.api_clients.fetch_simpler_grants", return_value=[]), \
             patch("modules.programs.get_client") as mock_get_client:

            mock_client = MagicMock()
            # Return bad JSON to trigger JSONDecodeError
            mock_client.messages.create.return_value = _make_claude_response(
                "this is not valid json {"
            )
            mock_get_client.return_value = mock_client

            from modules.programs import research_farm_programs
            result = research_farm_programs("Iowa", "Dairy")

        self.assertIsInstance(result, dict)
        self.assertIn("programs", result)


# ---------------------------------------------------------------------------
# Criterion 13 – POST /api/programs accepts page param
# ---------------------------------------------------------------------------

class TestFlaskProgramsRoute(unittest.TestCase):
    """Criterion 13: Flask route extracts page from body, defaults to 1."""

    def setUp(self):
        import app as flask_app
        flask_app.app.config["TESTING"] = True
        self.client = flask_app.app.test_client()

    def test_page_defaults_to_1(self):
        with patch("modules.programs.research_farm_programs") as mock_fn:
            mock_fn.return_value = {
                "programs": [], "has_more": False, "page": 1, "sources_queried": []
            }
            resp = self.client.post(
                "/api/programs",
                json={"state": "Iowa", "farm_type": "Dairy"},
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)
        args = mock_fn.call_args.args
        # page is the 4th positional arg: (state, farm_type, county, page)
        self.assertEqual(args[3], 1)

    def test_page_extracted_from_body(self):
        with patch("modules.programs.research_farm_programs") as mock_fn:
            mock_fn.return_value = {
                "programs": [], "has_more": False, "page": 3, "sources_queried": []
            }
            resp = self.client.post(
                "/api/programs",
                json={"state": "Iowa", "farm_type": "Dairy", "page": 3},
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)
        args = mock_fn.call_args.args
        self.assertEqual(args[3], 3)

    def test_response_contains_programs_key(self):
        with patch("modules.programs.research_farm_programs") as mock_fn:
            mock_fn.return_value = {
                "programs": [], "has_more": False, "page": 1, "sources_queried": ["grants.gov"]
            }
            resp = self.client.post(
                "/api/programs",
                json={"state": "Iowa", "farm_type": "Dairy"},
                content_type="application/json",
            )
        data = resp.get_json()
        self.assertIn("programs", data)
        self.assertIn("has_more", data)
        self.assertIn("page", data)
        self.assertIn("sources_queried", data)

    def test_missing_state_returns_400(self):
        resp = self.client.post(
            "/api/programs",
            json={"farm_type": "Dairy"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_missing_farm_type_returns_400(self):
        resp = self.client.post(
            "/api/programs",
            json={"state": "Iowa"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# Criterion 14 – Load More button present in HTML
# ---------------------------------------------------------------------------

class TestLoadMoreButtonInHtml(unittest.TestCase):
    """Criterion 14: programs.html contains #loadMoreBtn."""

    def _read_template(self):
        base = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(base, "templates", "programs.html")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_load_more_btn_id_present(self):
        html = self._read_template()
        self.assertIn("loadMoreBtn", html)

    def test_load_more_btn_is_button_element(self):
        html = self._read_template()
        self.assertIn('id="loadMoreBtn"', html)

    def test_load_more_onclick_calls_load_more(self):
        html = self._read_template()
        self.assertIn("loadMorePrograms", html)


# ---------------------------------------------------------------------------
# Criterion 15 – programs.js sends page in request body
# ---------------------------------------------------------------------------

class TestProgramsJsSendsPage(unittest.TestCase):
    """Criterion 15: programs.js fetch body includes page field."""

    def _read_js(self):
        base = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(base, "static", "js", "programs.js")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_page_field_in_fetch_body(self):
        js = self._read_js()
        self.assertIn("page", js)

    def test_page_1_sent_on_initial_search(self):
        js = self._read_js()
        # Initial search sends page: 1
        self.assertIn("page: 1", js)

    def test_current_page_sent_on_load_more(self):
        js = self._read_js()
        # loadMorePrograms uses currentPage
        self.assertIn("page: currentPage", js)

    def test_fetch_uses_post_method(self):
        js = self._read_js()
        self.assertIn("method: 'POST'", js)

    def test_fetch_targets_api_programs(self):
        js = self._read_js()
        self.assertIn("/api/programs", js)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
