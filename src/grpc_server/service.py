"""RecommendService gRPC servicer.

Delegates to the same cached pipelines the HTTP routes use, so gRPC and REST
share one implementation.
"""
import logging

import grpc

from src.grpc_gen.techscout.recommend.v1 import recommend_pb2, recommend_pb2_grpc

logger = logging.getLogger(__name__)


def _sources_from_recommendations(items) -> list:
    sources = []
    for r in items or []:
        if not isinstance(r, dict):
            continue
        sources.append(
            recommend_pb2.Source(
                id=str(r.get("id") or r.get("product_id") or ""),
                title=str(r.get("name") or r.get("title") or ""),
                score=float(r.get("score") or 0.0),
            )
        )
    return sources


class RecommendServicer(recommend_pb2_grpc.RecommendServiceServicer):
    def Recommend(self, request, context):
        try:
            from api.deps import get_cached_recommend_pipeline

            pipeline = get_cached_recommend_pipeline()
            result = pipeline.run(request.query, top_k=request.top_k or 5)
        except Exception as exc:  # noqa: BLE001 - surface as gRPC status
            logger.exception("gRPC Recommend failed")
            context.abort(grpc.StatusCode.INTERNAL, str(exc))
            return recommend_pb2.RecommendResponse()
        answer = result.get("summary") or result.get("text") or ""
        return recommend_pb2.RecommendResponse(
            answer=answer,
            sources=_sources_from_recommendations(result.get("recommendations")),
        )

    def Compare(self, request, context):
        try:
            from api.deps import get_cached_compare_pipeline

            pipeline = get_cached_compare_pipeline()
            result = pipeline.run(request.query, product_ids=list(request.product_ids))
        except Exception as exc:  # noqa: BLE001
            logger.exception("gRPC Compare failed")
            context.abort(grpc.StatusCode.INTERNAL, str(exc))
            return recommend_pb2.CompareResponse()
        analysis = result.get("analysis") or {}
        answer = analysis.get("conclusion") or result.get("conclusion") or ""
        return recommend_pb2.CompareResponse(answer=answer, sources=[])
