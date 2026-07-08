"""
Recommend Pipeline - Pipeline gợi ý sản phẩm end-to-end.
Query → [Input Guardrail] → Intent Parser → Filter → Retrieve → Score → Rank
      → [Context Guardrail] → Prompt → LLM → [Output Guardrail] → Response
"""

import logging
import time

from src.generation.llm_client import LLMClient
from src.generation.prompt_templates.recommend_prompt import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)
from src.generation.response_parser import ResponseParser
from src.guardrails import (
    GuardrailConfig,
    InputGuardrailBlocked,
    build_input_chain,
    build_recommend_fallback,
    ground_recommendations,
    log_guardrail_event,
    sanitize_text_field,
    validate_recommend_output,
)
from src.pipeline.recommend.engine import RecommendEngine

logger = logging.getLogger(__name__)


class RecommendPipeline:
    """End-to-end recommendation pipeline."""

    def __init__(
        self,
        recommend_engine: RecommendEngine,
        llm_client: LLMClient,
        guardrail_config: GuardrailConfig | None = None,
    ):
        self.recommend_engine = recommend_engine
        self.llm_client = llm_client
        self.parser = ResponseParser()
        self.guardrail_config = guardrail_config or GuardrailConfig()
        self.input_chain = build_input_chain(self.guardrail_config)

    def run(self, query: str, top_k: int = 5) -> dict:
        """Run the full recommendation pipeline.

        Raises:
            InputGuardrailBlocked: the query was rejected by an input
                guardrail (blank/too long/prompt-injection/etc). Callers
                (API routes) should map this to an HTTP 4xx.
        """
        # Step 0: Input guardrail - reject or sanitize the raw query first.
        input_result = self.input_chain.run(query)
        if input_result.blocked:
            log_guardrail_event(
                logger,
                stage="input",
                action="block",
                reason=input_result.reason,
                level=logging.WARNING,
                pipeline="recommend",
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
                pipeline="recommend",
                warnings=input_result.warnings,
            )
        query = input_result.sanitized_text or query
        warnings: list[str] = list(input_result.warnings)

        # Step 1: Get recommendations with scores
        t0 = time.perf_counter()
        result = self.recommend_engine.recommend(query, top_k=top_k)
        t_retrieve = time.perf_counter() - t0

        # Step 2: Build context for LLM (context guardrail sanitizes each field)
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
        t1 = time.perf_counter()
        llm_response = self.llm_client.generate(
            prompt, system_prompt=SYSTEM_PROMPT, json_output=True
        )
        t_llm = time.perf_counter() - t1

        # Step timings make slow requests diagnosable from the server log.
        logger.info(
            "Recommend pipeline done: retrieve=%.2fs llm=%.2fs candidates=%d",
            t_retrieve,
            t_llm,
            len(result["recommendations"]),
        )

        # Step 4: Output guardrail - schema validation, then grounding.
        parsed = self._guarded_output(llm_response, result["recommendations"], top_k, warnings)
        parsed["retrieved_products"] = result["recommendations"]
        parsed["warnings"] = warnings
        return parsed

    def _guarded_output(
        self,
        llm_response: str,
        retrieved_products: list[dict],
        top_k: int,
        warnings: list[str],
    ) -> dict:
        output_result = validate_recommend_output(llm_response)
        if output_result.blocked:
            log_guardrail_event(
                logger,
                stage="output",
                action="block",
                reason=output_result.reason,
                level=logging.WARNING,
                pipeline="recommend",
            )
            warnings.append("LLM tra ve du lieu khong hop le, da su dung ket qua goi y du phong.")
            return build_recommend_fallback(retrieved_products, top_k)

        payload = output_result.sanitized_payload or {}
        raw_items = payload.get("recommendations", [])
        grounded_items, ground_warnings = ground_recommendations(raw_items, retrieved_products)
        if ground_warnings:
            log_guardrail_event(
                logger,
                stage="output",
                action="sanitize",
                pipeline="recommend",
                warnings=ground_warnings,
            )
            warnings.extend(ground_warnings)

        if raw_items and not grounded_items:
            # Every item hallucinated a product that was never retrieved.
            warnings.append(
                "Toan bo goi y tu LLM khong khop du lieu san pham, da su dung ket qua du phong."
            )
            return build_recommend_fallback(retrieved_products, top_k)

        return {"recommendations": grounded_items, "summary": payload.get("summary", "")}

    def _build_context(self, products: list[dict]) -> str:
        cfg = self.guardrail_config
        lines = []
        for i, p in enumerate(products[: cfg.max_context_products], 1):
            meta = p.get("metadata", {})
            name = sanitize_text_field(meta.get("name", "N/A"), max_len=200) or "N/A"
            brand = sanitize_text_field(meta.get("brand", ""), max_len=100)
            lines.append(
                f"{i}. {name} - {brand} "
                f"| Giá: {meta.get('price', 'N/A')} | Rating: {meta.get('avg_rating', 'N/A')} "
                f"| Score: {p.get('final_score', p.get('score', 0))}"
            )
            document = sanitize_text_field(
                p.get("document", ""), max_len=cfg.max_context_field_chars
            )
            if document:
                lines.append(f"   Chi tiết: {document}")
        return "\n".join(lines)
