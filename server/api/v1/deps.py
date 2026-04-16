from fastapi import Header, HTTPException, Request


async def get_account_id(x_account_id: str = Header(...)) -> str:
    """Extract the tenant account_id from the X-Account-ID request header."""
    if not x_account_id or not x_account_id.strip():
        raise HTTPException(status_code=400, detail="X-Account-ID header is required")
    return x_account_id.strip()


async def get_current_user(request: Request) -> dict:
    """
    Returns the authenticated user payload set by the auth middleware.
    Raises 401 if the request was not authenticated (should never happen
    if the middleware is correctly configured, but acts as a safety net).
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
