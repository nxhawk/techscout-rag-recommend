"""
Compare Pipeline - Pipeline so sánh sản phẩm end-to-end.
Query → Extract Products → Retrieve Specs → Align → Compare → Prompt → LLM → Response
"""
from src.pipeline.compare.comparator import ProductComparator
from src.pipeline.compare.formatter import ComparisonFormatter
from src.generation.llm_client import LLMClient
from src.generation.response_parser import ResponseParser
from src.generation.prompt_templates.compare_prompt import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)
from src.retrieval.product_retriever import ProductRetriever


class ComparePipeline:
    """End-to-end comparison pipeline."""

    def __init__(
        self,
        retriever: ProductRetriever,
        comparator: ProductComparator,
        llm_client: LLMClient,
    ):
        self.retriever = retriever
        self.comparator = comparator
        self.formatter = ComparisonFormatter()
        self.llm_client = llm_client
        self.parser = ResponseParser()

    def run(self, query: str, product_ids: list[str] | None = None) -> dict:
        """Run the full comparison pipeline."""
        # Step 1: Get products to compare
        if product_ids:
            products = self._get_products_by_ids(product_ids)
        else:
            products = self._extract_products_from_query(query)

        if len(products) < 2:
            return {"error": "Cần ít nhất 2 sản phẩm để so sánh."}

        # Step 2: Compare
        comparison = self.comparator.compare(products)
        table_md = self.formatter.format_markdown_table(comparison)

        # Step 3: Generate LLM analysis
        product_context = "\n".join(
            f"- {p['name']}: {p.get('description', '')[:200]}" for p in products
        )
        prompt = USER_PROMPT_TEMPLATE.format(
            query=query,
            product_context=product_context,
            comparison_table=table_md,
        )
        llm_response = self.llm_client.generate(prompt, system_prompt=SYSTEM_PROMPT)
        parsed = self.parser.parse_comparison(llm_response)

        return {
            "comparison_table": comparison,
            "markdown_table": table_md,
            "analysis": parsed,
        }

    def _get_products_by_ids(self, product_ids: list[str]) -> list[dict]:
        """Retrieve full product data by IDs."""
        # TODO: Implement lookup from database/vector store
        return []

    def _extract_products_from_query(self, query: str) -> list[dict]:
        """Extract product names from query and retrieve their data."""
        results = self.retriever.retrieve(query, top_k=5)
        # TODO: Better product extraction logic
        return [r.get("metadata", {}) for r in results[:3]]
