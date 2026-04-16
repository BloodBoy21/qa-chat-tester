import math
from fastapi import Query


def page_params(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=200, description="Items per page"),
):
    return {"page": page, "page_size": page_size, "skip": (page - 1) * page_size}


def make_page(items: list, total: int, page: int, page_size: int) -> dict:
    pages = max(1, math.ceil(total / page_size)) if total > 0 else 1
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }
