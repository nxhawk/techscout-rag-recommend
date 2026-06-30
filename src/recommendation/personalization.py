"""
Personalization - Cá nhân hóa gợi ý dựa trên lịch sử người dùng.
"""


class Personalization:
    """Personalize recommendations based on user history."""

    def __init__(self):
        self.user_profiles: dict[str, dict] = {}

    def update_profile(self, user_id: str, action: str, product: dict) -> None:
        """Update user profile based on an action (view, purchase, like)."""
        if user_id not in self.user_profiles:
            self.user_profiles[user_id] = {
                "viewed": [], "purchased": [], "liked": [],
                "preferred_brands": [], "preferred_categories": [],
                "price_range": {"min": 0, "max": 0},
            }
        profile = self.user_profiles[user_id]
        if action in profile:
            profile[action].append(product.get("product_id"))

    def get_boost_factors(self, user_id: str, product: dict) -> float:
        """Get personalization boost factor for a product."""
        profile = self.user_profiles.get(user_id)
        if not profile:
            return 1.0
        boost = 1.0
        if product.get("brand") in profile.get("preferred_brands", []):
            boost += 0.1
        if product.get("category") in profile.get("preferred_categories", []):
            boost += 0.05
        return boost
