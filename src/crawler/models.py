"""
Models - Cấu trúc dữ liệu cho kết quả crawl.
"""
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime


@dataclass
class Review:
    """A single buyer review scraped from a product page or review endpoint."""

    author: str = ""
    rating: float = 0.0  # star rating for this review (0 if not shown)
    content: str = ""

    def key(self) -> tuple[str, str]:
        """Identity used to deduplicate reviews."""
        return (self.author, self.content)


@dataclass
class CrawledProduct:
    """A single product scraped from a source.

    Field names align with the raw product schema consumed by
    src/ingestion/data_cleaner.py (build_product_profile).
    """

    id: str
    name: str
    source: str
    source_url: str
    brand: str = ""
    category: str = ""
    price: int = 0
    currency: str = "VND"
    # Flattened label -> value map (union of all spec groups).
    specifications: dict[str, str] = field(default_factory=dict)
    # Specs grouped by canonical category (configuration_memory, camera_display,
    # battery_charging, design_material, connectivity, general).
    spec_groups: dict[str, dict[str, str]] = field(default_factory=dict)
    description: str = ""
    image_url: str = ""
    avg_rating: float = 0.0
    review_count: int = 0
    reviews: list[Review] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    crawled_at: str = field(default_factory=lambda: datetime.now(tz=UTC).isoformat())

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON storage (nested reviews included)."""
        return asdict(self)


@dataclass
class CrawlResult:
    """Summary of a crawl run for a single source."""

    source: str
    products: list[CrawledProduct] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(tz=UTC).isoformat())
    finished_at: str = ""

    @property
    def count(self) -> int:
        return len(self.products)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "count": self.count,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "errors": self.errors,
            "products": [p.to_dict() for p in self.products],
        }
