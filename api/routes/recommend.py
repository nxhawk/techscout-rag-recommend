"""Recommend Route - POST /api/recommend"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_cached_recommend_pipeline
from api.metrics import PIPELINE_LATENCY, RECOMMEND_ERRORS
from api.schemas import RecommendRequest, RecommendResponse
from src.guardrails import InputGuardrailBlocked
from src.pipeline.recommend_pipeline import RecommendPipeline
from src.utils.helpers import is_rate_limit_error

logger = logging.getLogger(__name__)

router = APIRouter()


def _log_pipeline_error(query: str, exc: Exception) -> None:
    """Log pipeline failures without flooding the console.

    Expected provider errors (rate limit / quota) are summarized on a single
    line; only unexpected errors keep the full traceback for debugging.
    """
    if is_rate_limit_error(exc):
        summary = str(exc).splitlines()[0][:300]
        logger.error("Recommend failed - provider quota/429 (query=%r): %s", query, summary)
    else:
        logger.exception("Recommend pipeline failed for query: %s", query)


def _error_detail(exc: Exception) -> str:
    """User-facing (Vietnamese) error message for a pipeline failure."""
    if is_rate_limit_error(exc):
        return "Hệ thống đã hết hạn mức gọi AI, vui lòng thử lại sau ít phút."
    return "Hệ thống gợi ý đang gặp sự cố, vui lòng thử lại sau."


@router.post("/recommend", response_model=RecommendResponse)
def recommend_products(
    request: RecommendRequest,
    pipeline: RecommendPipeline = Depends(get_cached_recommend_pipeline),
) -> RecommendResponse:
    """Run the recommendation pipeline for a natural-language query.

    Defined as a sync endpoint on purpose: the pipeline performs
    blocking I/O (vector DB + LLM calls), so FastAPI runs it in its
    threadpool instead of blocking the event loop.
    """
    try:
        # Time the whole pipeline (retrieval + rerank + LLM) so the dashboard
        # can separate "thinking" latency from raw HTTP overhead.
        with PIPELINE_LATENCY.labels(pipeline="recommend").time():
            result = pipeline.run(request.query, top_k=request.top_k)
    except InputGuardrailBlocked as exc:
        # Business-rule input guardrail (injection/heuristics) rejected the
        # query. Schema-level issues (blank/too long) are already caught by
        # RecommendRequest validators as a plain 422 before we get here.
        logger.info("Recommend blocked by input guardrail: %s", exc.reason)
        RECOMMEND_ERRORS.labels(reason="guardrail_input").inc()
        raise HTTPException(status_code=422, detail=exc.reason) from exc
    except Exception as exc:
        _log_pipeline_error(request.query, exc)
        # Split quota/429 from other backend failures for the error panel.
        RECOMMEND_ERRORS.labels(reason="quota" if is_rate_limit_error(exc) else "error").inc()
        raise HTTPException(status_code=503, detail=_error_detail(exc)) from exc

    # The LLM returns {"recommendations": [...], "summary": "..."} per the
    # prompt contract; on unparseable output the parser falls back to
    # {"text": "...", "structured": False}. The output guardrail (schema +
    # grounding) inside the pipeline already replaced malformed/ungrounded
    # output with a deterministic fallback, so this stays a plain 200.
    recommendations = result.get("recommendations") or []
    summary = result.get("summary") or result.get("text") or ""
    warnings = result.get("warnings") or []
    return RecommendResponse(recommendations=recommendations, summary=summary, warnings=warnings)
