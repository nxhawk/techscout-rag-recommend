"""Compare Route - POST /api/compare"""
from fastapi import APIRouter
from api.schemas import CompareRequest, CompareResponse

router = APIRouter()


@router.post("/compare", response_model=CompareResponse)
async def compare_products(request: CompareRequest):
    """So sánh sản phẩm."""
    # TODO: Initialize pipeline and run
    return CompareResponse(
        comparison_table={},
        analysis={},
        conclusion="Pipeline chưa được khởi tạo.",
    )
