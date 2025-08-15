from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
from dotenv import load_dotenv
from __future__ import annotations
import math

# Ortam değişkenlerini yükle (.env)
load_dotenv()

app = FastAPI(title="Coinspace API", version="1.0.0")

import os
from pathlib import Path
from starlette.staticfiles import StaticFiles

def _pick_web_dir() -> Path | None:
    # 1) ENV öncelikli
    env_dir = os.getenv("WEB_DIR")
    if env_dir and (Path(env_dir) / "index.html").exists():
        return Path(env_dir).resolve()
    # 2) Çalışma dizini /web
    if (Path.cwd() / "web" / "index.html").exists():
        return (Path.cwd() / "web").resolve()
    # 3) Bu dosyanın 2 üstünde /web (…/src/live/ → proje kökü)
    here = Path(__file__).resolve()
    cand = here.parents[2] / "web" if len(here.parents) >= 3 else None
    if cand and (cand / "index.html").exists():
        return cand.resolve()
    return None

WEB_DIR = _pick_web_dir()
if WEB_DIR:
    # /assets varsa ayrı mount (opsiyonel)
    if (WEB_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(WEB_DIR / "assets")), name="assets")
    # ⚠️ EN ÖNEMLİSİ: kökü web klasörüne bağla (html=True → index.html döner)
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="webroot")
else:
    # Bulunamazsa log at (Railway loglarında görürsünüz)
    print("[web] index.html bulunamadı; WEB_DIR ayarlayın veya /web dizini ekleyin.")

# CORS ayarları (Squarespace vb. dış bağlantılar için)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Güvenlik için burada domainin ile sınırlandırabilirsin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Yardımcı Fonksiyon: BTC fiyatını çek ===
def get_btc_price():
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        response = requests.get(url)
        data = response.json()
        return float(data["price"])
    except Exception:
        return None

# === Anasayfa ===
@app.get("/")
def root():
    return {"status": "✅ API aktif", "message": "Coinspace Backend Çalışıyor"}

# === Kaldıraçlı BTC Öneri Endpoint ===
@app.get("/advice")
def leveraged_btc_advice(
    sermaye: float = Query(..., description="Toplam sermaye (TL)"),
    kaldirac: float = Query(3, description="Kaldıraç oranı"),
    stop: float = Query(4.0, description="Stop loss yüzdesi"),
    risk: float = Query(1.0, description="İşlem başına risk yüzdesi")
):
    fiyat = get_btc_price()
    if fiyat is None:
        return {"error": "BTC fiyatı alınamadı"}

    teminat = sermaye / kaldirac
    pozisyon = sermaye
    adet = (pozisyon / fiyat)

    return {
        "BTC Kaldıraçlı Plan (özet)": {
            "Risk seviyesi": "orta",
            "Sermaye": f"{sermaye:,.2f} ₺",
            "Kaldıraç": f"{kaldirac}x",
            "Stop": f"%{stop:.2f}",
            "İşlem başı risk": f"%{risk:.2f} sermaye",
            "Teminat (nakit) limiti": f"{teminat:,.2f} ₺",
            "Pozisyon (notional)": f"{pozisyon:,.2f} ₺",
            "Anlık fiyat": f"{fiyat:,.2f}",
            "Tahmini adet": round(adet, 4)
        },
        "Uygulama": [
            "Giriş: kademeli (2–3 parça); ilk kademede yarım teminat.",
            "Çıkış: TP1 %3, TP2 %5; SL tetiklenince tam çık.",
            "Günlük toplam zarar limiti: ≤ %3; aşıldığında gün sonuna kadar işlem yapma."
        ]
    }

# Railway’de çalıştırmak için:
# uvicorn main:app --host 0.0.0.0 --port 8000