from fastapi import APIRouter
from src.dbutils import mark_provider_verified

router = APIRouter()

@router.get("/verify")
async def verify(provider_id: int):
    mark_provider_verified(provider_id, source="link_click")
    return {"status": "verified", "provider_id": provider_id}
