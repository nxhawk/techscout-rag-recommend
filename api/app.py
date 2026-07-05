"""FastAPI Application - Entry point."""
import logging

from dotenv import load_dotenv
from fastapi import FastAPI
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

app = FastAPI(
    title="RAG Product Recommendation & Comparison API",
    version="1.0.0",
    description="API gợi ý và so sánh sản phẩm dùng RAG",
)

app.include_router(recommend_router, prefix="/api", tags=["Recommend"])
app.include_router(compare_router, prefix="/api", tags=["Compare"])
app.include_router(search_router, prefix="/api", tags=["Search"])
app.include_router(products_router, prefix="/api", tags=["Products"])


@app.get("/health")
def health_check():
    return {"status": "ok"}
