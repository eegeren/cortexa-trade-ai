# src/live/advice_server.py
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional, List, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.staticfiles import StaticFiles

# ─────────────────────────────────────────────────────────────
# Guardrails / metin blokları
# ─────────────────────────────────────────────────────────────
from src.advice.guardrails import (
    build_intro, options_section, sample_portfolios,
    action_checklist, PROFILE_QUESTIONS, tailor_by_profile,
    topic_compare, build_dca_risk_plan, build_brief_answer,
    detect_leverage_intent, build_leverage_answer,
)

# Varlık sözlüğü ve tespit
from src.advice.assets import detect_assets_in_text, default_stop_for

# Canlı fiyat beslemeleri
from src.advice.price_feeds import (
    map_assets_to_feed_codes, fetch_live_prices_cached, format_live_table
)

# Kaldıraç modülü
from src.advice.leverage import (
    parse_leverage_from_text, LeverageInputs, build_leverage_plan, format_leverage_markdown
)

# ─────────────────────────────────────────────────────────────
# App & CORS
# ─────────────────────────────────────────────────────────────
app = FastAPI(title="Cortexa Advice API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────
# Web dizinini akıllı bulma (HTML servis)
# ─────────────────────────────────────────────────────────────
def _pick_web_dir() -> Path | None:
    # 1) ENV öncelikli
    env_dir = os.getenv("WEB_DIR")
    candidates = []
    if env_dir:
        candidates.append(Path(env_dir).resolve())

    # 2) Çalışma dizini altı
    candidates.append((Path.cwd() / "web").resolve())

    # 3) Bu dosyadan geriye doğru birkaç seviye
    here = Path(__file__).resolve()
    for up in [1, 2, 3, 4]:
        candidates.append((here.parents[up-1] / "web").resolve() if len(here.parents) >= up else None)

    # 4) Repo kökü varsayımı: src/…/…/.. → project_root/web
    if len(here.parents) >= 3:
        candidates.append((here.parents[2] / "web").resolve())

    seen = set()
    for p in [c for c in candidates if c]:
        if p in seen:
            continue
        seen.add(p)
        if (p / "index.html").exists():
            return p
    return None

WEB_DIR = _pick_web_dir()
INDEX_FILE = (WEB_DIR / "index.html") if WEB_DIR else None
print(f"[web] using: {WEB_DIR} index={INDEX_FILE.exists() if INDEX_FILE else False}")

# Statik varlıklar (opsiyonel)
if WEB_DIR and (WEB_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(WEB_DIR / "assets")), name="assets")

# ─────────────────────────────────────────────────────────────
# Şemalar
# ─────────────────────────────────────────────────────────────
class AdviceQuery(BaseModel):
    user_query: str
    goal: Optional[str] = ""
    horizon: Optional[str] = ""
    risk: Optional[str] = ""
    capital: Optional[float] = None
    stop_pct: Optional[float] = None
    show_prices: Optional[bool] = True
    suppress_disclaimer: Optional[bool] = False

class PriceQuery(BaseModel):
    assets: List[str]

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
    stop_pct: Optional[float] = None
    use_live_price: bool = True

class CompareQuery(BaseModel):
    user_query: str
    horizon: Optional[str] = ""
    risk: Optional[str] = ""
    capital: Optional[float] = None
    stop_pct: Optional[float] = None

class LeverageQuery(BaseModel):
    user_query: str
    capital: float
    risk_per_trade: float = 0.01
    stop_pct: Optional[float] = None
    leverage: Optional[int] = Field(None, ge=1, le=50)
    maintenance_margin: float = 0.01
    use_live_price: bool = True

# ─────────────────────────────────────────────────────────────
# Yardımcılar
# ─────────────────────────────────────────────────────────────
def _live_block_for_query_text(text: str) -> str:
    keys = detect_assets_in_text(text)
    if not keys:
        return ""
    snap = fetch_live_prices_cached(map_assets_to_feed_codes(keys), ttl=15)
    return format_live_table(snap)

def _is_gibberish_or_unknown(q: str) -> bool:
    if not q or len(q.strip()) < 2:
        return True
    if detect_assets_in_text(q):
        return False
    kws = ["altın","xau","gümüş","xag","petrol","wti","hisse","endeks","sp500","nasdaq",
           "btc","bitcoin","eth","ethereum","sol","solana","kripto","dolar","usd","euro",
           "eur","tahvil","bono","faiz","döviz","usdtry","eurtry","kaldıraç","leverage","x"]
    ql = q.lower()
    return not any(k in ql for k in kws)

