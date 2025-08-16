#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Railway worker scheduler
- Her gün RUN_AT saatinde (yerel TZ) COINS listesindeki semboller için
  src/online_crypto_trainer.py --mode update ... komutunu çalıştırır.
- Durum dosyasıyla (state/scheduler_state.json) aynı gün içinde iki kez çalışmaz.
- COINS: virgülle ayrılmış semboller (örn: BTC-USD,ETH-USD,BNB-USD,SOL-USD)
- Sembolleri dosyadan okumak istersen: symbols.txt (bir satır = bir sembol)

ENV değişkenleri:
  RUN_AT="06:05"            # HH:MM (default)
  TZ="Europe/Istanbul"      # default: Europe/Istanbul
  COINS="BTC-USD,ETH-USD"   # yoksa symbols.txt denenir, o da yoksa default 10'lu liste
  INTERVAL="1d"             # online_crypto_trainer için
  HORIZON="5"
  THRESHOLD="0.03"
  SIGNAL_THRESH="0.6"       # (trainer bunu kullanıyorsa)
  COST="0.001"
  CAP="0.3"
  ARTIFACTS_DIR="artifacts"
  PYTHON_BIN=""             # boş ise sys.executable kullanılır

Railway'de "Start Command":  python scheduler.py
"""

import os, sys, time, json, signal, subprocess
from datetime import datetime, date
from pathlib import Path

# ---------- Ayarlar (ENV + varsayılanlar) ----------
RUN_AT         = os.getenv("RUN_AT", "06:05").strip()       # HH:MM
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

ROOT           = Path(__file__).resolve().parent
TRAINER_PATH   = ROOT / "src" / "online_crypto_trainer.py"
LOG_DIR        = ROOT / "logs"
STATE_DIR      = ROOT / "state"
STATE_FILE     = STATE_DIR / "scheduler_state.json"

DEFAULT_COINS  = [
    "BTC-USD","ETH-USD","BNB-USD","SOL-USD","XRP-USD",
    "ADA-USD","DOGE-USD","TRX-USD","DOT-USD","MATIC-USD"
]

# ---------- Yardımcılar ----------
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
    # TZ uygulaması (Railway genelde UTC çalışır)
    try:
        import pytz
        from datetime import timezone
        tz = pytz.timezone(TZ)
        return datetime.now(tz)
    except Exception:
        # pytz yoksa sistem saatini kullan
        return datetime.now()

def parse_run_at(s):
    hh, mm = s.split(":")
    return int(hh), int(mm)

def read_symbols():
    # 1) ENV COINS
    if COINS_ENV:
        return [c.strip() for c in COINS_ENV.split(",") if c.strip()]
    # 2) symbols.txt
    sym_file = ROOT / "symbols.txt"
    if sym_file.exists():
        syms = []
        for line in sym_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                syms.append(line)
        if syms:
            return syms
    # 3) DEFAULT
    return DEFAULT_COINS

STOP = False
def _handle_sig(sig, frame):
    global STOP
    STOP = True
signal.signal(signal.SIGINT, _handle_sig)
signal.signal(signal.SIGTERM, _handle_sig)

def log(msg):
    ts = now_local().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    # aynı zamanda ana log'a yaz
    with (LOG_DIR / "scheduler.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def run_once_for_symbol(symbol: str):
    log(f"▶ Güncelle başlıyor: {symbol}")
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
    # Eğer trainer SIGNAL_THRESH'i de destekliyorsa gönder:
    if SIGNAL_THRESH:
        cmd += ["--signal-threshold", SIGNAL_THRESH]

    # Çalıştır
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True
    )

    sym_log = LOG_DIR / f"{symbol.replace('-','_')}.log"
    with sym_log.open("a", encoding="utf-8") as f:
        f.write("\n" + "="*60 + "\n")
        f.write("CMD: " + " ".join(cmd) + "\n")
        f.write(proc.stdout or "")
        if proc.stderr:
            f.write("\n[stderr]\n" + proc.stderr)

    if proc.returncode == 0:
        log(f"✅ Tamam: {symbol}")
    else:
        log(f"❌ Hata (code={proc.returncode}): {symbol}. Ayrıntı {sym_log.name} dosyasında.")

# ---------- Main döngü ----------
def main():
    ensure_dirs()

    if not TRAINER_PATH.exists():
        log(f"❌ Bulunamadı: {TRAINER_PATH}")
        sys.exit(1)

    hour_target, min_target = parse_run_at(RUN_AT)
    log(f"Scheduler hazır. TZ={TZ} | RUN_AT={RUN_AT} | PY={PYTHON_BIN}")
    log(f"Semboller: {', '.join(read_symbols())}")

    while not STOP:
        now = now_local()
        state = load_state()
        today_str = now.strftime("%Y-%m-%d")

        if (now.hour == hour_target and now.minute == min_target and
            state.get("last_run_date") != today_str):

            # Bugün ilk kez çalışacağız
            symbols = read_symbols()
            for sym in symbols:
                if STOP: break
                run_once_for_symbol(sym)
                time.sleep(2)  # servis nazikçe

            state["last_run_date"] = today_str
            state["done_symbols"] = symbols
            save_state(state)
            log("🗓️ Günlük görev tamamlandı.")

            # Aynı dakikada yeniden tetiklememek için 70sn bekle
            for _ in range(70):
                if STOP: break
                time.sleep(1)

        # hafif bekleme
        for _ in range(10):
            if STOP: break
            time.sleep(1)

    log("💤 Kapanıyor…")

if __name__ == "__main__":
    main()