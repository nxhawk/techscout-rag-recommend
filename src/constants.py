"""Shared constants - single source of truth for magic numbers/strings used
across the codebase.

This module intentionally has no dependencies on the rest of ``src``/``api``
so it can be imported from anywhere (including the crawler and sync layers)
without risking circular imports.

Two proper enums already exist elsewhere in the codebase and are NOT
duplicated here - they stay where they are as the local style precedent for
"closed-set string enum":

- ``GuardrailAction`` in ``src/guardrails/types.py``
- ``QueryType`` in ``src/pipeline/rag_router.py``
"""

from enum import Enum

# --------------------------------------------------------------------------
# Recommend/similarity scoring weights and heuristics
# --------------------------------------------------------------------------

# Multi-criteria product scoring (src/pipeline/recommend/scoring.py and its
# legacy duplicate src/recommendation/scoring.py).
RECOMMEND_SCORE_WEIGHTS: dict[str, float] = {
    "relevance": 0.35,
    "review": 0.25,
    "value": 0.25,
    "popularity": 0.15,
}

# Composite similarity scoring (src/retrieval/similarity_scorer.py).
SIMILARITY_SCORE_WEIGHTS: dict[str, float] = {
    "semantic": 0.5,
    "price_match": 0.2,
    "rating": 0.15,
    "popularity": 0.15,
}

# Below this many reviews, the review score is penalized (few reviews are
# less trustworthy as a signal).
FEW_REVIEWS_THRESHOLD = 10
FEW_REVIEWS_PENALTY = 0.7

# Value-score penalty applied when a product is priced under budget (scoring)
# and used analogously as a mismatch penalty concept in the two scoring
# copies (`1.0 - (budget_max - price) / budget_max * BUDGET_MISMATCH_PENALTY`).
BUDGET_MISMATCH_PENALTY = 0.3

# Popularity score: min(log(review_count + 1) / log(POPULARITY_LOG_BASE), 1.0)
POPULARITY_LOG_BASE = 10000

# Rating scale ceiling (ratings are 0..5 stars).
MAX_RATING = 5.0

# --------------------------------------------------------------------------
# Personalization boosts (src/pipeline/recommend/personalization.py and its
# legacy duplicate src/recommendation/personalization.py)
# --------------------------------------------------------------------------

BRAND_MATCH_BOOST = 0.1
CATEGORY_MATCH_BOOST = 0.05

# --------------------------------------------------------------------------
# Spec field aliases (SpecAligner: src/comparison/spec_aligner.py and its
# duplicate src/pipeline/compare/spec_aligner.py; SpecParser:
# src/ingestion/spec_parser.py uses a documented narrower subset of this -
# see the comment next to its own key_map).
# --------------------------------------------------------------------------

SPEC_FIELD_ALIASES: dict[str, str] = {
    "pin": "battery",
    "dung_luong_pin": "battery",
    "battery_capacity": "battery",
    "man_hinh": "screen_size",
    "display": "screen_size",
    "screen": "screen_size",
    "bo_nho_trong": "storage",
    "rom": "storage",
    "internal_storage": "storage",
    "bo_nho_ram": "ram",
    "memory": "ram",
    "camera_sau": "rear_camera",
    "main_camera": "rear_camera",
    "camera_truoc": "front_camera",
    "selfie_camera": "front_camera",
    "chip": "processor",
    "cpu": "processor",
    "chipset": "processor",
    "he_dieu_hanh": "os",
    "operating_system": "os",
    "trong_luong": "weight",
    "khoi_luong": "weight",
}

# --------------------------------------------------------------------------
# Price tier thresholds (src/comparison/pros_cons_extractor.py and its
# duplicate src/pipeline/compare/pros_cons_extractor.py)
# --------------------------------------------------------------------------

BUDGET_TIER_MAX_PRICE = 8_000_000
PREMIUM_TIER_MIN_PRICE = 25_000_000

