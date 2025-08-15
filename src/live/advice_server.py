# src/live/advice_server.py
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Optional, List, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.staticfiles import StaticFiles

# ---- Guardrails / metin blokları ----
from src.advice.guardrails import (
    build_intro,
    options_section,
    sample_portfolios,
    action_checklist,
    PROFILE_QUESTIONS,
    tailor_by_profile,
    topic_compare,
    build_dca_risk_plan,
    build_brief_answer,
    detect_leverage_intent,
    build_leverage_answer,
)

# ---- Varlık sözlüğü ve tespit ----
from src.advice.assets import (
    detect_assets_in_text,
    default_stop_for,
)

# ---- Canlı fiyat beslemeleri ----
from src.advice.price_feeds import (
    map_assets_to_feed_codes,
    fetch_live_prices_cached,
    format_live_table,
)

# ---- Kaldıraç modülü ----
from src.advice.leverage import (
    parse_leverage_from_text,
    LeverageInputs,
    build_leverage_plan,
    format_leverage_markdown,
)

# -----------------------------------------------------------------------------
# Uygulama
# -----------------------------------------------------------------------------
app = FastAPI(title="Cortexa Advice API")

# CORS (geliştirme için açık; prod’da originleri sınırlayabilirsiniz)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Web dosyaları — / ve SPA fallback için
# -----------------------------------------------------------------------------
WEB_DIR = (Path(__file__).resolve().parents[2] / "web").resolve()
INDEX_FILE = (WEB_DIR / "index.html").resolve()
print(f"[boot] WEB_DIR={WEB_DIR} exists={WEB_DIR.exists()} index={INDEX_FILE.exists()}")

assets_dir = WEB_DIR / "assets"
if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

# -----------------------------------------------------------------------------
# Şemalar
# -----------------------------------------------------------------------------
class AdviceQuery(BaseModel):
    user_query: str = Field(..., example="btc vs euro (6 ay, orta risk, 100k, %2 stop)")
    goal: Optional[str] = ""
    horizon: Optional[str] = ""
    risk: Optional[str] = ""
    capital: Optional[float] = None
    stop_pct: Optional[float] = None
    show_prices: Optional[bool] = True
    # Terms onaylandıysa UI bunu true yollar; bu durumda üstteki uyarı metni bastırılır
    suppress_disclaimer: Optional[bool] = False

class PriceQuery(BaseModel):
    assets: List[str] = Field(..., example=["btc", "xau", "usd", "eur"])

class AssetSnapshot(BaseModel):
    price: float
    change_pct: float
    src: str

class SnapshotResponse(BaseModel):
    snapshot: Dict[str, AssetSnapshot]

class PlanQuery(BaseModel):
    user_query: str
    capital: float = Field(..., example=50000.0)
    risk_per_trade: float = Field(0.01, example=0.02)
    dca_steps: int = Field(6, ge=1, le=24)
    stop_pct: Optional[float] = Field(None, example=0.06)
    use_live_price: bool = True

class CompareQuery(BaseModel):
    user_query: str
    horizon: Optional[str] = ""
    risk: Optional[str] = ""
    capital: Optional[float] = None
    stop_pct: Optional[float] = None

class LeverageQuery(BaseModel):
    user_query: str = Field(..., example="btc kaldıraç 5x, 100k sermaye, %2 stop")
    capital: float = Field(..., example=100000.0)
    risk_per_trade: float = Field(0.01, example=0.01, description="0.01 = %1")
    stop_pct: Optional[float] = Field(None, example=0.02, description="0.02 = %2")
    leverage: Optional[int] = Field(None, ge=1, le=50)
    maintenance_margin: float = Field(0.01, description="Yaklaşık bakım marjı (varsayılan %1)")
    use_live_price: bool = True

