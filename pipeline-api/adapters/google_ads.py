"""
Google Ads Keyword Planner adapter.

Thin wrapper over the official google-ads Python library.
Normalizes responses into keyword dict shape ready for DB/scoring.

Environment variables (required to use generate_keyword_ideas):
  GOOGLE_ADS_DEVELOPER_TOKEN
  GOOGLE_ADS_CLIENT_ID
  GOOGLE_ADS_CLIENT_SECRET
  GOOGLE_ADS_REFRESH_TOKEN
  GOOGLE_ADS_LOGIN_CUSTOMER_ID
  GOOGLE_ADS_CUSTOMER_ID

Module imports cleanly even if these vars are missing; client is lazily initialized
on first generate_keyword_ideas call.
"""

import os
import json
from typing import Optional, List, Dict, Any


class GoogleAdsNotConfigured(Exception):
    """Raised when required Google Ads env vars are missing."""
    pass


# ── Lazy client initialization ──────────────────────────────────────────────

_client = None


def _get_client():
    """
    Lazily initialize and return the Google Ads client.
    Raises GoogleAdsNotConfigured if any required env var is missing.
    """
    global _client
    if _client is not None:
        return _client

    required_vars = [
        "GOOGLE_ADS_DEVELOPER_TOKEN",
        "GOOGLE_ADS_CLIENT_ID",
        "GOOGLE_ADS_CLIENT_SECRET",
        "GOOGLE_ADS_REFRESH_TOKEN",
        "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
        "GOOGLE_ADS_CUSTOMER_ID",
    ]

    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        raise GoogleAdsNotConfigured(
            f"Missing required env vars: {', '.join(missing)}. "
            "Set all GOOGLE_ADS_* vars to use keyword research."
        )

    try:
        from google.ads.googleads.client import GoogleAdsClient
        from google.oauth2.credentials import Credentials
    except ImportError as e:
        raise GoogleAdsNotConfigured(
            f"google-ads library not installed: {e}. "
            "Install with: pip install google-ads"
        )

    # Build credentials and client
    credentials = Credentials(
        token=None,
        refresh_token=os.getenv("GOOGLE_ADS_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_ADS_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_ADS_CLIENT_SECRET"),
    )

    _client = GoogleAdsClient.load_from_storage(
        version="v17",
        credentials=credentials
    )
    _client.developer_token = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN")

    return _client


# ── Normalization ──────────────────────────────────────────────────────────

def _competition_enum_to_str(competition_enum: Optional[int]) -> Optional[str]:
    """
    Map Google Ads competition enum to readable string.

    0 = LOW
    1 = MEDIUM
    2 = HIGH
    """
    if competition_enum is None:
        return None
    if competition_enum == 0:
        return "LOW"
    if competition_enum == 1:
        return "MEDIUM"
    if competition_enum == 2:
        return "HIGH"
    return None


def normalize_keyword_ideas(
    results: List[Dict[str, Any]],
    source: str = "google_ads",
    region: str = "ID:id"
) -> List[Dict[str, Any]]:
    """
    Normalize Google Ads KeywordPlanIdeaService.generate_keyword_ideas results
    into keyword dict shape.

    Args:
        results: list of result dicts from Google Ads API
        source: source identifier (default "google_ads")
        region: geo+lang code (default "ID:id")

    Returns:
        list of normalized dicts ready for DB insertion
    """
    normalized = []

    for result in results:
        text = result.get("text", "").strip()
        if not text:
            continue

        metrics = result.get("keyword_idea_metrics", {})

        # ponytail: inline metric extraction, straightforward mapping
        avg_monthly_searches = metrics.get("avg_monthly_searches")
        competition = metrics.get("competition")
        competition_index = metrics.get("competition_index")
        cpc_low = metrics.get("low_top_of_page_bid_micros")
        cpc_high = metrics.get("high_top_of_page_bid_micros")

        normalized.append({
            "keyword": text,
            "source": source,
            "region": region,
            "search_volume_min": avg_monthly_searches,  # placeholder for future min/max ranges
            "search_volume_max": None,
            "avg_monthly_searches": avg_monthly_searches,
            "competition": _competition_enum_to_str(competition),
            "competition_index": competition_index,
            "cpc_low_micros": cpc_low,
            "cpc_high_micros": cpc_high,
            "niche": None,  # will be filled by caller if desired
            "raw": json.dumps({
                "text": text,
                "keyword_idea_metrics": metrics
            }),
        })

    return normalized


