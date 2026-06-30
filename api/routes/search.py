"""Search Route - POST /api/search"""
from fastapi import APIRouter
from api.schemas import SearchRequest, SearchResponse

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def search_products(request: SearchRequest):
    """Tìm kiếm sản phẩm."""
    # TODO: Initialize retriever and search
    return SearchResponse(results=[], total=0)
