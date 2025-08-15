# main.py
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from starlette.staticfiles import StaticFiles

# Mevcut API uygulamanı içe al (rotalar /advice, /prices, /plan, /compare, /health ...)
# NOT: Bu modülde app = FastAPI(...) tanımlı olmalı.
from src.live.advice_server import app as api_app


def _pick_web_dir() -> Path | None:
    """
    index.html'in bulunduğu /web dizinini bulur.
    Öncelik sırası:
      1) WEB_DIR env → (WEB_DIR/index.html)
      2) Çalışma dizini /web → (cwd/web/index.html)
      3) Bu dosyanın 1 üstünde /web → (main.py'nin ebeveyninde /web/index.html)
      4) Bu dosyanın 2 üstünde /web → (proje kökü varsayımı)
    """
    # 1) Env
    env_dir = os.getenv("WEB_DIR")
    if env_dir and (Path(env_dir) / "index.html").exists():
        return Path(env_dir).resolve()

    # 2) CWD/web
    cand = Path.cwd() / "web"
    if (cand / "index.html").exists():
        return cand.resolve()

    # 3) main.py'nin bulunduğu klasörün yanındaki /web
    here = Path(__file__).resolve()
    if (here.parent / "web" / "index.html").exists():
        return (here.parent / "web").resolve()

    # 4) iki üst (çoğu projede src/ ile çalışırken)
    if len(here.parents) >= 2:
        proj_root = here.parents[1]
        if (proj_root / "web" / "index.html").exists():
            return (proj_root / "web").resolve()

    return None


# ---- Üst FastAPI uygulaması ----
app = FastAPI(title="Cortexa – Web + API")

# API'yi /api altına bağla (JSON rotaların hepsi burada kalır)
app.mount("/api", api_app)

# WEB klasörünü bul ve köke bağla
WEB_DIR = _pick_web_dir()
if WEB_DIR:
    # /assets klasörü varsa ayrıca mount edelim (opsiyonel)
    assets_dir = WEB_DIR / "assets"
    if assets_dir.exists() and assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # KÖK: tüm HTML isteklerini web'e ver (html=True → / ⇒ index.html)
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="webroot")
else:
    # WEB_DIR bulunamazsa bir bilgi log'u basalım
    print("[web] index.html bulunamadı. WEB_DIR env ayarlayın veya proje köküne /web/index.html ekleyin.")

"""
⚙️ Railway notları
-------------------
- Environment:
    PORT         → (Railway otomatik sağlar)
    WEB_DIR      → /app/web  (önerilir; web/index.html burada)
- Procfile (opsiyonel):
    web: uvicorn main:app --host 0.0.0.0 --port ${PORT}
- Testler:
    /api/health  → {"ok": true}
    /            → index.html (SPA)
"""