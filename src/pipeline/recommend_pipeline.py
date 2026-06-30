"""
Recommend Pipeline - Pipeline gợi ý sản phẩm end-to-end.
Query → Intent Parser → Filter → Retrieve → Score → Rank → Prompt → LLM → Response
"""
from src.pipeline.recommend.engine import RecommendEngine
from src.generation.llm_client import LLMClient
from src.generation.response_parser import ResponseParser
from src.generation.prompt_templates.recommend_prompt import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)


class RecommendPipeline:
    """End-to-end recommendation pipeline."""

    def __init__(self, recommend_engine: RecommendEngine, llm_client: LLMClient):
        self.recommend_engine = recommend_engine
        self.llm_client = llm_client
        self.parser = ResponseParser()

    def run(self, query: str, top_k: int = 5) -> dict:
        """Run the full recommendation pipeline."""
        # Step 1: Get recommendations with scores
        result = self.recommend_engine.recommend(query, top_k=top_k)

        # Step 2: Build context for LLM
        product_context = self._build_context(result["recommendations"])

        # Step 3: Generate response via LLM
        prompt = USER_PROMPT_TEMPLATE.format(
            query=query,
            use_cases=", ".join(result["intent"]["use_case"]) or "Chưa xác định",
            priorities=", ".join(result["intent"]["priorities"]) or "Chưa xác định",
            budget=str(result["intent"]["budget"]) or "Không giới hạn",
            product_context=product_context,
            top_k=top_k,
        )
        llm_response = self.llm_client.generate(prompt, system_prompt=SYSTEM_PROMPT)

        # Step 4: Parse response
        parsed = self.parser.parse_recommendation(llm_response)
        parsed["retrieved_products"] = result["recommendations"]

        return parsed

    def _build_context(self, products: list[dict]) -> str:
        lines = []
        for i, p in enumerate(products, 1):
            meta = p.get("metadata", {})
            lines.append(
                f"{i}. {meta.get('name', 'N/A')} - {meta.get('brand', '')} "
                f"| Giá: {meta.get('price', 'N/A')} | Rating: {meta.get('avg_rating', 'N/A')} "
                f"| Score: {p.get('final_score', p.get('score', 0))}"
            )
            if p.get("document"):
                lines.append(f"   Chi tiết: {p['document'][:300]}")
        return "\n".join(lines)
