"""
Config - Cấu hình cho module crawler.

Loaded from configs/crawler.yaml. Mirrors the PipelineConfig pattern used in
src/pipeline/config.py.
"""
import yaml
from dataclasses import dataclass, field


@dataclass
class SourceConfig:
    """Configuration for a single crawl source (one website)."""

    name: str
    base_url: str
    enabled: bool = True
    # Category slug -> listing URL (may contain a `{page}` placeholder).
    categories: dict[str, str] = field(default_factory=dict)
    max_pages: int = 3
    max_products: int | None = None
    # Optional review endpoint template, may contain `{product_id}`, `{slug}`
    # and `{page}` placeholders. Leave empty to only parse inline reviews.
    # For GraphQL sources (e.g. cellphones) this is the plain endpoint URL and
    # the spider builds the POST payload itself.
    reviews_url: str | None = None
    # GraphQL comment query `type` argument (cellphones): "product" returns the
    # Q&A/comment feed; other values (e.g. "rating") may return starred reviews.
    reviews_query_type: str = "product"


@dataclass
class CrawlerConfig:
    """Top-level crawler configuration."""

    # HTTP client
    user_agent: str = (
        "Mozilla/5.0 (compatible; RagProductBot/0.1; "
        "+https://github.com/nxhawk/rag-product-recommend)"
    )
    timeout: float = 20.0
    max_retries: int = 3
    retry_backoff: float = 1.5

    # Politeness
    request_delay: float = 1.0  # seconds between requests to the same host
    respect_robots: bool = True

    # Concurrency (async fetch of detail pages)
    concurrency: int = 4

    # Reviews
    fetch_reviews: bool = True  # collect buyer reviews in addition to specs
    max_reviews: int = 20       # cap reviews kept per product

    # Output
    output_dir: str = "data/raw/crawled"

    # Sources: name -> SourceConfig
    sources: dict[str, SourceConfig] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, filepath: str = "configs/crawler.yaml") -> "CrawlerConfig":
        """Load crawler configuration from a YAML file."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        raw_sources = data.pop("sources", {}) or {}
        sources = {
            name: SourceConfig(name=name, **params)
            for name, params in raw_sources.items()
        }

        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(sources=sources, **known)

    def get_source(self, name: str) -> SourceConfig:
        """Return the config for a named source or raise KeyError."""
        return self.sources[name]
