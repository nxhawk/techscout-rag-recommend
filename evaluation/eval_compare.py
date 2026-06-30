"""Evaluation - Đánh giá chất lượng so sánh sản phẩm."""


class CompareEvaluator:
    """Evaluate comparison quality."""

    def evaluate(self, test_cases: list[dict]) -> dict:
        results = {"total": len(test_cases), "passed": 0, "metrics": {}}
        for case in test_cases:
            # TODO: Run pipeline and compare with expected
            pass
        return results
