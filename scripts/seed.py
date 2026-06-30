"""Script: Seed sample data cho development."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.logger import setup_logger

logger = setup_logger("seed")


def main():
    """Seed sample product data for development."""
    logger.info("Seeding sample data...")
    # TODO: Implement seeding logic
    logger.info("Seed complete!")


if __name__ == "__main__":
    main()