def _parse_inline_params(text: str) -> dict:
    out = {"risk":"", "capital":None, "stop_pct":None}
    if not text:
        return out
    t = text.lower()
    if any(s in t for s in ["düşük","dusuk","low"]): out["risk"]="dusuk"
    elif any(s in t for s in ["yüksek","yuksek","high"]): out["risk"]="yuksek"
    elif any(s in t for s in ["orta","medium"]): out["risk"]="orta"
    m = re.search(r"(\d+(?:[\.,]\d+)?)(\s*[kKmM])", t)
    if m:
        val = float(m.group(1).replace(",", "."))
        out["capital"] = val * (1_000 if m.group(2).strip().lower()=="k" else 1_000_000)
    else:
        m2 = re.search(r"\b(\d{5,})\b", t)
        if m2:
            out["capital"] = float(m2.group(1))
    ms = re.search(r"%\s*(\d+(?:[\.,]\d+)?)", t)
    if ms:
        out["stop_pct"] = float(ms.group(1).replace(",", ".")) / 100.0
    else:
        ms2 = re.search(r"\b0[\.,]\d+\b", t)
        if ms2:
            out["stop_pct"] = float(ms2.group(0).replace(",", "."))
    return out

# ─────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"ok": True}

# Hızlı teşhis için
@app.get("/__where", include_in_schema=False)
def __where():
    return {
        "web_dir": str(WEB_DIR) if WEB_DIR else None,
        "index_exists": INDEX_FILE.exists() if INDEX_FILE else False,
        "index_path": str(INDEX_FILE) if INDEX_FILE else None,
        "cwd": str(Path.cwd()),
    }

# ─────────────────────────────────────────────────────────────
# Advice
# ─────────────────────────────────────────────────────────────
@app.post("/advice")
def advice(q: AdviceQuery) -> Dict[str, str]:
    if _is_gibberish_or_unknown(q.user_query):
        guide = (
            "**Geçersiz/eksik istek** — örnekler:\n"
            "- `btc kaldıraçlı (orta risk, 50k, %1.5 stop)`\n"
            "- `eth kaldıraçlı (yüksek risk, 2m, %1 stop)`\n"
            "- `btc vs euro (6 ay, orta risk, 100k, %2 stop)`\n"
        )
        return {"answer": guide}

    if detect_leverage_intent(q.user_query):
        keys = detect_assets_in_text(q.user_query) or []
        asset_key = keys[0] if keys else "btc"
        inline = _parse_inline_params(q.user_query)
        risk = q.risk or inline["risk"] or "orta"
        capital = q.capital if q.capital is not None else inline["capital"] or 0.0
        stop_pct = q.stop_pct if q.stop_pct is not None else inline["stop_pct"]
        if stop_pct is None:
            stop_pct = max(default_stop_for(asset_key) / 2, 0.005)

        entry_price = None
        try:
            snap = fetch_live_prices_cached(map_assets_to_feed_codes([asset_key]), ttl=15)
            entry_price = snap.get(asset_key, {}).get("price")
        except Exception:
            pass

        header = (f"**Soru:** {q.user_query}\n\n") if q.suppress_disclaimer else build_intro(q.user_query)
        short = build_leverage_answer(asset_key=asset_key, risk=risk, capital=capital, stop_pct=stop_pct, entry_price=entry_price)
        live_tbl = _live_block_for_query_text(asset_key) if q.show_prices else ""
        return {"answer": header + short + (("\n" + live_tbl) if live_tbl else "")}

    intro = f"**Soru:** {q.user_query}\n\n" if q.suppress_disclaimer else build_intro(q.user_query)
    brief = build_brief_answer(q.user_query, q.horizon, q.risk, q.capital, q.stop_pct)
    opts = options_section()
    topic = topic_compare(q.user_query)
    live_tbl = _live_block_for_query_text(q.user_query) if q.show_prices else ""
    tailoring = tailor_by_profile(q.goal, q.horizon, q.risk)
    plan = build_dca_risk_plan(q.user_query, q.horizon, q.risk, q.capital, q.stop_pct)
    questions = "\n".join(PROFILE_QUESTIONS)

    body = (
        f"{intro}{brief}\n"
        f"---\nSEÇENEKLER ÖZETİ (kısa):\n{opts}\n"
        f"{topic}{live_tbl}\n"
        f"---\nPROFİLİNİZE GÖRE NOTLAR (kısa):\n{tailoring}\n\n"
        f"{plan}\n\n{sample_portfolios()}\n{action_checklist()}\n"
        f"Profil soruları:\n{questions}\n"
    )
    return {"answer": body}

# ─────────────────────────────────────────────────────────────
# Prices
# ─────────────────────────────────────────────────────────────
@app.post("/prices", response_model=SnapshotResponse)
def prices(p: PriceQuery):
    items = map_assets_to_feed_codes(p.assets or [])
    snap = fetch_live_prices_cached(items, ttl=15) if items else {}
    return {"snapshot": snap}

# ─────────────────────────────────────────────────────────────
# Plan
# ─────────────────────────────────────────────────────────────
@app.post("/plan")
def plan(p: PlanQuery) -> Dict[str, object]:
    keys = detect_assets_in_text(p.user_query) or []
    asset_key = keys[0] if keys else "btc"
    stop_pct = p.stop_pct if p.stop_pct is not None else default_stop_for(asset_key)
    pos_cash = (p.capital * p.risk_per_trade) / max(stop_pct, 1e-9)

    qty = None
    entry_price = None
    if p.use_live_price:
        snap = fetch_live_prices_cached(map_assets_to_feed_codes([asset_key]), ttl=15)
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
            "hint": "Her adımı aynı gün (örn. 5/15) yap; 3 ardışık zarar sonrası 1 kademe ara.",
        },
        "sizing": {
            "position_cash_limit_by_risk": round(pos_cash, 2),
            "formula": "position_cash ≈ (capital × risk_per_trade) / stop_pct",
            "note": "Miktar = position_cash / entry_price. Stop mesafesini oynaklığa göre ayarla.",
        },
    }
    if entry_price:
        resp["market"] = {"entry_price": round(float(entry_price), 6)}
    if qty:
        resp["sizing"]["quantity_estimate"] = round(float(qty), 8)
    return resp