# -----------------------------------------------------------------------------
# Yardımcılar
# -----------------------------------------------------------------------------
def _live_block_for_query_text(text: str) -> str:
    keys = detect_assets_in_text(text)
    if not keys:
        return ""
    items = map_assets_to_feed_codes(keys)
    if not items:
        return ""
    snap = fetch_live_prices_cached(items, ttl=15)
    return format_live_table(snap)

def _is_gibberish_or_unknown(q: str) -> bool:
    """Tamamen alakasız / varlık tespit edilemeyen kısa girdiler için filtre."""
    if not q or len(q.strip()) < 2:
        return True
    assets = detect_assets_in_text(q)
    if assets:
        return False
    keywords = [
        "altın", "xau", "gümüş", "xag", "petrol", "wti",
        "hisse", "endeks", "sp500", "nasdaq",
        "btc", "bitcoin", "eth", "ethereum", "sol", "solana", "kripto",
        "dolar", "usd", "euro", "eur", "tahvil", "bono", "faiz", "döviz",
        "usdtry", "eurtry", "kaldıraç", "leverage", "x"
    ]
    ql = q.lower()
    return not any(k in ql for k in keywords)

_NUM_RE = re.compile(r"(\d+(?:[\.,]\d+)?)")

def _parse_inline_params(text: str) -> dict:
    """
    Metinden 'risk', 'capital' (k/m), 'stop_pct (%x veya 0.x)' çıkarır.
    """
    out = {"risk": "", "capital": None, "stop_pct": None}
    if not text:
        return out
    t = text.lower()

    # risk
    if "düşük" in t or "dusuk" in t or "low" in t:
        out["risk"] = "dusuk"
    elif "yüksek" in t or "yuksek" in t or "high" in t:
        out["risk"] = "yuksek"
    elif "orta" in t or "medium" in t:
        out["risk"] = "orta"

    # capital (…k / …m destekli)
    cap = None
    m = re.search(r"(\d+(?:[\.,]\d+)?)(\s*[kKmM])", t)
    if m:
        val = float(m.group(1).replace(",", "."))
        suf = m.group(2).strip().lower()
        cap = val * (1_000 if suf == "k" else 1_000_000)
    else:
        m2 = re.search(r"\b(\d{5,})\b", t)  # 5+ hane düz sayı
        if m2:
            cap = float(m2.group(1))
    out["capital"] = cap

    # stop: “%1.5” ya da “0.015”
    ms = re.search(r"%\s*(\d+(?:[\.,]\d+)?)", t)
    if ms:
        out["stop_pct"] = float(ms.group(1).replace(",", ".")) / 100.0
    else:
        ms2 = re.search(r"\b0[\.,]\d+\b", t)
        if ms2:
            out["stop_pct"] = float(ms2.group(0).replace(",", "."))

    return out

# -----------------------------------------------------------------------------
# Sağlık
# -----------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True}

