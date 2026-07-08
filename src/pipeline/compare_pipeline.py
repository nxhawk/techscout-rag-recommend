"""
Compare Pipeline - Pipeline so sánh sản phẩm end-to-end.
Query → [Input Guardrail] → Extract Products → Retrieve Specs → Align
      → Compare → [Context Guardrail] → Prompt → LLM → [Output Guardrail] → Response
"""

import logging

from src.generation.llm_client import LLMClient
from src.generation.prompt_templates.compare_prompt import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)
from src.generation.response_parser import ResponseParser
from src.guardrails import (
    GuardrailConfig,
    InputGuardrailBlocked,
    build_compare_fallback,
    build_input_chain,
    ground_compare_analysis,
    log_guardrail_event,
    sanitize_text_field,
    validate_compare_output,
)
from src.pipeline.compare.comparator import ProductComparator
from src.pipeline.compare.formatter import ComparisonFormatter
from src.retrieval.product_retriever import ProductRetriever

logger = logging.getLogger(__name__)

_INSUFFICIENT_PRODUCTS_MSG = "Cần ít nhất 2 sản phẩm để so sánh."


class ComparePipeline:
    """End-to-end comparison pipeline."""

    def __init__(
        self,
        retriever: ProductRetriever,
        comparator: ProductComparator,
        llm_client: LLMClient,
        product_repository: object | None = None,
        guardrail_config: GuardrailConfig | None = None,
    ):
        self.retriever = retriever
        self.comparator = comparator
        self.formatter = ComparisonFormatter()
        self.llm_client = llm_client
        self.parser = ResponseParser()
        # Optional: anything with a `.get(product_id) -> dict | None` method
        # (typically `src.catalog.product_repository.ProductRepository`).
        # Kept untyped here to avoid a hard import dependency on the catalog
        # layer from the generation layer.
        self.product_repository = product_repository
        self.guardrail_config = guardrail_config or GuardrailConfig()
        self.input_chain = build_input_chain(self.guardrail_config)

    def run(self, query: str | None = None, product_ids: list[str] | None = None) -> dict:
        """Run the full comparison pipeline.

        Raises:
            InputGuardrailBlocked: ``query`` was rejected by an input
                guardrail. Callers (API routes) should map this to an
                HTTP 4xx. Only applies when ``query`` is provided - a pure
                ``product_ids`` request skips the input-text guardrail.
        """
        warnings: list[str] = []
        if query:
            input_result = self.input_chain.run(query)
            if input_result.blocked:
                log_guardrail_event(
                    logger,
                    stage="input",
                    action="block",
                    reason=input_result.reason,
                    level=logging.WARNING,
                    pipeline="compare",
                )
                raise InputGuardrailBlocked(
                    reason=input_result.reason or "Query khong hop le.",
                    warnings=input_result.warnings,
                )
            if input_result.warnings:
                log_guardrail_event(
                    logger,
                    stage="input",
                    action="sanitize",
                    pipeline="compare",
                    warnings=input_result.warnings,
                )
            query = input_result.sanitized_text or query
            warnings.extend(input_result.warnings)

        # Step 1: Get products to compare
        if product_ids:
            products = self._get_products_by_ids(product_ids)
        else:
            products = self._extract_products_from_query(query or "")

        products = products[: self.guardrail_config.max_compare_products]

        if len(products) < 2:
            return {
                "comparison_table": {},
                "markdown_table": "",
                "analysis": build_compare_fallback(products),
                "warnings": warnings,
                "error": _INSUFFICIENT_PRODUCTS_MSG,
            }

        # Step 2: Compare
        comparison = self.comparator.compare(products)
        table_md = self.formatter.format_markdown_table(comparison)

        # Step 3: Generate LLM analysis (context guardrail sanitizes each field)
        product_context = self._build_context(products)
        prompt = USER_PROMPT_TEMPLATE.format(
            query=query or "",
            product_context=product_context,
            comparison_table=table_md,
        )
        llm_response = self.llm_client.generate(prompt, system_prompt=SYSTEM_PROMPT)

        # Step 4: Output guardrail - schema validation, then grounding.
        analysis = self._guarded_output(llm_response, products, warnings)

        return {
            "comparison_table": comparison,
            "markdown_table": table_md,
            "analysis": analysis,
            "warnings": warnings,
        }

    def _guarded_output(self, llm_response: str, products: list[dict], warnings: list[str]) -> dict:
        output_result = validate_compare_output(llm_response)
        if output_result.blocked:
            log_guardrail_event(
                logger,
                stage="output",
                action="block",
                reason=output_result.reason,
                level=logging.WARNING,
                pipeline="compare",
            )
            warnings.append(
                "LLM tra ve du lieu khong hop le, da su dung ket qua phan tich du phong."
            )
            return build_compare_fallback(products)

        payload = output_result.sanitized_payload or {}
        raw_items = payload.get("product_analysis", [])
        grounded_items, ground_warnings = ground_compare_analysis(raw_items, products)
        if ground_warnings:
            log_guardrail_event(
                logger,
                stage="output",
                action="sanitize",
                pipeline="compare",
                warnings=ground_warnings,
            )
            warnings.extend(ground_warnings)

        if raw_items and not grounded_items:
            warnings.append(
                "Toan bo phan tich tu LLM khong khop du lieu san pham, da su dung ket qua du phong."
            )
            return build_compare_fallback(products)

        return {
            "criteria_comparison": payload.get("criteria_comparison", []),
            "product_analysis": grounded_items,
            "conclusion": payload.get("conclusion", ""),
        }

    def _build_context(self, products: list[dict]) -> str:
        cfg = self.guardrail_config
        lines = []
        for p in products:
            name = sanitize_text_field(p.get("name", "N/A"), max_len=200) or "N/A"
            description = sanitize_text_field(
                p.get("description", ""), max_len=cfg.max_context_field_chars
            )
            lines.append(f"- {name}: {description}")
        return "\n".join(lines)

    def _get_products_by_ids(self, product_ids: list[str]) -> list[dict]:
        """Retrieve full product data by IDs from the source-of-truth catalog."""
        if self.product_repository is None:
            logger.warning("Compare requested by product_ids but no product_repository configured.")
            return []
        products = []
        for product_id in product_ids:
            product = self.product_repository.get(product_id)  # type: ignore[attr-defined]
            if product:
                products.append(product)
        return products

    def _extract_products_from_query(self, query: str) -> list[dict]:
        """Extract product names from query and retrieve their data."""
        if not query:
            return []
        results = self.retriever.retrieve(query, top_k=5)
        # TODO: Better product extraction logic (currently: top retrieval hits).
        return [r.get("metadata", {}) for r in results[:3]]
