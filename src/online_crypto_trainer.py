#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Online (kademeli) kripto modeli
- init: geçmiş verilerle ilk eğitim
- update: son çalışmadan bu yana gelen mumlarla partial_fit
Artefaktlar: artifacts/<symbol>/
  - model.joblib   : SGDClassifier (logistic)
  - scaler.joblib  : StandardScaler (partial_fit destekli)
  - state.json     : en son işlenen tarih
  - features.csv   : son snapshot (opsiyonel)
"""

import argparse, json, os, sys, time
from pathlib import Path
from typing import Optional, Tuple, List

import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.linear_model import SGDClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix
from joblib import dump, load

# ============ Teknik indikatörler ============

def ema(s: pd.Series, span: int) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").ewm(span=span, adjust=False).mean()

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    close = pd.to_numeric(close, errors="coerce")
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    roll_up = up.ewm(alpha=1/period, adjust=False).mean()
    roll_down = down.ewm(alpha=1/period, adjust=False).mean()
    rs = roll_up / (roll_down + 1e-12)
    return 100 - (100 / (1 + rs))

def macd(close: pd.Series, fast=12, slow=26, signal=9):
    close = pd.to_numeric(close, errors="coerce")
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def bollinger(close: pd.Series, period=20, k=2.0):
    close = pd.to_numeric(close, errors="coerce")
    mavg = close.rolling(period).mean()
    mstd = close.rolling(period).std(ddof=0)
    upper = mavg + k * mstd
    lower = mavg - k * mstd
    bbp = (close - lower) / ((upper - lower).replace(0, np.nan))
    return mavg, upper, lower, bbp

def true_range(high, low, close):
    high = pd.to_numeric(high, errors="coerce")
    low = pd.to_numeric(low, errors="coerce")
    close = pd.to_numeric(close, errors="coerce")
    pc = close.shift(1)
    tr1 = high - low
    tr2 = (high - pc).abs()
    tr3 = (low - pc).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

def atr(high, low, close, period=14):
    return true_range(high, low, close).rolling(period).mean()

def adx(high, low, close, period=14):
    high = pd.to_numeric(high, errors="coerce")
    low = pd.to_numeric(low, errors="coerce")
    close = pd.to_numeric(close, errors="coerce")
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = true_range(high, low, close)
    atr_n = tr.rolling(period).mean()
    plus_di = 100 * pd.Series(plus_dm, index=high.index).rolling(period).sum() / (atr_n * period)
    minus_di = 100 * pd.Series(minus_dm, index=high.index).rolling(period).sum() / (atr_n * period)
    dx = 100 * (plus_di - minus_di).abs() / ((plus_di + minus_di).replace(0, np.nan))
    return dx.rolling(period).mean()

# ============ Özellik/Etiket ============

FEATURES = [
    "ema20_dist","ema50_dist","ema200_dist","rsi14",
    "macd","macd_signal","macd_hist",
    "bbp","atr_pct","adx14","ret_1d","vol_10","mom_3","mom_7","mom_14",
]

def _col(frame: pd.DataFrame, name: str) -> pd.Series:
    s = frame[name]
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:,0]
    return pd.to_numeric(s, errors="coerce")

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    close = _col(out, "Close"); high = _col(out, "High"); low = _col(out, "Low")

    out["ema20"]  = ema(close, 20);  out["ema50"]  = ema(close, 50);  out["ema200"] = ema(close, 200)
    out["ema20_dist"]  = close/out["ema20"] - 1.0
    out["ema50_dist"]  = close/out["ema50"] - 1.0
    out["ema200_dist"] = close/out["ema200"] - 1.0

    out["rsi14"] = rsi(close, 14)
    out["macd"], out["macd_signal"], out["macd_hist"] = macd(close, 12,26,9)
    out["bb_mid"], out["bb_up"], out["bb_low"], out["bbp"] = bollinger(close, 20, 2.0)

    out["atr14"]  = atr(high, low, close, 14)
    out["atr_pct"] = out["atr14"] / close
    out["adx14"]  = adx(high, low, close, 14)

    out["ret_1d"] = close.pct_change()
    out["vol_10"] = out["ret_1d"].rolling(10).std(ddof=0)

    out["mom_3"]  = close.pct_change(3)
    out["mom_7"]  = close.pct_change(7)
    out["mom_14"] = close.pct_change(14)

    out = out.replace([np.inf,-np.inf], np.nan).dropna()
    return out

def label_future(df_feats: pd.DataFrame, horizon=5, threshold=0.03) -> pd.DataFrame:
    out = df_feats.copy()
    future = out["Close"].shift(-horizon)
    out["future_ret"] = (future/out["Close"]) - 1.0
    out["target"] = (out["future_ret"] > threshold).astype(int)
    out = out.iloc[:-horizon]
    return out

# ============ Veri ============

def download(symbol: str, start: str, end: str, interval="1d") -> pd.DataFrame:
    print(f"Veri çekiliyor: {symbol} {start} → {end} (interval={interval})")
    df = yf.download(symbol, start=start, end=end, interval=interval)
    if df.empty:
        raise ValueError("YFinance boş veri döndürdü.")

    if isinstance(df.columns, pd.MultiIndex):
        if df.columns.nlevels == 2 and len(df.columns.get_level_values(1).unique()) == 1:
            df = df.droplevel(1, axis=1)
        else:
            first_sym = df.columns.get_level_values(-1).unique()[0]
            df = df.xs(first_sym, axis=1, level=-1)

    need = ["Open","High","Low","Close","Volume"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"Beklenen kolonlar yok: {missing}. Gelen: {list(df.columns)}")

    out = pd.DataFrame(index=df.index)
    for c in need:
        col = df[c]
        if isinstance(col, pd.DataFrame):
            col = col.iloc[:,0]
        out[c] = pd.to_numeric(col, errors="coerce")
    return out.dropna()

# ============ Model IO ============

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def save_state(dir_: Path, last_dt: str):
    with open(dir_/ "state.json", "w") as f:
        json.dump({"last_dt": last_dt}, f)

def load_state(dir_: Path) -> Optional[str]:
    p = dir_/ "state.json"
    if not p.exists(): return None
    try:
        with open(p, "r") as f:
            return json.load(f).get("last_dt")
    except: return None

# ============ Eğitim / Update ============

def init_train(symbol: str, start: str, end: str, interval: str,
               horizon: int, threshold: float,
               out_dir: Path):
    raw   = download(symbol, start, end, interval)
    feats = build_features(raw)
    data  = label_future(feats, horizon=horizon, threshold=threshold)

    X = data[FEATURES].values.astype(np.float64)
    y = data["target"].values.astype(np.int32)

    scaler = StandardScaler(with_mean=True, with_std=True)
    scaler.partial_fit(X)                # tüm geçmişle fit
    Xs = scaler.transform(X)

    model = SGDClassifier(loss="log_loss", penalty="l2", alpha=1e-4,
                          max_iter=1, learning_rate="optimal",
                          random_state=42)
    # sınıfları ilk çağrıda veriyoruz
    model.partial_fit(Xs, y, classes=np.array([0,1], dtype=np.int32))

    ensure_dir(out_dir)
    dump(model, out_dir/"model.joblib")
    dump(scaler, out_dir/"scaler.joblib")
    data.to_csv(out_dir/"features.csv")
    last_dt = str(data.index[-1].date())
    save_state(out_dir, last_dt)

    # hızlı rapor
    y_pred = (model.predict_proba(Xs)[:,1] >= 0.5).astype(int)
    acc = accuracy_score(y, y_pred)
    print(f"[init] örnek={len(y)} acc={acc:.3f}")
    print(classification_report(y, y_pred, digits=3))
    print(confusion_matrix(y, y_pred))

def update_train(symbol: str, since: str, end: str, interval: str,
                 horizon: int, threshold: float,
                 out_dir: Path):
    # since tarihinden END’e kadar yeni veri
    raw   = download(symbol, since, end, interval)
    feats = build_features(raw)
    data  = label_future(feats, horizon=horizon, threshold=threshold)
    if data.empty:
        print("[update] yeni veri yok.")
        return

    model  = load(out_dir/"model.joblib")
    scaler = load(out_dir/"scaler.joblib")

    X = data[FEATURES].values.astype(np.float64)
    y = data["target"].values.astype(np.int32)

    # scaler’ı da kademeli güncelle
    scaler.partial_fit(X)
    Xs = scaler.transform(X)

    # birkaç epoch küçük bite-size update (stabilizasyon için)
    for _ in range(3):
        model.partial_fit(Xs, y)

    dump(model, out_dir/"model.joblib")
    dump(scaler, out_dir/"scaler.joblib")
    data.to_csv(out_dir/"features.csv")

    last_dt = str(data.index[-1].date())
    save_state(out_dir, last_dt)

    # mini rapor
    y_pred = (model.predict_proba(Xs)[:,1] >= 0.5).astype(int)
    acc = accuracy_score(y, y_pred)
    print(f"[update] yeni_örnek={len(y)} acc={acc:.3f}")

# ============ CLI ============

def main():
    ap = argparse.ArgumentParser(description="Online kripto eğitici (init/update).")
    ap.add_argument("--mode", choices=["init","update"], required=True)
    ap.add_argument("--symbol", default="BTC-USD")
    ap.add_argument("--start",  default="2020-01-01")
    ap.add_argument("--end",    default=None, help="YYYY-MM-DD, boşsa bugün")
    ap.add_argument("--interval", default="1d")
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--threshold", type=float, default=0.03)
    ap.add_argument("--artifacts", default="artifacts")
    args = ap.parse_args()

    end = args.end or pd.Timestamp.utcnow().date().isoformat()
    out_dir = Path(args.artifacts) / args.symbol
    ensure_dir(out_dir)

    if args.mode == "init":
        init_train(args.symbol, args.start, end, args.interval, args.horizon, args.threshold, out_dir)
    else:
        last_dt = load_state(out_dir)
        if not last_dt:
            print("[update] state bulunamadı, önce --mode init çalıştırın.")
            sys.exit(1)
        # yfinance end exclusive olabilir → güvenli olmak için last_dt - 5 gün
        since = (pd.to_datetime(last_dt) - pd.Timedelta(days=5)).date().isoformat()
        update_train(args.symbol, since, end, args.interval, args.horizon, args.threshold, out_dir)

if __name__ == "__main__":
    main()