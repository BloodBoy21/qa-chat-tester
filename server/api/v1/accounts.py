from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from lib.mongo import db
from db.repositories.account_repository import AccountRepository

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _repo() -> AccountRepository:
    return AccountRepository(db["accounts"])


class AccountCreate(BaseModel):
    account_id: str
    name: str
    description: str | None = None


class AccountUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


@router.get("")
async def list_accounts():
    return _repo().get_all()


@router.post("", status_code=201)
async def create_account(body: AccountCreate):
    repo = _repo()
    if repo.exists(body.account_id):
        raise HTTPException(status_code=409, detail=f"Account '{body.account_id}' already exists")
    return repo.create(
        account_id=body.account_id,
        name=body.name,
        description=body.description,
    )


@router.get("/{account_id}")
async def get_account(account_id: str):
    acc = _repo().get(account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    return acc


@router.patch("/{account_id}")
async def update_account(account_id: str, body: AccountUpdate):
    repo = _repo()
    if not repo.exists(account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    repo.update(account_id, **body.model_dump(exclude_none=True))
    return repo.get(account_id)


@router.delete("/{account_id}", status_code=200)
async def delete_account(account_id: str):
    repo = _repo()
    if not repo.exists(account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    repo.delete(account_id)
    return {"ok": True}
