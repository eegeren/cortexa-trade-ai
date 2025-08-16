#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kripto backtest (stabil + cost/cap entegre)
- MultiIndex/çok kolonu normalize eder
- Fiyat kolonlarını Series'e zorlar
- Sınıflandırma: RandomForest (balanced)
- Strateji: proba >= signal_threshold ise LONG; horizon sonunda kapanır
- Cost & Cap backteste dahildir, equity curve ve MDD hesaplanır
"""

import argparse
from dataclasses import dataclass
from typing import Tuple, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix
import yfinance as yf

# ==================== Teknik İndikatörler ====================

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

def macd(close: pd.Series, fast=12, slow=26, signal=9) -> Tuple[pd.Series, pd.Series, pd.Series]:
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

def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    high = pd.to_numeric(high, errors="coerce")
    low = pd.to_numeric(low, errors="coerce")
    close = pd.to_numeric(close, errors="coerce")
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

def atr(high: pd.Series, low: pd.Series, close: pd.Series, period=14) -> pd.Series:
    return true_range(high, low, close).rolling(period).mean()

def adx(high: pd.Series, low: pd.Series, close: pd.Series, period=14) -> pd.Series:
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
    return pd.Series(dx, index=high.index).rolling(period).mean()

# ==================== Özellik İnşası & Etiket ====================

def _as_series(frame: pd.DataFrame, col: str) -> pd.Series:
    s = frame[col]
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    return pd.to_numeric(s, errors="coerce")

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    close = _as_series(out, "Close")
    high  = _as_series(out, "High")
    low   = _as_series(out, "Low")

    out["ema20"]  = ema(close, 20)
    out["ema50"]  = ema(close, 50)
    out["ema200"] = ema(close, 200)

    out["ema20_dist"]  = close / out["ema20"] - 1.0
    out["ema50_dist"]  = close / out["ema50"] - 1.0
    out["ema200_dist"] = close / out["ema200"] - 1.0

    out["rsi14"] = rsi(close, 14)
    out["macd"], out["macd_signal"], out["macd_hist"] = macd(close, 12, 26, 9)
    out["bb_mid"], out["bb_up"], out["bb_low"], out["bbp"] = bollinger(close, 20, 2.0)

    out["atr14"]   = atr(high, low, close, 14)
    out["atr_pct"] = out["atr14"] / close

    out["adx14"] = adx(high, low, close, 14)

    out["ret_1d"] = close.pct_change()
    out["vol_10"] = out["ret_1d"].rolling(10).std(ddof=0)

    out["mom_3"]  = close.pct_change(3)
    out["mom_7"]  = close.pct_change(7)
    out["mom_14"] = close.pct_change(14)

    out = out.replace([np.inf, -np.inf], np.nan).dropna()
    return out

def label_future(df: pd.DataFrame, horizon: int = 5, threshold: float = 0.03) -> pd.DataFrame:
    out = df.copy()
    future = out["Close"].shift(-horizon)
    out["future_ret"] = (future / out["Close"]) - 1.0
    out["target"] = (out["future_ret"] > threshold).astype(int)
    out = out.iloc[:-horizon]  # future_ret sonlarda NaN olur
    return out

# ==================== Strateji & Backtest ====================

@dataclass
class StrategyMetrics:
    n_trades: int
    hit_rate: float
    avg_win: float
    avg_loss: float
    total_return: float
    mdd: float
    equity_last: float

def backtest_with_cost_cap(
    df_pred: pd.DataFrame,
    horizon: int,
    signal_threshold: float = 0.55,
    cost: float = 0.0,
    cap: float = 1.0,
) -> StrategyMetrics:
    """
    Sinyal günü t -> trade kapanışı t+horizon'da.
    Net trade getirisi: cap * (future_ret - 2*cost)
    Equity eğrisi kapanış günlerinde güncellenir.
    """
    dfp = df_pred.copy()
    dfp = dfp.sort_index()  # tarih sırası
    idx = dfp.index

    equity = pd.Series(1.0, index=idx)  # gün içi aynı equity; kapanışlarda sıçrar

    # Sinyal günleri
    signal_mask = dfp["proba"] >= signal_threshold
    signal_days = np.where(signal_mask.values)[0]

    trades = []
    eq = 1.0
    last_eq = 1.0

    for i in signal_days:
        j = i + horizon
        if j >= len(dfp):
            break  # future yok

        raw_ret = dfp.iloc[j]["future_ret"]  # gerçekleşen getiri
        net_trade_ret = cap * (raw_ret - 2.0 * cost)

        # kâr/zarar sınıflandırma için ham future_ret kullan (pozitif/negatif)
        trades.append(raw_ret)

        # equity güncellemesini kapanış gününde uygula
        eq = last_eq * (1.0 + net_trade_ret)
        # i..j-1 arası equity sabit kalır; j gününde sıçrat
        equity.iloc[j:] *= (eq / last_eq)
        last_eq = eq

    # Metrikler
    trades = pd.Series(trades, dtype=float)
    n_trades = int(trades.shape[0])
    if n_trades == 0:
        return StrategyMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, float(equity.iloc[-1]))

    wins = trades[trades > 0]
    losses = trades[trades <= 0]
    hit_rate = wins.shape[0] / n_trades
    avg_win = float(wins.mean()) if wins.shape[0] else 0.0
    avg_loss = float(losses.mean()) if losses.shape[0] else 0.0

    # Toplam bileşik getiri: equity_last - 1
    equity_last = float(equity.iloc[-1])
    total_return = equity_last - 1.0

    # MDD
    roll_max = equity.cummax()
    dd = (equity / roll_max) - 1.0
    mdd = float(dd.min())

    return StrategyMetrics(n_trades, hit_rate, avg_win, avg_loss, total_return, mdd, equity_last)

# ==================== Eğitim & Değerlendirme ====================

def train_evaluate(
    df: pd.DataFrame,
    test_size: float = 0.2,
    random_state: int = 42,
):
    n = df.shape[0]
    n_test = max(1, int(n * test_size))
    n_train = n - n_test
    train = df.iloc[:n_train].copy()
    test  = df.iloc[n_train:].copy()

    feature_cols = [
        "ema20_dist","ema50_dist","ema200_dist","rsi14",
        "macd","macd_signal","macd_hist",
        "bbp","atr_pct","adx14","ret_1d","vol_10","mom_3","mom_7","mom_14",
    ]
    X_train = train[feature_cols].values
    y_train = train["target"].values
    X_test  = test[feature_cols].values
    y_test  = test["target"].values

    model = RandomForestClassifier(
        n_estimators=400, max_depth=6, min_samples_leaf=3,
        class_weight="balanced", random_state=random_state, n_jobs=-1
    )
    model.fit(X_train, y_train)

    proba_test = model.predict_proba(X_test)[:, 1]
    y_pred = (proba_test >= 0.5).astype(int)

    acc = accuracy_score(y_test, y_pred)
    rep = classification_report(y_test, y_pred, digits=3)
    cm  = confusion_matrix(y_test, y_pred)

    proba_all = model.predict_proba(df[feature_cols].values)[:, 1]
    df_pred = df.copy()
    df_pred["proba"] = proba_all
    return df_pred, model, acc, rep, cm

# ==================== Veri İndirme (MultiIndex fix) ====================

def download(symbol: str, start: str, end: str, interval: str = "1d") -> pd.DataFrame:
    print(f"Veri çekiliyor: {symbol} {start} → {end} (interval={interval})")
    df = yf.download(symbol, start=start, end=end, interval=interval)
    if df.empty:
        raise ValueError("YFinance boş veri döndürdü.")

    # MultiIndex kolonları düzleştir
    if isinstance(df.columns, pd.MultiIndex):
        if df.columns.nlevels == 2 and len(df.columns.get_level_values(1).unique()) == 1:
            df = df.droplevel(1, axis=1)
        else:
            first_sym = df.columns.get_level_values(-1).unique()[0]
            df = df.xs(first_sym, axis=1, level=-1)

    need = ["Open","High","Low","Close","Volume"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"Beklenen kolonlar yok: {missing}. Gelen kolonlar: {list(df.columns)}")

    out = pd.DataFrame(index=df.index)
    for c in need:
        col = df[c]
        if isinstance(col, pd.DataFrame):
            col = col.iloc[:, 0]
        out[c] = pd.to_numeric(col, errors="coerce")
    out = out.dropna()
    return out

# ==================== Tam Akış ====================

def run(
    symbol: str,
    start: str,
    end: str,
    interval: str = "1d",
    horizon: int = 5,
    threshold: float = 0.03,
    signal_threshold: float = 0.55,
    test_size: float = 0.2,
    seed: int = 42,
    save_csv: Optional[str] = None,
    cost: float = 0.001,
    cap: float = 0.30
):
    print(f"=== PARAMETRELER ===")
    print(f"Symbol        : {symbol}")
    print(f"Start / End   : {start} → {end}")
    print(f"Interval      : {interval}")
    print(f"Horizon       : {horizon}")
    print(f"Threshold     : {threshold}")
    print(f"Signal Thresh.: {signal_threshold}")
    print(f"Test Size     : {test_size}")
    print(f"Seed          : {seed}")
    print(f"Cost          : {cost}")
    print(f"Cap           : {cap}\n")

    raw = download(symbol, start, end, interval)
    feats = build_features(raw)
    labeled = label_future(feats, horizon=horizon, threshold=threshold)

    df_pred, model, acc, rep, cm = train_evaluate(labeled, test_size=test_size, random_state=seed)

    # Strateji metrikleri (cost & cap dahil)
    strat = backtest_with_cost_cap(
        df_pred, horizon=horizon, signal_threshold=signal_threshold,
        cost=cost, cap=cap
    )

    if save_csv:
        df_pred.to_csv(save_csv, index=True)
        print(f"[+] CSV kaydedildi: {save_csv}")

    # --- Çıktılar ---
    print("\n=== SINIFLANDIRMA SONUÇLARI ===")
    print(f"Accuracy: {acc:.3f}")
    print(rep)
    print("Confusion Matrix (y_true vs y_pred):")
    print(cm)

    print("\n=== BASİT SİNYAL STRATEJİSİ ===")
    print(f"Sinyal eşiği (proba)       : {signal_threshold:.2f}")
    print(f"Toplam trade sayısı        : {strat.n_trades}")
    print(f"Hit rate                   : {strat.hit_rate:.2%}")
    print(f"Ortalama kazanç (win avg)  : {strat.avg_win:.2%}")
    print(f"Ortalama kayıp  (loss avg) : {strat.avg_loss:.2%}")
    print(f"Toplam bileşik getiri      : {strat.total_return:.2%}")
    print(f"Maks. düşüş (MDD)          : {strat.mdd:.2%}")
    print(f"Equity (son)               : {strat.equity_last:.4f}")

    return df_pred, model, acc, strat

# ==================== CLI ====================

def parse_args():
    p = argparse.ArgumentParser(description="Kripto sinyal/backtest (Series-safe, cost/cap entegre).")
    p.add_argument("--symbol", default="BTC-USD")
    p.add_argument("--start",  default="2020-01-01")
    p.add_argument("--end",    default="2024-01-01")
    p.add_argument("--interval", default="1d")
    p.add_argument("--horizon", type=int, default=5)
    p.add_argument("--threshold", type=float, default=0.03)
    p.add_argument("--signal-threshold", type=float, default=0.55)
    p.add_argument("--test-size", type=float, default=0.2)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--save-csv", default="")
    p.add_argument("--cost", type=float, default=0.001, help="İşlem maliyeti (giriş + çıkış toplamı oranı/2 kez uygulanır)")
    p.add_argument("--cap", type=float, default=0.30, help="İşlem başına portföyün azami oranı (0-1)")
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    save_csv = args.save_csv.strip() or None
    run(
        symbol=args.symbol,
        start=args.start,
        end=args.end,
        interval=args.interval,
        horizon=args.horizon,
        threshold=args.threshold,
        signal_threshold=args.signal_threshold,
        test_size=args.test_size,
        seed=args.seed,
        save_csv=save_csv,
        cost=args.cost,
        cap=args.cap,
    )