# -----------------------------------------------------------------------------
# /advice
# -----------------------------------------------------------------------------
@app.post("/advice")
def advice(q: AdviceQuery) -> Dict[str, str]:
    # 1) Geçersiz / alakasız giriş reddi
    if _is_gibberish_or_unknown(q.user_query):
        guide = (
            "**Geçersiz/eksik istek** — şu formatta deneyebilirsin:\n"
            "- `btc kaldıraçlı (orta risk, 50k, %1.5 stop)`\n"
            "- `eth kaldıraçlı (yüksek risk, 2m, %1 stop)`\n"
            "- `btc vs euro (6 ay, orta risk, 100k, %2 stop)`\n"
        )
        return {"answer": guide}

    # 2) KALDIRAÇLI kısa cevap modu
    if detect_leverage_intent(q.user_query):
        keys = detect_assets_in_text(q.user_query) or []
        asset_key = keys[0] if keys else "btc"

        inline = _parse_inline_params(q.user_query)
        risk = q.risk or inline["risk"] or "orta"
        capital = q.capital if q.capital is not None else inline["capital"] or 0.0
        stop_pct = q.stop_pct if q.stop_pct is not None else inline["stop_pct"]
        if stop_pct is None:
            stop_pct = max(default_stop_for(asset_key) / 2, 0.005)  # kaldıraçta daraltma

        entry_price = None
        try:
            items = map_assets_to_feed_codes([asset_key])
            snap = fetch_live_prices_cached(items, ttl=15) if items else {}
            entry_price = snap.get(asset_key, {}).get("price")
        except Exception:
            pass

        header = (f"**Soru:** {q.user_query}\n\n") if q.suppress_disclaimer else build_intro(q.user_query)

        short = build_leverage_answer(
            asset_key=asset_key,
            risk=risk,
            capital=capital,
            stop_pct=stop_pct,
            entry_price=entry_price,
        )

        live_tbl = _live_block_for_query_text(asset_key) if q.show_prices else ""
        answer = header + short + (("\n" + live_tbl) if live_tbl else "")
        return {"answer": answer}

    # 3) Klasik akış
    intro = f"**Soru:** {q.user_query}\n\n" if q.suppress_disclaimer else build_intro(q.user_query)
    brief = build_brief_answer(q.user_query, q.horizon, q.risk, q.capital, q.stop_pct)
    opts = options_section()
    topic = topic_compare(q.user_query)
    live_tbl = _live_block_for_query_text(q.user_query) if q.show_prices else ""
    tailoring = tailor_by_profile(q.goal, q.horizon, q.risk)
    plan = build_dca_risk_plan(q.user_query, q.horizon, q.risk, q.capital, q.stop_pct)
    questions = "\n".join(PROFILE_QUESTIONS)

    body = (
        f"{intro}"
        f"{brief}\n"
        f"---\nSEÇENEKLER ÖZETİ (kısa):\n{opts}\n"
        f"{topic}"
        f"{live_tbl}\n"
        f"---\nPROFİLİNİZE GÖRE NOTLAR (kısa):\n{tailoring}\n\n"
        f"{plan}\n\n"
        f"{sample_portfolios()}\n"
        f"{action_checklist()}\n"
        f"Profil soruları:\n{questions}\n"
    )
    return {"answer": body}

# -----------------------------------------------------------------------------
# /prices
# -----------------------------------------------------------------------------
@app.post("/prices", response_model=SnapshotResponse)
def prices(p: PriceQuery):
    items = map_assets_to_feed_codes(p.assets or [])
    snap = fetch_live_prices_cached(items, ttl=15) if items else {}
    return {"snapshot": snap}

# -----------------------------------------------------------------------------
# /plan
# -----------------------------------------------------------------------------
@app.post("/plan")
def plan(p: PlanQuery) -> Dict[str, object]:
    keys = detect_assets_in_text(p.user_query) or []
    asset_key = keys[0] if keys else "btc"
    stop_pct = p.stop_pct if p.stop_pct is not None else default_stop_for(asset_key)
    pos_cash = (p.capital * p.risk_per_trade) / max(stop_pct, 1e-9)

    qty = None
    entry_price = None
    if p.use_live_price:
        items = map_assets_to_feed_codes([asset_key])
        snap = fetch_live_prices_cached(items, ttl=15) if items else {}
        v = snap.get(asset_key, {})
        entry_price = v.get("price", None)
        if entry_price and entry_price > 0:
            qty = pos_cash / entry_price

    resp = {
        "message": "ok",
        "meta": {
            "asset": asset_key.upper(),
            "default_stop": stop_pct,
            "risk_per_trade": p.risk_per_trade,
            "capital": float(p.capital),
        },
        "dca": {
            "steps": int(p.dca_steps),
            "per_installment_cash": round(p.capital / max(p.dca_steps, 1), 2),
            "hint": "Her adımı aynı takvim gününde (örn. ayın 5/15’i) yap ve üç ardışık zarar sonrası 1 kademe ara ver.",
        },
        "sizing": {
            "position_cash_limit_by_risk": round(pos_cash, 2),
            "formula": "position_cash ≈ (capital × risk_per_trade) / stop_pct",
            "note": "Miktar için: position_cash / entry_price. Stop mesafesini varlığın oynaklığına göre ayarla.",
        },
    }

    if entry_price:
        resp["market"] = {"entry_price": round(float(entry_price), 6)}
    if qty:
        resp["sizing"]["quantity_estimate"] = round(float(qty), 8)

    return resp

