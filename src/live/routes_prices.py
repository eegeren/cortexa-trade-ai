from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Dict, Tuple, Optional
import math

from src.advice.assets import get_asset
from src.advice.price_feeds import fetch_live_prices

router = APIRouter(prefix="/prices", tags=["prices"])

class PricesQuery(BaseModel):
    assets: List[str] = Field(..., example=["btc", "xau", "eur", "usd"])

class PriceEntry(BaseModel):
    price: Optional[float] = None
    change_pct: Optional[float] = None
    src: Optional[str] = None

class PricesResponse(BaseModel):
    snapshot: Dict[str, PriceEntry]

def _clean_num(x) -> Optional[float]:
    try:
        v = float(x)
        if math.isfinite(v):
            # İstersen yuvarlayabilirsin:
            return round(v, 6)
        return None
    except Exception:
        return None

def _sanitize_snapshot(raw: Dict[str, Dict[str, float]]) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for k, v in (raw or {}).items():
        out[k] = {
            "price": _clean_num(v.get("price")),
            "change_pct": _clean_num(v.get("change_pct")),
            "src": v.get("src")
        }
    return out

@router.post("", response_model=PricesResponse, summary="Seçilen varlıklar için canlı fiyat döndürür")
def prices(q: PricesQuery) -> PricesResponse:
    items: List[Tuple[str, str, str]] = []
    for key in q.assets[:12]:  # basit limit
        a = get_asset(key)
        if not a:
            continue
        feed, code = a.get("feed"), a.get("code")
        if feed and code:
            items.append((key, feed, code))
    raw = fetch_live_prices(items) if items else {}
    clean = _sanitize_snapshot(raw)
    return PricesResponse(snapshot=clean)