# src/advice/price_feeds.py
from __future__ import annotations

from typing import Dict, List, Tuple, Optional
import time
import math

import requests
import requests_cache
import yfinance as yf
import pandas as pd

# ------------------------------------------------------------
# Basit cache (60 sn) – CoinGecko istekleri için
# ------------------------------------------------------------
requests_cache.install_cache("cortexa_price_cache", backend="memory", expire_after=60)

# ------------------------------------------------------------
# CoinGecko – kripto basit fiyat
# ------------------------------------------------------------
def coingecko_simple_price(ids: List[str], vs: str = "usd") -> Dict[str, Dict[str, float]]:
    if not ids:
        return {}
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": ",".join(ids),
        "vs_currencies": vs,
        "include_24hr_change": "true",
    }
    headers = {"User-Agent": "cortexa/1.0"}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()

# ------------------------------------------------------------
# Yahoo Finance – FX / Emtia / Hisse
# ------------------------------------------------------------
def _extract_last_prev(df: pd.DataFrame) -> Optional[Tuple[float, float]]:
    if df is None or len(df) == 0:
        return None
    last = float(df["Close"].iloc[-1])
    prev = float(df["Close"].iloc[-2]) if len(df) > 1 else last
    return last, prev

def yfinance_quote(tickers: List[str]) -> Dict[str, Dict[str, float]]:
    """
    Dönüş: {ticker: {price, prev_close, change_pct}}
    Örnek tickers:
      FX: 'USDTRY=X', 'EURUSD=X', 'EURTRY=X'
      Altın futures: 'GC=F'
      Altın spot: 'XAUUSD=X'
      Endeks: '^GSPC', '^NDX'
      Hisse/ETF: 'AAPL', 'SPY'
    """
    out: Dict[str, Dict[str, float]] = {}
    if not tickers:
        return out

    data = yf.download(
        tickers=" ".join(tickers),
        period="2d",
        interval="1d",
        progress=False,
        group_by="ticker",
        auto_adjust=False,
        threads=True,
    )

    multi = isinstance(getattr(data, "columns", None), pd.MultiIndex)

    if multi:
        for t in tickers:
            try:
                df = data[t]
                vals = _extract_last_prev(df)
                if not vals:
                    continue
                last, prev = vals
                chg = ((last / prev) - 1.0) * 100.0 if prev else 0.0
                out[t] = {"price": float(last), "prev_close": float(prev), "change_pct": float(chg)}
            except Exception:
                continue
    else:
        try:
            vals = _extract_last_prev(data)
            if vals:
                last, prev = vals
                chg = ((last / prev) - 1.0) * 100.0 if prev else 0.0
                out[tickers[0]] = {"price": float(last), "prev_close": float(prev), "change_pct": float(chg)}
        except Exception:
            pass

    return out

# ------------------------------------------------------------
# Varlık anahtarı → (feed, code) eşlemesi
# ------------------------------------------------------------
_FEED_MAP: Dict[str, List[Tuple[str, str]]] = {
    # Kripto (CoinGecko)
    "btc": [("coingecko", "bitcoin")],
    "eth": [("coingecko", "ethereum")],
    "sol": [("coingecko", "solana")],

    # Altın – önce futures, sonra spot dene
    "xau": [("yfinance", "GC=F"), ("yfinance", "XAUUSD=X")],
    "xag": [("yfinance", "SI=F"), ("yfinance", "XAGUSD=X")],

    # Döviz – TRY çaprazları (örnek)
    "usd": [("yfinance", "USDTRY=X")],
    "eur": [("yfinance", "EURTRY=X")],
    "try": [("yfinance", "TRY=X")],  # çoğu zaman veri dönmeyebilir

    # Endeks / Hisse
    "spx": [("yfinance", "^GSPC"), ("yfinance", "SPY")],
    "ndx": [("yfinance", "^NDX"), ("yfinance", "QQQ")],
    "aapl": [("yfinance", "AAPL")],
    "tsla": [("yfinance", "TSLA")],
}

def map_assets_to_feed_codes(keys: List[str]) -> List[Tuple[str, str, str]]:
    """
    keys: ['btc','xau','eur'] gibi.
    Dönüş: [(key, feed, code), ...]
    """
    items: List[Tuple[str, str, str]] = []
    for k in keys or []:
        routes = _FEED_MAP.get(k.lower(), [])
        for (feed, code) in routes:
            items.append((k.lower(), feed, code))
    return items

