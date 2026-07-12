"""FastAPI Application - Entry point."""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from api.metrics import setup_metrics
from api.paths import PROJECT_ROOT, REQUIRED_CONFIG_PATHS
from api.routes.recommend import router as recommend_router
from api.routes.compare import router as compare_router
from api.routes.search import router as search_router
from api.routes.products import router as products_router

# Configure application logging (uvicorn only configures its own loggers).
# Short timestamps and one line per event keep the console readable.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

# Third-party libraries are chatty at INFO (HTTP request lines, retry
# internals, AFC notices). Keep them at WARNING so the console only shows
# application events.
for _noisy in (
    "httpx",
    "httpcore",
    "google_genai",
    "openai",
    "anthropic",
    "tenacity",
    "urllib3",
):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# Load environment variables from .env (API keys read lazily at request time).
load_dotenv()

logger = logging.getLogger(__name__)


def _validate_required_configs() -> None:
    """Fail fast at startup when config files are missing (e.g. wrong cwd)."""
    missing = [path for path in REQUIRED_CONFIG_PATHS if not path.is_file()]
    if not missing:
        return

    lines = "\n".join(f"  - {path}" for path in missing)
    raise RuntimeError(
        "Missing required config file(s):\n"
        f"{lines}\n"
        f"Project root: {PROJECT_ROOT}\n"
        f"Current working directory: {Path.cwd()}\n"
        "Run uvicorn from the repository root, for example:\n"
        "  cd /path/to/techscout-rag-recommend && uv run uvicorn api.app:app --reload"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_required_configs()
    logger.info("Startup config check passed (project root: %s)", PROJECT_ROOT)

    # Start the internal gRPC server (RecommendService) alongside HTTP. The
    # gateway talks to this over gRPC; REST stays available for health/metrics
    # and direct use. Disable with GRPC_ENABLED=false (e.g. in unit tests).
    grpc_server = None
    if os.getenv("GRPC_ENABLED", "true").lower() != "false":
        try:
            from src.grpc_server.server import serve_in_thread

            grpc_server = serve_in_thread()
        except Exception:  # noqa: BLE001 - never let gRPC startup break HTTP
            logger.exception("gRPC server failed to start")

    # Register {name, host, port, health} with the service-registry so the
    # gateway can look this instance up by name instead of a hardcoded addr.
    # Registered port is the gRPC port (what the gateway dials); health is the
    # HTTP health endpoint. No-op if REGISTRY_URL is unset.
    from src.registry.client import register_if_configured

    service_host = os.getenv("SERVICE_HOST", "rag-recommend")
    http_port = os.getenv("HTTP_PORT", "8000")
    grpc_port = int(os.getenv("GRPC_PORT", "50052"))
    registry_client = register_if_configured(
        name=os.getenv("SERVICE_NAME", "rag-recommend"),
        port=grpc_port,
        health=f"http://{service_host}:{http_port}/health",
    )

    try:
        yield
    finally:
        if grpc_server is not None:
            grpc_server.stop(grace=5)
        if registry_client is not None:
            await registry_client.stop()


app = FastAPI(
    title="RAG Product Recommendation & Comparison API",
    version="1.0.0",
    description="API gợi ý và so sánh sản phẩm dùng RAG",
    lifespan=lifespan,
)

app.include_router(recommend_router, prefix="/api", tags=["Recommend"])
app.include_router(compare_router, prefix="/api", tags=["Compare"])
app.include_router(search_router, prefix="/api", tags=["Search"])
app.include_router(products_router, prefix="/api", tags=["Products"])

# Expose Prometheus metrics at GET /metrics and instrument every route with the
# default HTTP request/latency collectors. Registered after the routers so the
# instrumentation middleware wraps them.
setup_metrics(app)


@app.get("/health")
def health_check():
    return {"status": "ok"}
