"""Prometheus metrics wiring for the FastAPI app.

Exposes a Prometheus scrape endpoint at ``GET /metrics`` and registers the
default HTTP instrumentation (request counter, latency histogram, request/
response sizes) via ``prometheus-fastapi-instrumentator``, plus a couple of
RAG-specific collectors that the default HTTP metrics cannot express.

Prometheus scrapes ``/metrics`` on an interval; Grafana then queries Prometheus.
See ``docs/deployment/monitoring.md`` for the full flow and dashboard queries.
"""

from fastapi import FastAPI
from prometheus_client import Counter, Histogram
from prometheus_fastapi_instrumentator import Instrumentator

# Domain metric: recommend-pipeline failures split by reason, so a provider
# quota/429 spike (reason="quota") is visually distinct from other backend
# errors (reason="error") on the dashboard. The default per-endpoint status
# counter only shows "503" for both cases.
RECOMMEND_ERRORS = Counter(
    "rag_recommend_errors_total",
    "Recommend pipeline failures, labelled by failure reason.",
    ["reason"],
)

# Domain metric: end-to-end latency of the RAG pipelines (retrieval + rerank +
# LLM). Labelled by pipeline so recommend/compare/search can be compared. This
# isolates the "thinking" cost from the raw HTTP overhead measured by the
# default ``http_request_duration_seconds`` histogram.
PIPELINE_LATENCY = Histogram(
    "rag_pipeline_duration_seconds",
    "End-to-end RAG pipeline latency in seconds.",
    ["pipeline"],
    # Buckets tuned for LLM-backed calls (sub-second retrieval up to ~30s LLM).
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0),
)


def setup_metrics(app: FastAPI) -> None:
    """Instrument ``app`` and expose Prometheus metrics at ``GET /metrics``.

    Configuration choices:

    - ``should_group_status_codes=False`` keeps exact status codes (``200``,
      ``503`` …) instead of coarse ``2xx``/``5xx`` buckets, so error-rate
      queries can target ``status=~"5.."`` precisely.
    - ``should_ignore_untemplated=True`` drops requests to unmatched paths
      (random 404 probes) so the ``handler`` label stays bounded to real routes
      and series cardinality does not explode.
    """
    Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
