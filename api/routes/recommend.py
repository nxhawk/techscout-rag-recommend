"""Recommend Route - POST /api/recommend"""
from fastapi import APIRouter
from api.schemas import RecommendRequest, RecommendResponse

router = APIRouter()


@router.post("/recommend", response_model=RecommendResponse)
async def recommend_products(request: RecommendRequest):
    """Gợi ý sản phẩm dựa trên nhu cầu người dùng."""
    # TODO: Initialize pipeline and run
    return RecommendResponse(
        recommendations=[],
        summary="Pipeline chưa được khởi tạo.",
    )
