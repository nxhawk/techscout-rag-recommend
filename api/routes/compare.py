"""Compare Route - POST /api/compare"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_cached_compare_pipeline
from api.metrics import PIPELINE_LATENCY
from api.schemas import CompareRequest, CompareResponse
from src.guardrails import InputGuardrailBlocked
from src.pipeline.compare_pipeline import ComparePipeline
from src.utils.helpers import is_rate_limit_error

logger = logging.getLogger(__name__)

router = APIRouter()


def _error_detail(exc: Exception) -> str:
    """User-facing (Vietnamese) error message for a pipeline failure."""
    if is_rate_limit_error(exc):
        return "Hệ thống đã hết hạn mức gọi AI, vui lòng thử lại sau ít phút."
    return "Hệ thống so sánh đang gặp sự cố, vui lòng thử lại sau."


@router.post("/compare", response_model=CompareResponse)
def compare_products(
    request: CompareRequest,
    pipeline: ComparePipeline = Depends(get_cached_compare_pipeline),
) -> CompareResponse:
    """Run the comparison pipeline for a query and/or explicit product ids.

    Defined as a sync endpoint on purpose: the pipeline performs blocking
    I/O (vector DB + LLM calls), so FastAPI runs it in its threadpool
    instead of blocking the event loop.
    """
    try:
        with PIPELINE_LATENCY.labels(pipeline="compare").time():
            result = pipeline.run(request.query, product_ids=request.product_ids)
    except InputGuardrailBlocked as exc:
        logger.info("Compare blocked by input guardrail: %s", exc.reason)
        raise HTTPException(status_code=422, detail=exc.reason) from exc
    except Exception as exc:
        if is_rate_limit_error(exc):
            summary = str(exc).splitlines()[0][:300]
            logger.error(
                "Compare failed - provider quota/429 (query=%r): %s", request.query, summary
            )
        else:
            logger.exception("Compare pipeline failed for query: %s", request.query)
        raise HTTPException(status_code=503, detail=_error_detail(exc)) from exc

    if result.get("error"):
        # Business-rule guardrail: not enough valid products to compare.
        raise HTTPException(status_code=422, detail=result["error"])

    analysis = result.get("analysis") or {}
    return CompareResponse(
        comparison_table=result.get("comparison_table") or {},
        analysis=analysis,
        conclusion=analysis.get("conclusion", ""),
        warnings=result.get("warnings") or [],
    )
