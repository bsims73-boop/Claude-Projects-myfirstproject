import json
import concurrent.futures

import anthropic

import config
from modules.ocr import get_client, _strip_markdown
from modules import api_clients

FARM_TYPES = [
    "Row Crops (corn, soybeans, wheat, etc.)",
    "Livestock (beef cattle, hogs, sheep)",
    "Dairy",
    "Poultry (broilers, layers, turkeys)",
    "Organic",
    "Specialty Crops (fruits, vegetables, nuts)",
    "Mixed / Diversified",
]

def _build_location(state, county):
    if not county:
        return state
    if state == "Alaska":
        return f"{county}, {state}"
    return f"{county} County, {state}"


PROMPT_TEMPLATE = """\
Research all available farm assistance programs for a {farm_type} farmer in {location}.

Include:
- Federal programs through USDA agencies (FSA, NRCS, RMA, Rural Development, AMS)
- State programs through the {state} Department of Agriculture or related agencies
- Any notable local, county, or regional programs

Return ONLY a JSON array using this structure (no other text):
[
  {{
    "program_name": "Full official program name",
    "agency": "Administering agency name",
    "level": "federal or state or local",
    "description": "2-3 sentence description of what the program provides",
    "eligibility": "Who qualifies and any key requirements",
    "how_to_apply": "Step-by-step application process",
    "documents_needed": ["list", "of", "required", "documents"],
    "website": "Official URL if known, else null",
    "deadline": "Application deadline info, or Rolling, or null"
  }}
]

Be comprehensive — include at least 10 programs if available. Prioritize programs most relevant to {farm_type} operations. Only return the JSON array."""


def research_farm_programs(state, farm_type, county="", page=1):
    per_page = 25
    location = _build_location(state, county)
    sources_queried = ["grants.gov"]
    if config.SAM_GOV_API_KEY:
        sources_queried.append("sam.gov")
    if config.SIMPLER_GRANTS_API_KEY:
        sources_queried.append("simpler.grants.gov")

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            f_grants  = executor.submit(api_clients.fetch_grants_gov,     state, farm_type, page, per_page)
            f_sam     = executor.submit(api_clients.fetch_sam_gov,        state, farm_type, page, per_page)
            f_simpler = executor.submit(api_clients.fetch_simpler_grants, state, farm_type, page, per_page)
        grants_results  = f_grants.result()
        sam_results     = f_sam.result()
        simpler_results = f_simpler.result()

        raw_all    = grants_results + sam_results + simpler_results
        raw_deduped = api_clients.deduplicate(raw_all)

        has_more = (
            len(grants_results)  == per_page or
            len(sam_results)     == per_page or
            len(simpler_results) == per_page
        )

        if not raw_deduped:
            # Fallback: Claude training data
            response = get_client().messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=8192,
                system=(
                    "You are an agricultural policy expert with comprehensive knowledge of USDA programs, "
                    "state agricultural department programs, and local farm assistance programs. "
                    "Provide accurate, detailed, actionable information for farmers. "
                    "Always respond with valid JSON only."
                ),
                messages=[{"role": "user", "content": PROMPT_TEMPLATE.format(
                    state=state, farm_type=farm_type, location=location
                )}],
            )
            text = _strip_markdown(response.content[0].text.strip())
            programs = json.loads(text)
            return {"programs": programs, "has_more": False, "page": page, "sources_queried": sources_queried}

        # Enrichment path — trim raw data to reduce prompt size
        trimmed = [_trim_raw(p) for p in raw_deduped]
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
            max_tokens=16000,
            system="You are an agricultural program specialist. You receive raw government program listings and return enriched, farmer-friendly descriptions in structured JSON.",
            messages=[{"role": "user", "content": enrichment_prompt}],
        )
        text = _strip_markdown(response.content[0].text.strip())
        programs = json.loads(text)
        return {"programs": programs, "has_more": has_more, "page": page, "sources_queried": sources_queried}

    except anthropic.RateLimitError:
        return {"programs": [_error_card("Rate limit reached. Please wait a moment and try again.")], "has_more": False, "page": page, "sources_queried": sources_queried}
    except json.JSONDecodeError as e:
        return {"programs": [_error_card(f"Could not parse program data. Error: {e}")], "has_more": False, "page": page, "sources_queried": sources_queried}
    except Exception as e:
        return {"programs": [_error_card(str(e))], "has_more": False, "page": page, "sources_queried": sources_queried}


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