# -----------------------------------------------------------------------------
# /compare
# -----------------------------------------------------------------------------
@app.post("/compare")
def compare_assets(p: CompareQuery) -> Dict[str, str]:
    keys = detect_assets_in_text(p.user_query)
    keys = list(dict.fromkeys(keys))  # uniq
    if len(keys) < 2:
        return {"compare": "**Kıyas için iki varlık tespit edilemedi.**"}

    a, b = keys[:2]
    items = map_assets_to_feed_codes([a, b])
    snap = fetch_live_prices_cached(items, ttl=15) if items else {}
    live_tbl = format_live_table(snap) if snap else ""

    table = (
        "**Hızlı Karşılaştırma (genel bilgi, tavsiye değildir):**\n\n"
        "| Özellik | A | B |\n"
        "|---|---|---|\n"
        f"| Varlık | {a.upper()} | {b.upper()} |\n"
        "| Sınıf | — | — |\n"
        "| Rol | — | — |\n"
        "| Volatilite | — | — |\n"
        "| Getiri Kaynağı | — | — |\n"
        "| Likidite | — | — |\n"
        "| Portföy Aralığı | — | — |\n\n"
        "– Oynaklığı yüksek tarafa ayrılan payı düşük tut; DCA ve pozisyon başına risk limiti uygula.\n"
    )

    return {"compare": table + (("\n" + live_tbl) if live_tbl else "")}

# -----------------------------------------------------------------------------
# /leverage
# -----------------------------------------------------------------------------
@app.post("/leverage")
def leverage_endpoint(p: LeverageQuery) -> Dict[str, str]:
    keys = detect_assets_in_text(p.user_query) or []
    asset_key = keys[0] if keys else "btc"

    stop_pct = p.stop_pct if p.stop_pct is not None else default_stop_for(asset_key)
    lev = p.leverage if p.leverage else parse_leverage_from_text(p.user_query)

    entry_price = None
    if p.use_live_price:
        items = map_assets_to_feed_codes([asset_key])
        snap = fetch_live_prices_cached(items, ttl=15) if items else {}
        entry_price = (snap.get(asset_key, {}) or {}).get("price")

    plan = build_leverage_plan(LeverageInputs(
        asset_key=asset_key,
        capital=p.capital,
        risk_per_trade=p.risk_per_trade,
        stop_pct=stop_pct,
        leverage=lev,
        entry_price=entry_price,
        maintenance_margin=p.maintenance_margin,
    ))

    text = format_leverage_markdown(asset_key, entry_price, plan, lev)
    return {"text": text}

# -----------------------------------------------------------------------------
# Web: Root ve SPA fallback
# -----------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def serve_index_root():
    if INDEX_FILE.exists():
        return FileResponse(str(INDEX_FILE), media_type="text/html; charset=utf-8")
    # Web dosyası yoksa basit durum cevabı
    return {"ok": True, "service": "Cortexa Advice API", "index_found": False, "index_path": str(INDEX_FILE)}

@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    # API yollarına karışma
    api_prefixes = {"advice", "prices", "plan", "compare", "leverage", "health"}
    first = (full_path or "").split("/", 1)[0]
    if first in api_prefixes:
        raise HTTPException(status_code=404, detail="API path")

    if INDEX_FILE.exists():
        return FileResponse(str(INDEX_FILE), media_type="text/html; charset=utf-8")

    raise HTTPException(status_code=404, detail="index.html not found")