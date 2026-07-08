"""FastAPI Application - Entry point."""
import logging
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
        "  cd /path/to/rag-product-recommend && uv run uvicorn api.app:app --reload"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_required_configs()
    logger.info("Startup config check passed (project root: %s)", PROJECT_ROOT)
    yield


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
