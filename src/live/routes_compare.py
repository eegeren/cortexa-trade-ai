from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional, Dict
from src.advice.compare_engine import compare_or_empty

router = APIRouter(prefix="/compare", tags=["compare"])

class CompareQuery(BaseModel):
    user_query: str = Field(..., example="BTC mi altın mı?")
    horizon: Optional[str] = Field("", example="6-12 ay")
    risk: Optional[str] = Field("", example="orta")
    capital: Optional[float] = Field(None, example=50000.0)
    stop_pct: Optional[float] = Field(None, example=0.06)

@router.post("", summary="Sorguda algılanan iki varlığı tablo halinde kıyaslar")
def compare(q: CompareQuery) -> Dict[str, str]:
    block = compare_or_empty(q.user_query, q.horizon, q.risk, q.capital, q.stop_pct) or ""
    return {"compare": block}
