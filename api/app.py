"""FastAPI Application - Entry point."""
from fastapi import FastAPI
from api.routes.recommend import router as recommend_router
from api.routes.compare import router as compare_router
from api.routes.search import router as search_router

app = FastAPI(
    title="RAG Product Recommendation & Comparison API",
    version="1.0.0",
    description="API gợi ý và so sánh sản phẩm dùng RAG",
)

app.include_router(recommend_router, prefix="/api", tags=["Recommend"])
app.include_router(compare_router, prefix="/api", tags=["Compare"])
app.include_router(search_router, prefix="/api", tags=["Search"])


@app.get("/health")
def health_check():
    return {"status": "ok"}