# --------------------------------------------------------------------------
# Category enum (from src/retrieval/filter_engine.py's CATEGORY_MAP and the
# crawler spider files, which hardcode category="smartphone")
# --------------------------------------------------------------------------


class Category(str, Enum):
    """Canonical product categories."""

    SMARTPHONE = "smartphone"
    LAPTOP = "laptop"
    HEADPHONE = "headphone"
    TABLET = "tablet"


# --------------------------------------------------------------------------
# Debezium CDC operation codes (from src/sync/events.py's _SUPPORTED_OPS)
# --------------------------------------------------------------------------


class DebeziumOp(str, Enum):
    """Debezium ``op`` field values for Postgres CDC change events."""

    CREATE = "c"
    UPDATE = "u"
    DELETE = "d"
    READ = "r"


# --------------------------------------------------------------------------
# Retrieval / DB defaults
# --------------------------------------------------------------------------

DEFAULT_POSTGRES_DSN = "postgresql://postgres:postgres@localhost:5432/rag_products"
DEFAULT_EMBEDDING_DIM = 1536
DEFAULT_COLLECTION_NAME = "products"
DEFAULT_ES_URL = "http://localhost:9200"
DEFAULT_ES_INDEX = "product_chunks"

# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------

DEFAULT_LLM_MODEL = "claude-sonnet-4-6"
DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# --------------------------------------------------------------------------
# Guardrail limits
#
# Single source of truth for src/guardrails/config.py's GuardrailConfig
# defaults and api/schemas.py's own limits, replacing what used to be two
# independently-maintained copies of the same numbers.
# --------------------------------------------------------------------------

MAX_QUERY_LENGTH = 2000
MAX_COMPARE_PRODUCTS = 5

# NOTE: these three are genuinely different values in the current codebase
# (src/guardrails/output/schemas.py used 20, src/guardrails/config.py used 10
# for both recommendation and compare items). That 20 vs 10 mismatch looks
# like it may be an oversight worth double-checking with the team - it is
# preserved as-is here (three distinct named constants) rather than silently
# unified, so behavior does not change.
MAX_OUTPUT_ITEMS = 20  # src/guardrails/output/schemas.py hard ceiling on LLM output list length
MAX_RECOMMENDATION_ITEMS = 10  # src/guardrails/config.py GuardrailConfig.max_recommendation_items
MAX_COMPARE_ITEMS = 10  # src/guardrails/config.py GuardrailConfig.max_compare_items

MAX_LIST_STR_ITEMS = 15  # src/guardrails/output/schemas.py _MAX_LIST_STR_ITEMS
PRODUCT_NAME_MAX_LEN = 200  # truncation length used in recommend/compare pipeline context builders
BRAND_MAX_LEN = 100  # truncation length used in recommend pipeline context builder

# --------------------------------------------------------------------------
# Query/candidate pool multipliers (src/pipeline/recommend/engine.py)
# --------------------------------------------------------------------------

CANDIDATE_POOL_MULTIPLIER = 3
RERANK_KEEP_MULTIPLIER = 2

# --------------------------------------------------------------------------
# Rate limiting (api/middleware/rate_limit.py)
# --------------------------------------------------------------------------

DEFAULT_REQUESTS_PER_MINUTE = 30
RATE_LIMIT_WINDOW_S = 60

# --------------------------------------------------------------------------
# Good-rating / price-band heuristics (src/retrieval/filter_engine.py)
# --------------------------------------------------------------------------

# "rating cao" / "được đánh giá cao" keyword match -> minimum rating filter.
GOOD_RATING_THRESHOLD = 4.0

# "tầm X triệu" / "around X million" price parsing does not build an
# intermediate target-price variable - it multiplies the parsed number
# directly by a fixed absolute factor, so these are named as factors rather
# than as a single tolerance ratio (matches the existing formula shape).
PRICE_BAND_LOWER_FACTOR = 0.8
PRICE_BAND_UPPER_FACTOR = 1.2
