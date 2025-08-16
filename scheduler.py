#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Railway worker scheduler
- Her gün RUN_AT saatinde (yerel TZ) COINS listesindeki semboller için
  src/online_crypto_trainer.py --mode update ... komutunu çalıştırır.
- Durum dosyasıyla (state/scheduler_state.json) aynı gün içinde iki kez çalışmaz.
- COINS: virgülle ayrılmış semboller (örn: BTC-USD,ETH-USD,BNB-USD,SOL-USD)

ENV:
  RUN_AT="06:05" | TZ="Europe/Istanbul" | COINS="BTC-USD,ETH-USD,BNB-USD,SOL-USD"
  INTERVAL="1d" | HORIZON="5" | THRESHOLD="0.03" | SIGNAL_THRESH="0.6"
  COST="0.001" | CAP="0.3" | ARTIFACTS_DIR="artifacts" | PYTHON_BIN=""
  TELEGRAM_BOT_TOKEN="" | TELEGRAM_CHAT_ID="" | PING_URL=""
  STARTUP_RUN="0"  # "1" ise açılışta bir tur çalıştırır

Start Command (Railway):  python scheduler.py
"""

import os, sys, time, json, signal, subprocess
from datetime import datetime
from pathlib import Path

# ---------- Ayarlar ----------
RUN_AT         = os.getenv("RUN_AT", "06:05").strip()
TZ             = os.getenv("TZ", "Europe/Istanbul").strip()
COINS_ENV      = os.getenv("COINS", "").strip()
INTERVAL       = os.getenv("INTERVAL", "1d").strip()
HORIZON        = os.getenv("HORIZON", "5").strip()
THRESHOLD      = os.getenv("THRESHOLD", "0.03").strip()
SIGNAL_THRESH  = os.getenv("SIGNAL_THRESH", "0.6").strip()
COST           = os.getenv("COST", "0.001").strip()
CAP            = os.getenv("CAP", "0.3").strip()
ARTIFACTS_DIR  = os.getenv("ARTIFACTS_DIR", "artifacts").strip()
PYTHON_BIN     = os.getenv("PYTHON_BIN", "").strip() or sys.executable
STARTUP_RUN    = os.getenv("STARTUP_RUN", "0").strip()

# Bildirim (opsiyonel)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "").strip()
PING_URL           = os.getenv("PING_URL", "").strip()

ROOT           = Path(__file__).resolve().parent
TRAINER_PATH   = ROOT / "src" / "online_crypto_trainer.py"
LOG_DIR        = ROOT / "logs"
STATE_DIR      = ROOT / "state"
STATE_FILE     = STATE_DIR / "scheduler_state.json"

DEFAULT_COINS  = [
    "BTC-USD","ETH-USD","BNB-USD","SOL-USD","XRP-USD",
    "ADA-USD","DOGE-USD","TRX-USD","DOT-USD","MATIC-USD"
]

STOP = False
def _handle_sig(sig, frame):
    global STOP
    STOP = True
signal.signal(signal.SIGINT, _handle_sig)
signal.signal(signal.SIGTERM, _handle_sig)

# ---------- FS & Zaman ----------
def ensure_dirs():
    (ROOT / ARTIFACTS_DIR).mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_run_date": "", "done_symbols": []}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def now_local():
    try:
        import pytz
        tz = pytz.timezone(TZ)
        return datetime.now(tz)
    except Exception:
        return datetime.now()

def parse_run_at(s):
    hh, mm = s.split(":")
    return int(hh), int(mm)

def read_symbols():
    if COINS_ENV:
        return [c.strip() for c in COINS_ENV.split(",") if c.strip()]
    sym_file = ROOT / "symbols.txt"
    if sym_file.exists():
        syms = []
        for line in sym_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                syms.append(line)
        if syms:
            return syms
    return DEFAULT_COINS

# ---------- Log ----------
def log(msg):
    ts = now_local().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with (LOG_DIR / "scheduler.log").open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

# ---------- Bildirim ----------
def notify(msg: str):
    """
    Telegram veya Webhook (PING_URL). Hangi kanal deneniyorsa loglar.
    """
    log(f"[notify] {msg}")
    sent = False

    # Telegram
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            import urllib.request, json as _json
            data = _json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": msg}).encode("utf-8")
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                code = resp.getcode()
                log(f"[notify:telegram] HTTP {code}")
                sent = (200 <= code < 300)
        except Exception as e:
            log(f"[notify:telegram] hata: {e}")

    # Basit webhook (JSON)
    if (not sent) and PING_URL:
        try:
            import urllib.request, json as _json
            data = _json.dumps({
                "message": msg, "source": "scheduler", "ts": now_local().isoformat()
            }).encode("utf-8")
            req = urllib.request.Request(PING_URL, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                code = resp.getcode()
                log(f"[notify:webhook] HTTP {code}")
                sent = (200 <= code < 300)
        except Exception as e:
            log(f"[notify:webhook] hata: {e}")

    if not sent:
        log("[notify] Kanal yok ya da teslim edilemedi (Telegram env set edilmedi / webhook 2xx dönmedi).")
    return sent

def notify_probe():
    """
    Başlangıçta kanal uygunluğunu raporlar ve test bildirimi yollar.
    """
    has_tg = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
    has_wh = bool(PING_URL)
    log(f"[probe] telegram={'OK' if has_tg else 'YOK'} | webhook={'OK' if has_wh else 'YOK'}")
    delivered = notify("✅ Scheduler başlatıldı (probe)")
    log(f"[probe] delivered={delivered}")

# ---------- Çalıştır ----------
def run_once_for_symbol(symbol: str):
    log(f"⏰ Tetik yakalandı, güncelle başlıyor: {symbol}")
    cmd = [
        PYTHON_BIN, str(TRAINER_PATH),
        "--mode", "update",
        "--symbol", symbol,
        "--interval", INTERVAL,
        "--horizon", HORIZON,
        "--threshold", THRESHOLD,
        "--artifacts", ARTIFACTS_DIR,
        "--cost", COST,
        "--cap", CAP
    ]
    if SIGNAL_THRESH:
        cmd += ["--signal-threshold", SIGNAL_THRESH]

    try:
        proc = subprocess.run(
            cmd, cwd=str(ROOT),
            capture_output=True, text=True, check=False
        )
    except Exception as e:
        log(f"❌ Çalıştırma hatası: {symbol} -> {e}")
        notify(f"❌ {symbol} update hata: {e}")
        return

    sym_log = LOG_DIR / f"{symbol.replace('-','_')}.log"
    try:
        with sym_log.open("a", encoding="utf-8") as f:
            f.write("\n" + "="*60 + "\n")
            f.write("CMD: " + " ".join(cmd) + "\n")
            f.write(proc.stdout or "")
            if proc.stderr:
                f.write("\n[stderr]\n" + proc.stderr)
    except Exception:
        pass

    if proc.returncode == 0:
        log(f"✅ Tamam: {symbol}")
    else:
        log(f"❌ Hata (code={proc.returncode}): {symbol}. Ayrıntı {sym_log.name} içinde.")
        notify(f"❌ {symbol} update RC={proc.returncode} (log: {sym_log.name})")

# ---------- Main ----------
def main():
    ensure_dirs()

    if not TRAINER_PATH.exists():
        log(f"❌ Bulunamadı: {TRAINER_PATH}")
        notify("❌ Trainer dosyası bulunamadı (src/online_crypto_trainer.py)")
        sys.exit(1)

    hour_target, min_target = parse_run_at(RUN_AT)
    syms_preview = ", ".join(read_symbols())
    log(f"Scheduler hazır. TZ={TZ} | RUN_AT={RUN_AT} | PY={PYTHON_BIN}")
    log(f"Semboller: {syms_preview}")

    # Başlangıçta bildirim kanalı provasını yap
    notify_probe()

    # İsteğe bağlı: açılışta bir tur çalıştır
    if STARTUP_RUN == "1":
        log("🚀 STARTUP_RUN=1 — İlk açılışta bir seferlik update başlıyor.")
        for sym in read_symbols():
            if STOP: break
            run_once_for_symbol(sym)
            time.sleep(2)
        log("🚀 STARTUP_RUN tamamlandı.")
        notify("🚀 STARTUP_RUN tamamlandı.")

    # Ana döngü
    while not STOP:
        now = now_local()
        state = load_state()
        today_str = now.strftime("%Y-%m-%d")

        if (now.hour == hour_target and now.minute == min_target and
            state.get("last_run_date") != today_str):

            symbols = read_symbols()
            notify(f"⏱️ Günlük görev tetiklendi • {today_str} • {RUN_AT}")
            for sym in symbols:
                if STOP: break
                run_once_for_symbol(sym)
                time.sleep(2)

            state["last_run_date"] = today_str
            state["done_symbols"] = symbols
            save_state(state)
            log("🗓️ Günlük görev tamamlandı.")
            notify("🗓️ Günlük görev tamamlandı.")

            # Aynı dakikada tekrar tetiklenmesin
            for _ in range(70):
                if STOP: break
                time.sleep(1)

        # hafif bekleme
        for _ in range(10):
            if STOP: break
            time.sleep(1)

    log("💤 Kapanıyor…")
    notify("💤 Scheduler kapanıyor…")

if __name__ == "__main__":
    main()