"""Script: Seed sample product data for development.

Generates a small, realistic set of sample products that match the crawl data
schema (:class:`src.crawler.models.CrawledProduct`, the same shape the crawler
writes to ``data/raw/crawled/<source>/latest.json``) so the ingest pipeline can
be exercised without running a live crawl.

The products are built from the ``CrawledProduct`` dataclass itself, so the
output structure always tracks the model: flat ``specifications`` derived from
canonical ``spec_groups`` (via :func:`flatten_spec_groups`), plus ``source``,
``source_url``, ``image_url``, ``reviews`` and ``crawled_at``.

Output is written to ``data/raw/products/sample_products.json`` as a JSON list of
product dicts (identical shape to a crawler ``latest.json``). Ingest it with::

    uv run python scripts/ingest.py --source products
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.crawler.models import CrawledProduct, Review
from src.crawler.parser import flatten_spec_groups
from src.utils.logger import setup_logger

logger = setup_logger("seed")

# All sample products carry this synthetic source so they are easy to tell apart
# from real crawled data.
SEED_SOURCE = "seed"

# Where the sample products land (the `products` ingest source reads this dir).
OUTPUT_FILE = Path(__file__).parent.parent / "data" / "raw" / "products" / "sample_products.json"


def _product(
    slug: str,
    name: str,
    brand: str,
    price: int,
    spec_groups: dict[str, dict[str, str]],
    description: str,
    image_url: str,
    avg_rating: float,
    review_count: int,
    reviews: list[Review],
    tags: list[str],
) -> CrawledProduct:
    """Build one sample ``CrawledProduct`` with specs flattened from spec_groups."""
    return CrawledProduct(
        id=f"{SEED_SOURCE}-{slug}",
        name=name,
        source=SEED_SOURCE,
        source_url=f"https://example.com/{SEED_SOURCE}/{slug}",
        brand=brand,
        category="smartphone",
        price=price,
        currency="VND",
        specifications=flatten_spec_groups(spec_groups),
        spec_groups=spec_groups,
        description=description,
        image_url=image_url,
        avg_rating=avg_rating,
        review_count=review_count,
        reviews=reviews,
        tags=tags,
    )


def sample_products() -> list[CrawledProduct]:
    """Return the hand-authored sample catalog (crawl-shaped)."""
    return [
        _product(
            slug="iphone-15-pro-max",
            name="Điện thoại iPhone 15 Pro Max 256GB",
            brand="Apple",
            price=29990000,
            spec_groups={
                "configuration_memory": {
                    "Hệ điều hành": "iOS 17",
                    "Chip xử lý (CPU)": "Apple A17 Pro 6 nhân",
                    "RAM": "8 GB",
                    "Dung lượng lưu trữ": "256 GB",
                },
                "camera_display": {
                    "Kích thước màn hình": "6.7 inch",
                    "Công nghệ màn hình": "OLED Super Retina XDR",
                    "Camera sau": "48 MP + 12 MP + 12 MP",
                    "Camera trước": "12 MP",
                },
                "battery_charging": {
                    "Dung lượng pin": "4441 mAh",
                    "Hỗ trợ sạc tối đa": "20 W",
                },
                "design_material": {
                    "Chất liệu khung": "Titan",
                    "Khối lượng": "221 g",
                },
            },
            description=(
                "Flagship cao cấp nhất của Apple với chip A17 Pro, camera 48MP "
                "và khung viền titan bền nhẹ."
            ),
            image_url="https://example.com/images/iphone-15-pro-max.jpg",
            avg_rating=4.7,
            review_count=1250,
            reviews=[
                Review(
                    author="Minh Anh",
                    rating=5.0,
                    content="Máy đẹp, quay phim cực nét, pin dùng cả ngày thoải mái.",
                ),
                Review(
                    author="Hoàng Nam",
                    rating=4.0,
                    content="Hiệu năng mạnh nhưng giá hơi cao và sạc vẫn khá chậm.",
                ),
            ],
            tags=["flagship", "cao cấp", "chụp ảnh", "gaming"],
        ),
        _product(
            slug="samsung-galaxy-s24-ultra",
            name="Điện thoại Samsung Galaxy S24 Ultra 256GB",
            brand="Samsung",
            price=31990000,
            spec_groups={
                "configuration_memory": {
                    "Hệ điều hành": "Android 14 (One UI 6.1)",
                    "Chip xử lý (CPU)": "Snapdragon 8 Gen 3 for Galaxy",
                    "RAM": "12 GB",
                    "Dung lượng lưu trữ": "256 GB",
                },
                "camera_display": {
                    "Kích thước màn hình": "6.8 inch",
                    "Công nghệ màn hình": "Dynamic AMOLED 2X",
                    "Camera sau": "200 MP + 50 MP + 12 MP + 10 MP",
                    "Camera trước": "12 MP",
                },
                "battery_charging": {
                    "Dung lượng pin": "5000 mAh",
                    "Hỗ trợ sạc tối đa": "45 W",
                },
                "design_material": {
                    "Chất liệu khung": "Titan",
                    "Khối lượng": "232 g",
                },
            },
            description=(
                "Flagship Android hàng đầu với bút S Pen tích hợp, camera 200MP "
                "và bộ tính năng Galaxy AI."
            ),
            image_url="https://example.com/images/samsung-galaxy-s24-ultra.jpg",
            avg_rating=4.6,
            review_count=980,
            reviews=[
                Review(
                    author="Thu Trang",
                    rating=5.0,
                    content="Camera zoom 100x quá đỉnh, S Pen tiện cho công việc.",
                ),
                Review(
                    author="Đức Long",
                    rating=4.0,
                    content="Máy to và nặng, cầm lâu hơi mỏi tay nhưng pin rất trâu.",
                ),
            ],
            tags=["flagship", "cao cấp", "S Pen", "AI", "zoom"],
        ),
        _product(
            slug="xiaomi-14",
            name="Điện thoại Xiaomi 14 12GB 256GB",
            brand="Xiaomi",
            price=13990000,
            spec_groups={
                "configuration_memory": {
                    "Hệ điều hành": "Android 14 (HyperOS)",
                    "Chip xử lý (CPU)": "Snapdragon 8 Gen 3",
                    "RAM": "12 GB",
                    "Dung lượng lưu trữ": "256 GB",
                },
                "camera_display": {
                    "Kích thước màn hình": "6.36 inch",
                    "Công nghệ màn hình": "OLED LTPO",
                    "Camera sau": "50 MP + 50 MP + 50 MP (Leica)",
                    "Camera trước": "32 MP",
                },
                "battery_charging": {
                    "Dung lượng pin": "4610 mAh",
                    "Hỗ trợ sạc tối đa": "90 W",
                },
                "design_material": {
                    "Chất liệu khung": "Nhôm",
                    "Khối lượng": "193 g",
                },
            },
            description=(
                "Flagship nhỏ gọn với hệ camera Leica, chip Snapdragon 8 Gen 3 "
                "và mức giá cạnh tranh."
            ),
            image_url="https://example.com/images/xiaomi-14.jpg",
            avg_rating=4.5,
            review_count=650,
            reviews=[
                Review(
                    author="Quốc Bảo",
                    rating=5.0,
                    content="Nhỏ gọn dễ cầm, ảnh chụp màu Leica rất đẹp, sạc siêu nhanh.",
                ),
                Review(
                    author="Lan Phương",
                    rating=4.0,
                    content="Cấu hình mạnh, giá tốt, chỉ tiếc HyperOS còn ít quảng cáo.",
                ),
            ],
            tags=["flagship", "Leica", "compact", "giá tốt"],
        ),
        _product(
            slug="oppo-reno11-f",
            name="Điện thoại OPPO Reno11 F 5G 8GB 256GB",
            brand="OPPO",
            price=8490000,
            spec_groups={
                "configuration_memory": {
                    "Hệ điều hành": "Android 14 (ColorOS 14)",
                    "Chip xử lý (CPU)": "MediaTek Dimensity 7050",
                    "RAM": "8 GB",
                    "Dung lượng lưu trữ": "256 GB",
                },
                "camera_display": {
                    "Kích thước màn hình": "6.7 inch",
                    "Công nghệ màn hình": "AMOLED 120Hz",
                    "Camera sau": "64 MP + 8 MP + 2 MP",
                    "Camera trước": "32 MP",
                },
                "battery_charging": {
                    "Dung lượng pin": "5000 mAh",
                    "Hỗ trợ sạc tối đa": "67 W",
                },
                "design_material": {
                    "Chất liệu khung": "Nhựa",
                    "Khối lượng": "177 g",
                },
            },
            description=(
                "Điện thoại tầm trung với thiết kế mỏng nhẹ, màn hình AMOLED 120Hz "
                "và sạc nhanh SUPERVOOC 67W."
            ),
            image_url="https://example.com/images/oppo-reno11-f.jpg",
            avg_rating=4.3,
            review_count=420,
            reviews=[
                Review(
                    author="Gia Hân",
                    rating=4.0,
                    content="Máy mỏng nhẹ, màn mượt, sạc nhanh đầy trong khoảng 45 phút.",
                ),
                Review(
                    author="Tấn Phát",
                    rating=4.0,
                    content="Tầm giá này dùng ổn, chơi game nhẹ nhàng thì mượt.",
                ),
            ],
            tags=["tầm trung", "pin trâu", "sạc nhanh", "màn đẹp"],
        ),
        _product(
            slug="samsung-galaxy-a15",
            name="Điện thoại Samsung Galaxy A15 8GB 128GB",
            brand="Samsung",
            price=4690000,
            spec_groups={
                "configuration_memory": {
                    "Hệ điều hành": "Android 14 (One UI 6)",
                    "Chip xử lý (CPU)": "MediaTek Helio G99",
                    "RAM": "8 GB",
                    "Dung lượng lưu trữ": "128 GB",
                },
                "camera_display": {
                    "Kích thước màn hình": "6.5 inch",
                    "Công nghệ màn hình": "Super AMOLED 90Hz",
                    "Camera sau": "50 MP + 5 MP + 2 MP",
                    "Camera trước": "13 MP",
                },
                "battery_charging": {
                    "Dung lượng pin": "5000 mAh",
                    "Hỗ trợ sạc tối đa": "25 W",
                },
                "design_material": {
                    "Chất liệu khung": "Nhựa",
                    "Khối lượng": "200 g",
                },
            },
            description=(
                "Điện thoại giá rẻ với màn hình Super AMOLED sắc nét, pin 5000mAh "
                "bền bỉ dùng cả ngày."
            ),
            image_url="https://example.com/images/samsung-galaxy-a15.jpg",
            avg_rating=4.2,
            review_count=310,
            reviews=[
                Review(
                    author="Ngọc Mai",
                    rating=4.0,
                    content="Giá rẻ mà màn AMOLED đẹp, pin dùng thoải mái hơn một ngày.",
                ),
                Review(
                    author="Văn Hùng",
                    rating=4.0,
                    content="Hợp làm máy phụ, nghe gọi lướt web ổn định.",
                ),
            ],
            tags=["giá rẻ", "phổ thông", "pin trâu", "màn AMOLED"],
        ),
    ]


def main() -> None:
    """Generate sample products and write them to the products data dir."""
    logger.info("Seeding sample data...")
    products = sample_products()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = [p.to_dict() for p in products]
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    logger.info("Wrote %d sample products -> %s", len(products), OUTPUT_FILE)
    logger.info("Seed complete! Ingest with: uv run python scripts/ingest.py --source products")


if __name__ == "__main__":
    main()
