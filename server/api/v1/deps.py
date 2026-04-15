from fastapi import Header, HTTPException


async def get_account_id(x_account_id: str = Header(...)) -> str:
    """
    Extract the tenant account_id from the X-Account-ID request header.
    All endpoints that touch MongoDB data require this header.
    """
    if not x_account_id or not x_account_id.strip():
        raise HTTPException(status_code=400, detail="X-Account-ID header is required")
    return x_account_id.strip()
