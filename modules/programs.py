import json
import concurrent.futures
from datetime import datetime

import anthropic

import config
from modules.ocr import get_client, _strip_markdown
from modules import api_clients, db

_CURATED_PATH = config.BASE_DIR / "static" / "data" / "curated_state_programs.json"
try:
    _CURATED_PROGRAMS = json.loads(_CURATED_PATH.read_text(encoding="utf-8"))
except Exception:
    _CURATED_PROGRAMS = []

# Maps both full state names and abbreviations to the 2-letter code used in curated JSON
_PILOT_STATE_CODES = {
    "kentucky": "KY", "ky": "KY",
    "ohio": "OH", "oh": "OH",
    "west virginia": "WV", "wv": "WV",
}

FARM_TYPES = [
    "Row Crops (corn, soybeans, wheat, etc.)",
    "Livestock (beef cattle, hogs, sheep)",
    "Dairy",
    "Poultry (broilers, layers, turkeys)",
    "Organic",
    "Specialty Crops (fruits, vegetables, nuts)",
    "Mixed / Diversified",
]

CACHE_TTL_DAYS = 30


def _build_location(state, county):
    if not county:
        return state
    if state == "Alaska":
        return f"{county}, {state}"
    return f"{county} County, {state}"


def _stable_id(p):
    if p.get("curated_id"):
        return p["curated_id"]
    if p.get("opportunity_id"):
        return str(p["opportunity_id"])
    if p.get("assistance_listing_id"):
        return str(p["assistance_listing_id"])
    return f"{(p.get('title') or '')}|{(p.get('agency') or '')}".lower()


def research_farm_programs(state, farm_type, county="", force_refresh=False):
    per_page = 25
    location = _build_location(state, county)
    sources_queried = ["grants.gov"]
    if config.SAM_GOV_API_KEY:
        sources_queried.append("sam.gov")
    if config.SIMPLER_GRANTS_API_KEY:
        sources_queried.append("simpler.grants.gov")
    if state.lower() in _PILOT_STATE_CODES:
        sources_queried.append("state-programs")

    cache_key = f"{state}|{farm_type}|{county}".lower()

    if not force_refresh:
        row = db.get_program_cache(cache_key)
        if row:
            age_days = (datetime.now() - datetime.fromisoformat(row["updated_at"])).days
            if age_days < CACHE_TTL_DAYS:
                return {
                    "programs": json.loads(row["programs_json"]),
                    "sources_queried": sources_queried,
                    "cached_at": row["updated_at"],
                }
            # else: expired, fall through to live fetch

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            f_grants  = executor.submit(api_clients.fetch_grants_gov,     state, farm_type, 1, per_page)
            f_sam     = executor.submit(api_clients.fetch_sam_gov,        state, farm_type, 1, per_page)
            f_simpler = executor.submit(api_clients.fetch_simpler_grants, state, farm_type, 1, per_page)
        grants_results  = f_grants.result()
        sam_results     = f_sam.result()
        simpler_results = f_simpler.result()

        raw_all = grants_results + sam_results + simpler_results
        raw_deduped = api_clients.deduplicate(raw_all)

        if not raw_deduped:
            curated = _get_curated(state)
            if curated:
                return {"programs": curated, "sources_queried": sources_queried, "cached_at": None}
            return {"programs": [], "sources_queried": sources_queried, "cached_at": None}

        # Incremental enrichment
        existing_row = db.get_program_cache(cache_key)
        cached_programs = json.loads(existing_row["programs_json"]) if existing_row else []
        seen_ids = set(json.loads(existing_row["seen_ids_json"])) if existing_row else set()

        new_raw = [p for p in raw_deduped if _stable_id(p) not in seen_ids]

        if new_raw:
            trimmed = [_trim_raw(p) for p in new_raw]
            enrichment_prompt = (
                f"The following {len(trimmed)} programs were found in government databases "
                f"for a {farm_type} farmer in {location}.\n\n"
                "Enrich each program and return a JSON array. For each program, produce exactly this structure:\n"
                "{\n"
                '  "program_name": "...",\n'
                '  "agency": "...",\n'
                '  "level": "federal or state or local",\n'
                '  "description": "2-3 sentence plain-English description of what this program provides",\n'
                '  "eligibility": "Who qualifies and any key requirements",\n'
                '  "how_to_apply": "Step-by-step how to apply",\n'
                '  "documents_needed": ["list", "of", "documents"],\n'
                '  "website": "URL if available else null",\n'
                '  "deadline": "Deadline info, Rolling, or null"\n'
                "}\n\n"
                f"Raw program data:\n{json.dumps(trimmed)}\n\n"
                "Return ONLY the JSON array. No other text."
            )

            response = get_client().messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=8192,
                system="You are an agricultural program specialist. You receive raw government program listings and return enriched, farmer-friendly descriptions in structured JSON.",
                messages=[{"role": "user", "content": enrichment_prompt}],
            )
            text = _strip_markdown(response.content[0].text.strip())
            new_enriched = json.loads(text)
            all_programs = cached_programs + new_enriched
            new_seen_ids = seen_ids | {_stable_id(p) for p in new_raw}
            curated = _get_curated(state)
            for p in curated:
                pid = _stable_id(p)
                if pid not in new_seen_ids:
                    all_programs.append(p)
                    new_seen_ids.add(pid)
            db.upsert_program_cache(cache_key, json.dumps(all_programs), json.dumps(list(new_seen_ids)))
            cached_at = datetime.now().isoformat()
        else:
            # No new IDs — no Claude call, but timestamp still updates
            all_programs = cached_programs
            curated = _get_curated(state)
            for p in curated:
                pid = _stable_id(p)
                if pid not in seen_ids:
                    all_programs.append(p)
                    seen_ids.add(pid)
            db.update_program_cache_timestamp(cache_key)
            cached_at = datetime.now().isoformat()

        return {
            "programs": all_programs,
            "sources_queried": sources_queried,
            "cached_at": cached_at,
        }

    except anthropic.RateLimitError:
        return {"programs": [_error_card("Rate limit reached. Please wait a moment and try again.")], "sources_queried": sources_queried, "cached_at": None}
    except json.JSONDecodeError as e:
        return {"programs": [_error_card(f"Could not parse program data. Error: {e}")], "sources_queried": sources_queried, "cached_at": None}
    except Exception as e:
        return {"programs": [_error_card(str(e))], "sources_queried": sources_queried, "cached_at": None}


def _get_curated(state):
    code = _PILOT_STATE_CODES.get(state.lower())
    if not code:
        return []
    return [p for p in _CURATED_PROGRAMS if p.get("state", "").upper() == code]


def _trim_raw(program):
    """Strip None fields and keep only the fields useful for Claude enrichment."""
    keep = ("title", "agency", "synopsis", "objective", "close_date",
            "source", "assistance_listing_id", "opportunity_id")
    return {k: v for k, v in program.items() if k in keep and v is not None}


def _error_card(message):
    return {
        "program_name": "Error Retrieving Programs",
        "agency": "System",
        "level": "federal",
        "description": message,
        "eligibility": "N/A",
        "how_to_apply": "Please try again.",
        "documents_needed": [],
        "website": None,
        "deadline": None,
    }
