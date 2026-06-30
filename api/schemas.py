"""API Schemas - Request/Response models."""
from pydantic import BaseModel


class RecommendRequest(BaseModel):
    query: str
    top_k: int = 5
    filters: dict | None = None

class RecommendResponse(BaseModel):
    recommendations: list[dict]
    summary: str = ""

class CompareRequest(BaseModel):
    query: str | None = None
    product_ids: list[str] | None = None

class CompareResponse(BaseModel):
    comparison_table: dict
    analysis: dict
    conclusion: str = ""

class SearchRequest(BaseModel):
    query: str
    filters: dict | None = None
    limit: int = 10

class SearchResponse(BaseModel):
    results: list[dict]
    total: int = 0