# ─────────────────────────────────────────────────────────────
# Compare
# ─────────────────────────────────────────────────────────────
@app.post("/compare")
def compare_assets(p: CompareQuery) -> Dict[str, str]:
    keys = detect_assets_in_text(p.user_query)
    keys = list(dict.fromkeys(keys))
    if len(keys) < 2:
        return {"compare": "**Kıyas için iki varlık tespit edilemedi.**"}

    a, b = keys[:2]
    snap = fetch_live_prices_cached(map_assets_to_feed_codes([a, b]), ttl=15)
    live_tbl = format_live_table(snap) if snap else ""

    table = (
        "**Hızlı Karşılaştırma (genel bilgi):**\n\n"
        "| Özellik | A | B |\n"
        "|---|---|---|\n"
        f"| Varlık | {a.upper()} | {b.upper()} |\n"
        "| Sınıf | — | — |\n"
        "| Rol | — | — |\n"
        "| Volatilite | — | — |\n"
        "| Getiri Kaynağı | — | — |\n"
        "| Likidite | — | — |\n"
        "| Portföy Aralığı | — | — |\n\n"
        "– Oynaklığı yüksek tarafa ayrılan payı düşük tut; DCA ve pozisyon başı risk limiti uygula.\n"
    )
    return {"compare": table + (("\n" + live_tbl) if live_tbl else "")}

# ─────────────────────────────────────────────────────────────
# Leverage
# ─────────────────────────────────────────────────────────────
@app.post("/leverage")
def leverage_endpoint(p: LeverageQuery) -> Dict[str, str]:
    keys = detect_assets_in_text(p.user_query) or []
    asset_key = keys[0] if keys else "btc"

    stop_pct = p.stop_pct if p.stop_pct is not None else default_stop_for(asset_key)
    lev = p.leverage if p.leverage else parse_leverage_from_text(p.user_query)

    entry_price = None
    if p.use_live_price:
        snap = fetch_live_prices_cached(map_assets_to_feed_codes([asset_key]), ttl=15)
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

# ─────────────────────────────────────────────────────────────
# HTML: Root ve SPA fallback
# ─────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
def serve_index_root():
    if INDEX_FILE and INDEX_FILE.exists():
        return FileResponse(str(INDEX_FILE), media_type="text/html; charset=utf-8")
    # index yoksa, açıkça bildir (neden JSON gördüğünü anlamak için)
    return JSONResponse(
        {
            "ok": False,
            "reason": "index.html not found",
            "web_dir": str(WEB_DIR) if WEB_DIR else None,
            "index_path": str(INDEX_FILE) if INDEX_FILE else None,
            "hint": "WEB_DIR ortam değişkeni ile yol belirt veya web/index.html ekle.",
        },
        status_code=404,
    )

@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    # API yollarına dokunma
    api_prefixes = {"advice", "prices", "plan", "compare", "leverage", "health", "__where"}
    first = (full_path or "").split("/", 1)[0]
    if first in api_prefixes:
        raise HTTPException(status_code=404, detail="API path")

    if INDEX_FILE and INDEX_FILE.exists():
        return FileResponse(str(INDEX_FILE), media_type="text/html; charset=utf-8")
    raise HTTPException(status_code=404, detail="index.html not found")

# --- KOMPOZİT UYGULAMA (API: /api, WEB: /) ---

# 1) Var olan API uygulamanızı "api_app" olarak saklayın
api_app = app

# 2) Dışa servis edilecek ana uygulama
from fastapi import FastAPI
from starlette.staticfiles import StaticFiles
from pathlib import Path
import os

app = FastAPI(title="Cortexa (Web + API)")

# 3) API'yi /api altına mount edin
app.mount("/api", api_app)

# 4) Web klasörünü kökten servis edin
def _pick_web_dir() -> Path | None:
    env_dir = os.getenv("WEB_DIR")
    if env_dir and (Path(env_dir) / "index.html").exists():
        return Path(env_dir).resolve()
    cand1 = Path.cwd() / "web" / "index.html"
    if cand1.exists():
        return cand1.parent.resolve()
    here = Path(__file__).resolve()
    cand2 = (here.parents[2] / "web") if len(here.parents) >= 3 else None
    if cand2 and (cand2 / "index.html").exists():
        return cand2.resolve()
    return None

WEB_DIR = _pick_web_dir()
if WEB_DIR:
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
else:
    @app.get("/", include_in_schema=False)
    def _root_placeholder():
        return {"ok": True, "service": "Cortexa Advice API (no web dir)"}