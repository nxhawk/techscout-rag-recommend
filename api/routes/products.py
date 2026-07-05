"""Products Route - CRUD on the source-of-truth catalog.

Writes go ONLY to the ``product_catalog`` table. Debezium (CDC) picks the
change up from the WAL and the sync workers propagate it to Elasticsearch
and pgvector - handlers here never touch the search indexes directly, so
the two indexes can never be updated out of order.

Endpoints are sync (blocking DB I/O runs in FastAPI's threadpool).
"""

import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_cached_product_repository
from api.schemas import (
    ProductCreateRequest,
    ProductListResponse,
    ProductMutationResponse,
    ProductResponse,
    ProductUpdateRequest,
)
from src.catalog.product_repository import ProductRepository

logger = logging.getLogger(__name__)

router = APIRouter()

_SYNC_NOTE = "Dữ liệu tìm kiếm sẽ được đồng bộ trong giây lát."


def _generate_product_id(name: str) -> str:
    """Slug from the name + short random suffix (collision-safe)."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48] or "product"
    return f"{slug}-{uuid.uuid4().hex[:8]}"


@router.post("/products", response_model=ProductMutationResponse, status_code=201)
def create_product(
    request: ProductCreateRequest,
    repo: ProductRepository = Depends(get_cached_product_repository),
) -> ProductMutationResponse:
    """Tạo sản phẩm mới trong catalog (source of truth)."""
    product = request.model_dump()
    product["product_id"] = request.product_id or _generate_product_id(request.name)
    created = repo.create(product)
    if not created:
        raise HTTPException(
            status_code=409,
            detail=f"Sản phẩm '{product['product_id']}' đã tồn tại.",
        )
    logger.info("Catalog: created product %s", product["product_id"])
    return ProductMutationResponse(
        product_id=product["product_id"],
        message=f"Đã tạo sản phẩm. {_SYNC_NOTE}",
    )


@router.put("/products/{product_id}", response_model=ProductMutationResponse)
def update_product(
    product_id: str,
    request: ProductUpdateRequest,
    repo: ProductRepository = Depends(get_cached_product_repository),
) -> ProductMutationResponse:
    """Cập nhật sản phẩm (partial update - chỉ các trường được gửi lên)."""
    fields = request.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=422, detail="Không có trường nào để cập nhật.")
    updated = repo.update(product_id, fields)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy sản phẩm '{product_id}'.")
    logger.info("Catalog: updated product %s (fields=%s)", product_id, sorted(fields))
    return ProductMutationResponse(
        product_id=product_id,
        message=f"Đã cập nhật sản phẩm. {_SYNC_NOTE}",
    )


@router.delete("/products/{product_id}", response_model=ProductMutationResponse)
def delete_product(
    product_id: str,
    repo: ProductRepository = Depends(get_cached_product_repository),
) -> ProductMutationResponse:
    """Xóa sản phẩm khỏi catalog (CDC sẽ gỡ khỏi các index tìm kiếm)."""
    deleted = repo.delete(product_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy sản phẩm '{product_id}'.")
    logger.info("Catalog: deleted product %s", product_id)
    return ProductMutationResponse(
        product_id=product_id,
        message=f"Đã xóa sản phẩm. {_SYNC_NOTE}",
    )


@router.get("/products/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: str,
    repo: ProductRepository = Depends(get_cached_product_repository),
) -> ProductResponse:
    """Lấy thông tin một sản phẩm."""
    product = repo.get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy sản phẩm '{product_id}'.")
    return ProductResponse(product=product)


@router.get("/products", response_model=ProductListResponse)
def list_products(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    repo: ProductRepository = Depends(get_cached_product_repository),
) -> ProductListResponse:
    """Liệt kê sản phẩm trong catalog (phân trang)."""
    return ProductListResponse(
        products=repo.list_products(limit=limit, offset=offset),
        total=repo.count(),
    )
