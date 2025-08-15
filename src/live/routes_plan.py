from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional, Dict
from src.advice.assets import get_asset, detect_assets_in_text, default_stop_for

router = APIRouter(prefix="/plan", tags=["plan"])

class PlanQuery(BaseModel):
    user_query: str = Field(..., example="BTC mi altın mı?")
    capital: float = Field(..., example=50000.0, description="Toplam sermaye")
    risk_per_trade: float = Field(0.01, example=0.01, description="Pozisyon başına risk (sermaye oranı)")
    dca_steps: int = Field(6, ge=1, le=24, description="Kademeli alım adedi")
    stop_pct: Optional[float] = Field(None, example=0.06, description="Stop mesafesi (0.06=%6). Boşsa varlığa göre varsayılan.")

@router.post("", summary="DCA programı ve örnek pozisyon boyutu")
def plan(q: PlanQuery) -> Dict:
    keys = detect_assets_in_text(q.user_query)
    sel = keys[:1]  # basit: ilk varlık için plan
    if not sel:
        return {"message": "Sorguda tanınan bir varlık yok.", "plan": {}}

    key = sel[0]
    a = get_asset(key)
    if not a:
        return {"message": f"'{key}' varlık profili bulunamadı.", "plan": {}}

    sp = q.stop_pct if q.stop_pct is not None else default_stop_for(key)
    dca_per_installment = q.capital / q.dca_steps
    pos_risk_cash = q.capital * q.risk_per_trade
    # Birim fiyat bilinmiyor; miktar örneğini fiyat girdisi olmadan veremeyiz.
    # Yine de riskten bağımsız pozisyon_tutarı üst sınırını örnekleyelim:
    # (Bu tutarı kullanıcı fiyatla bölerek miktarı kendi hesaplar.)
    pos_size_cash_cap = pos_risk_cash / max(sp, 1e-9)

    meta = {
        "asset": key.upper(),
        "default_stop": sp,
        "risk_per_trade": q.risk_per_trade,
        "capital": q.capital,
    }
    dca = {
        "steps": q.dca_steps,
        "per_installment_cash": round(dca_per_installment, 2),
        "hint": "Her adımı aynı takvim gününde (örn. ayın 5/15’i) yap ve üç ardışık zarar sonrası 1 kademe ara ver."
    }
    sizing = {
        "position_cash_limit_by_risk": round(pos_size_cash_cap, 2),
        "formula": "position_cash ≈ (capital × risk_per_trade) / stop_pct",
        "note": "Miktar için: position_cash / entry_price. Stop mesafesini varlığın oynaklığına göre ayarla."
    }
    return {"message": "ok", "meta": meta, "dca": dca, "sizing": sizing}
