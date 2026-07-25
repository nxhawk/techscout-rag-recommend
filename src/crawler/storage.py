"""
Storage - Lưu kết quả crawl ra đĩa (JSON) trong data/raw/crawled.
"""
import json
from datetime import UTC, datetime
from pathlib import Path

from src.crawler.models import CrawlResult
from src.utils.logger import setup_logger

logger = setup_logger("crawler.storage")


class CrawlStorage:
    """Persist crawl results as JSON files.

    Layout:
        <output_dir>/<source>/<timestamp>.json   # full run (with metadata)
        <output_dir>/<source>/latest.json        # products only, ingest-ready
    """

    def __init__(self, output_dir: str = "data/raw/crawled"):
        self.output_dir = Path(output_dir)

    def save(self, result: CrawlResult) -> Path:
        """Save a full crawl run and update the `latest.json` snapshot."""
        source_dir = self.output_dir / result.source
        source_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
        run_file = source_dir / f"{timestamp}.json"
        with open(run_file, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)

        latest_file = source_dir / "latest.json"
        products = [p.to_dict() for p in result.products]
        with open(latest_file, "w", encoding="utf-8") as f:
            json.dump(products, f, ensure_ascii=False, indent=2)

        logger.info("Saved %d products -> %s", result.count, run_file)
        return run_file

    def load_latest(self, source: str) -> list[dict]:
        """Load the most recent products snapshot for a source."""
        latest_file = self.output_dir / source / "latest.json"
        if not latest_file.exists():
            return []
        with open(latest_file, "r", encoding="utf-8") as f:
            return json.load(f)