def compute_score(
    avg_monthly_searches: Optional[int],
    competition_index: Optional[int],
    niche_fit: float = 1.0
) -> float:
    """
    Compute composite keyword score.

    Formula: score = avg_monthly_searches * (1 - competition_index/100) * niche_fit

    Args:
        avg_monthly_searches: search volume (may be None)
        competition_index: 0-100 competition score (may be None)
        niche_fit: multiplier for niche relevance (default 1.0)

    Returns:
        float score, or 0.0 if any required input is None
    """
    if avg_monthly_searches is None or competition_index is None:
        return 0.0

    # Clamp competition_index to [0, 100]
    ci = max(0, min(int(competition_index), 100))
    return float(avg_monthly_searches) * (1.0 - ci / 100.0) * float(niche_fit)


def generate_keyword_ideas(
    seeds: List[str],
    geo: str = "ID",
    lang: str = "id"
) -> Dict[str, Any]:
    """
    Call Google Ads KeywordPlanIdeaService.generate_keyword_ideas.

    Args:
        seeds: list of seed keywords (e.g. ["video editing", "adobe premiere"])
        geo: geo code (default "ID" = Indonesia)
        lang: language code (default "id" = Indonesian)

    Returns:
        dict with "results" key containing list of keyword ideas

    Raises:
        GoogleAdsNotConfigured if env vars are missing
        Exception if API call fails
    """
    client = _get_client()  # May raise GoogleAdsNotConfigured

    # Map geo/lang to Google Ads constants
    # ponytail: minimal mapping; extend if needed for other regions
    GEO_CONSTANTS = {
        "ID": 2360,  # Indonesia
        "US": 2840,  # United States
    }
    LANG_CONSTANTS = {
        "id": 1000,  # Indonesian (placeholder, Google Ads uses different codes)
        "en": 1000,  # English (placeholder)
    }

    geo_id = GEO_CONSTANTS.get(geo.upper())
    lang_id = LANG_CONSTANTS.get(lang.lower())

    if not geo_id:
        raise ValueError(f"Unknown geo code: {geo}")
    if not lang_id:
        raise ValueError(f"Unknown lang code: {lang}")

    # Build API request
    customer_id = os.getenv("GOOGLE_ADS_CUSTOMER_ID", "").replace("-", "")
    service = client.get_service("KeywordPlanIdeaService")

    # Create location and language objects
    location = client.get_type("LocationInfo")
    location.geo_target_constant = f"geoTargetConstants/{geo_id}"
    locations = [location]

    language = client.get_type("LanguageInfo")
    language.language_constant = f"languageConstants/{lang_id}"
    languages = [language]

    keyword_seed = client.get_type("KeywordSeed")
    keyword_seed.keywords = seeds

    request = client.get_type("GenerateKeywordIdeasRequest")
    request.customer_id = customer_id
    request.language = languages[0]
    request.geo_target_constants = locations
    request.keyword_seed = keyword_seed

    # Execute request and collect results
    response = service.generate_keyword_ideas(request=request)

    results = []
    for idea in response.results:
        results.append({
            "text": idea.text,
            "keyword_idea_metrics": {
                "avg_monthly_searches": idea.keyword_idea_metrics.avg_monthly_searches,
                "competition": idea.keyword_idea_metrics.competition,
                "competition_index": idea.keyword_idea_metrics.competition_index,
                "low_top_of_page_bid_micros": idea.keyword_idea_metrics.low_top_of_page_bid_micros,
                "high_top_of_page_bid_micros": idea.keyword_idea_metrics.high_top_of_page_bid_micros,
            }
        })

    return {"results": results}
