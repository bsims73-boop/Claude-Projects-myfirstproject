import json
import logging
import re
import config

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)

PER_PAGE = 25


def _clean_farm_type(farm_type):
    """Strip parenthetical content from farm type labels for cleaner API keywords.
    e.g. 'Row Crops (corn, soybeans, wheat, etc.)' -> 'Row Crops'
    """
    return re.sub(r'\s*\(.*?\)', '', farm_type).strip()


def fetch_grants_gov(state, farm_type, page=1, per_page=PER_PAGE):
    """Fetch from Grants.gov search API. No API key required."""
    if requests is None:
        return []
    try:
        resp = requests.post(
            "https://api.grants.gov/v1/api/search2",
            json={
                "keyword": f"{_clean_farm_type(farm_type)} agriculture conservation loan habitat",
                "oppStatuses": "posted|forecasted",
                "agencies": "USDA",
                "rows": per_page,
                "startRecordNum": (page - 1) * per_page,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        # Actual field names confirmed via live test: data.oppHits list,
        # fields: id, title, agency, closeDate (no synopsis in search results)
        opportunities = data.get("data", {}).get("oppHits", [])
        result = []
        for opp in opportunities:
            result.append({
                "title": opp.get("title"),
                "opportunity_id": opp.get("id"),
                "opportunity_number": opp.get("number"),
                "agency": opp.get("agency"),
                "synopsis": None,  # not returned by search2 endpoint
                "close_date": opp.get("closeDate"),
                "award_ceiling": None,  # not returned by search2 endpoint
                "source": "grants.gov",
            })
        return result
    except Exception as e:
        logger.warning("Grants.gov fetch failed: %s", e)
        return []


def fetch_sam_gov(state, farm_type, page=1, per_page=PER_PAGE):
    """Fetch from SAM.gov Assistance Listings. Skipped if key not configured."""
    if not config.SAM_GOV_API_KEY or requests is None:
        return []
    try:
        resp = requests.get(
            "https://api.sam.gov/assistance-listings/v1/search",
            params={
                "api_key": config.SAM_GOV_API_KEY,
                "keyword": f"{_clean_farm_type(farm_type)} agriculture",
                "status": "Active",
                "pageSize": per_page,
                "pageNumber": page,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        listings = data.get("assistanceListingsData", [])
        _USDA_TERMS = {"usda", "agriculture", "fsa", "nrcs", "rural development",
                       "aphis", "ams", "rma", "fns", "farm service", "natural resources"}
        result = []
        for listing in listings:
            agency = ((listing.get("federalOrganization") or {}).get("agency") or "").lower()
            title = (listing.get("title") or "").lower()
            objective = ((listing.get("overview") or {}).get("objective") or "").lower()
            combined = f"{agency} {title} {objective}"
            if not any(term in combined for term in _USDA_TERMS):
                continue
            result.append({
                "title": listing.get("title"),
                "assistance_listing_id": listing.get("assistanceListingId"),
                "agency": (listing.get("federalOrganization") or {}).get("agency"),
                "objective": (listing.get("overview") or {}).get("objective"),
                "status": listing.get("status"),
                "source": "sam.gov",
            })
        return result
    except Exception as e:
        logger.warning("SAM.gov fetch failed: %s", e)
        return []


def fetch_simpler_grants(state, farm_type, page=1, per_page=PER_PAGE):
    """Fetch from Simpler.Grants.gov. Skipped if key not configured."""
    if not config.SIMPLER_GRANTS_API_KEY or requests is None:
        return []
    try:
        resp = requests.post(
            "https://api.simpler.grants.gov/v1/opportunities/search",
            json={
                "query": f"{_clean_farm_type(farm_type)} agriculture",
                "pagination": {
                    "page_offset": page,
                    "page_size": per_page,
                },
            },
            headers={"X-Api-Key": config.SIMPLER_GRANTS_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        opportunities = data.get("data", data.get("opportunities", []))
        result = []
        for opp in opportunities:
            summary = opp.get("summary") or {}
            result.append({
                "title": opp.get("opportunity_title") or opp.get("title"),
                "opportunity_id": opp.get("opportunity_id") or opp.get("id"),
                "agency": opp.get("agency_name") or opp.get("agency"),
                "synopsis": summary.get("summary_description") or opp.get("description"),
                "close_date": opp.get("close_date"),
                "source": "simpler.grants.gov",
            })
        return result
    except Exception as e:
        logger.warning("Simpler.Grants.gov fetch failed: %s", e)
        return []


def deduplicate(programs):
    """Deduplicate program list by stable ID then by name+agency. Max 75 returned."""
    SOURCE_PRIORITY = {"grants.gov": 0, "sam.gov": 1, "simpler.grants.gov": 2}
    seen_ids = {}    # stable_id -> index in result
    seen_names = {}  # name_key  -> index in result
    result = []

    for program in programs:
        stable_id = program.get("assistance_listing_id") or program.get("opportunity_id")
        if stable_id is not None:
            stable_id = str(stable_id)

        if stable_id and stable_id in seen_ids:
            idx = seen_ids[stable_id]
            existing = result[idx]
            if _is_better(program, existing, SOURCE_PRIORITY):
                result[idx] = program
            continue

        name_key = (
            (program.get("title") or "").lower().strip()
            + "|"
            + (program.get("agency") or "").lower().strip()
        )

        if name_key in seen_names:
            idx = seen_names[name_key]
            existing = result[idx]
            if _is_better(program, existing, SOURCE_PRIORITY):
                result[idx] = program
            continue

        idx = len(result)
        result.append(program)
        if stable_id:
            seen_ids[stable_id] = idx
        seen_names[name_key] = idx

    return result[:75]


def _is_better(candidate, existing, priority):
    """Return True if candidate should replace existing."""
    cand_score = sum(1 for v in candidate.values() if v is not None)
    exist_score = sum(1 for v in existing.values() if v is not None)
    if cand_score != exist_score:
        return cand_score > exist_score
    return priority.get(candidate.get("source"), 99) < priority.get(existing.get("source"), 99)
