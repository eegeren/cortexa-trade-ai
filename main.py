# main.py
from __future__ import annotations

import os
import traceback
import logging
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.staticfiles import StaticFiles

# --- notify() içe aktar (yoksa no-op) ---
try:
    from notifier import notify  # notify("mesaj")
except Exception:
    def notify(_msg: str) -> bool:  # fallback
        try:
            print("[notify:fallback]", _msg)
        except Exception:
            pass
        return False

# Mevcut API uygulaman (rotalar /advice, /prices, /plan, /compare, /health ...)
from src.live.advice_server import app as api_app


def _pick_web_dir() -> Path | None:
    """
    index.html'in bulunduğu /web dizinini bulur.
    Öncelik:
      1) WEB_DIR env → (WEB_DIR/index.html)
      2) CWD/web      → (cwd/web/index.html)
      3) Bu dosyanın yanındaki /web
      4) Bu dosyanın iki üstündeki /web
    """
    env_dir = os.getenv("WEB_DIR")
    if env_dir and (Path(env_dir) / "index.html").exists():
        return Path(env_dir).resolve()

    cand = Path.cwd() / "web"
    if (cand / "index.html").exists():
        return cand.resolve()

    here = Path(__file__).resolve()
    if (here.parent / "web" / "index.html").exists():
        return (here.parent / "web").resolve()

    if len(here.parents) >= 2:
        proj_root = here.parents[1]
        if (proj_root / "web" / "index.html").exists():
            return (proj_root / "web").resolve()

    return None


# ---- Üst FastAPI uygulaması ----
app = FastAPI(title="Cortexa – Web + API")

# Basit health (ana app için ayrı uç)
@app.get("/healthz")
async def healthz():
    return {"ok": True}

# API'yi /api altına bağla
app.mount("/api", api_app)

# WEB klasörünü bul ve köke bağla
WEB_DIR = _pick_web_dir()
if WEB_DIR:
    assets_dir = WEB_DIR / "assets"
    if assets_dir.exists() and assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="webroot")
else:
    print("[web] index.html bulunamadı. WEB_DIR env ayarlayın veya proje köküne /web/index.html ekleyin.")


# ==================== Bildirimli Hata Yönetimi ====================

# (Opsiyonel) Startup / Shutdown bildirimi
@app.on_event("startup")
async def _on_startup():
    try:
        notify("🟢 Backend başladı (startup)")
    except Exception:
        pass

@app.on_event("shutdown")
async def _on_shutdown():
    try:
        notify("🔴 Backend kapanıyor (shutdown)")
    except Exception:
        pass


# Global Exception Handler — yakalanmamış tüm hataları bildir
@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    try:
        client = request.client.host if request.client else "?"
        path = request.url.path
        method = request.method
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        tb_short = tb[-2000:]  # mesaj limiti için kısalt
        notify(
            "❌ Unhandled Error\n"
            f"• {method} {path}\n"
            f"• client: {client}\n"
            f"• err: {str(exc)}\n"
            f"• trace:\n```\n{tb_short}\n```"
        )
    except Exception:
        pass

    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


# HTTP middleware — 5xx yanıtları ve HTTPException(>=500) bildirim
# Statik isteklerde gürültüyü azalt: /assets, favicon, .css, .js vs.
_SKIP_PREFIXES = ("/assets", "/static", "/favicon", "/robots.txt")
_SKIP_EXTS = (".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico", ".map")

def _is_static(path: str) -> bool:
    if any(path.startswith(p) for p in _SKIP_PREFIXES):
        return True
    if any(path.endswith(ext) for ext in _SKIP_EXTS):
        return True
    return False

@app.middleware("http")
async def _error_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        if response.status_code >= 500 and not _is_static(request.url.path):
            try:
                notify(f"⚠️ 5xx yanıt: {request.method} {request.url.path} → {response.status_code}")
            except Exception:
                pass
        return response
    except HTTPException as he:
        if he.status_code >= 500 and not _is_static(request.url.path):
            try:
                notify(f"⚠️ HTTPException: {request.method} {request.url.path} → {he.status_code} | {he.detail}")
            except Exception:
                pass
        raise
    except Exception:
        # Diğer tüm hatalar global handler'a gidecek
        raise


# Logger → Telegram ERROR forward (opsiyonel)
class TelegramHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            if len(msg) > 3500:
                msg = msg[-3500:]
            # Statik kaynak hataları çok gürültü yapmasın:
            if hasattr(record, "request_path") and _is_static(str(record.request_path)):
                return
            notify(f"📣 LOG {record.levelname}\n```\n{msg}\n```")
        except Exception:
            pass

tg_handler = TelegramHandler()
tg_handler.setLevel(logging.ERROR)
tg_handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s"))

root_logger = logging.getLogger()
root_logger.addHandler(tg_handler)
# root_logger.setLevel(logging.INFO)  # İstersen aç


"""
⚙️ Railway notları
-------------------
Env:
  PORT         → (Railway verir)
  WEB_DIR      → /app/web   (önerilir; web/index.html burada)
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID → notifier için

Procfile (opsiyonel):
  web: uvicorn main:app --host 0.0.0.0 --port ${PORT}

Test:
  GET /api/health → {"ok": true}
  GET /healthz    → {"ok": true}
  GET /           → index.html (SPA)
"""