# ------------------------------------------------------------
# Toplayıcı (CoinGecko + Yahoo Finance)
# ------------------------------------------------------------
def fetch_live_prices(items: List[Tuple[str, str, str]]) -> Dict[str, Dict[str, float]]:
    """
    items: [(key, feed, code)] listesi
    Dönüş: {key: {price, change_pct, src}}
    Not: Aynı key için birden fazla rota verilmişse, ilk başarılı sonuç kaydedilir.
    """
    out: Dict[str, Dict[str, float]] = {}
    if not items:
        return out

    # 1) CoinGecko toplu
    cg_list = [code for _, feed, code in items if feed == "coingecko"]
    if cg_list:
        try:
            cg_data = coingecko_simple_price(cg_list)
            id_to_key = {code: key for key, feed, code in items if feed == "coingecko"}
            for cg_id, v in cg_data.items():
                key = id_to_key.get(cg_id)
                if not key or key in out:
                    continue
                price = float(v.get("usd"))
                chg = float(v.get("usd_24h_change", 0.0))
                if not math.isfinite(price):
                    continue
                out[key] = {"price": price, "change_pct": chg, "src": "coingecko"}
        except Exception:
            pass

    # 2) yfinance toplu (aynı key için önceden doldurulmamışsa)
    yf_codes = [code for _, feed, code in items if feed == "yfinance"]
    if yf_codes:
        try:
            data = yfinance_quote(yf_codes)
        except Exception:
            data = {}

        code_to_key = {}
        for key, feed, code in items:
            if feed == "yfinance":
                code_to_key.setdefault(code, []).append(key)

        for code, v in data.items():
            keys_for_code = code_to_key.get(code, [])
            for key in keys_for_code:
                if key in out:
                    continue
                price = float(v.get("price", float("nan")))
                chg = float(v.get("change_pct", float("nan")))
                if not math.isfinite(price) or not math.isfinite(chg):
                    continue
                out[key] = {"price": price, "change_pct": chg, "src": f"yfinance:{code}"}

    return out

# ------------------------------------------------------------
# Basit TTL cache – API seviyesinde rate-limit rahatlığı için
# ------------------------------------------------------------
_cache_store: Dict[str, Tuple[float, Dict[str, Dict[str, float]]]] = {}

def _make_cache_key(items: List[Tuple[str, str, str]]) -> str:
    return "|".join(sorted([f"{k}:{f}:{c}" for (k, f, c) in items]))

def fetch_live_prices_cached(items: List[Tuple[str, str, str]], ttl: int = 15) -> Dict[str, Dict[str, float]]:
    if not items:
        return {}
    key = _make_cache_key(items)
    now = time.time()
    ts, val = _cache_store.get(key, (0.0, {}))
    if now - ts < ttl and val:
        return val
    val = fetch_live_prices(items)
    _cache_store[key] = (now, val)
    return val

# ------------------------------------------------------------
# Görünüm yardımcıları
# ------------------------------------------------------------
def format_live_table(snapshot: Dict[str, Dict[str, float]]) -> str:
    """
    Markdown tablo (çok satır). Boşsa '' döner.
    """
    if not snapshot:
        return ""
    header = "**💹 Canlı Fiyat Anlık:**\n| Varlık | Fiyat | Değişim |\n|---|---:|---:|\n"
    lines = []
    for key, v in snapshot.items():
        p = v.get("price")
        c = v.get("change_pct")
        if p is None or c is None:
            continue
        lines.append(f"| {key.upper()} | {p:,.2f} | {c:+.2f}% |")
    return header + "\n".join(lines)

def format_live_inline(snapshot: Dict[str, Dict[str, float]]) -> str:
    """
    Tek satırlık, kısa görünüm. Boşsa '' döner.
    """
    if not snapshot:
        return ""
    parts = []
    for k, v in snapshot.items():
        p = v.get("price")
        c = v.get("change_pct")
        if p is None or c is None:
            continue
        parts.append(f"{k.upper()}: {p:,.2f} ({c:+.2f}%)")
    return " | ".join(parts)