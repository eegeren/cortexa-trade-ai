import pandas as pd
import numpy as np

def rsi(series: pd.Series, n: int = 14) -> pd.Series:
    delta = series.diff()
    up = (delta.clip(lower=0)).ewm(alpha=1/n, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = up / (down + 1e-12)
    return 100 - (100 / (1 + rs))

def make_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Basit getiriler ve EMA'lar
    df["ret1"] = df["close"].pct_change()
    df["ema9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema_ratio"] = df["ema9"] / (df["ema20"] + 1e-12) - 1
    # RSI ve basit ATR
    df["rsi14"] = rsi(df["close"], 14)
    tr = (df["high"] - df["low"]).abs()
    df["atr14"] = tr.rolling(14, min_periods=14).mean()
    # Hacim anomali z-skoru
    vmean = df["volume"].rolling(50, min_periods=50).mean()
    vstd  = df["volume"].rolling(50, min_periods=50).std()
    df["vol_z"] = (df["volume"] - vmean) / (vstd + 1e-12)
    # Wick/Gövde oranları
    body = (df["close"] - df["open"]).abs()
    upper = (df["high"] - df[["open","close"]].max(axis=1)).clip(lower=0)
    lower = (df[["open","close"]].min(axis=1) - df["low"]).clip(lower=0)
    df["wick_upper_ratio"] = upper / (body + 1e-9)
    df["wick_lower_ratio"] = lower / (body + 1e-9)
    return df.dropna().reset_index(drop=True)

if __name__ == "__main__":
    import sys, os
    if len(sys.argv) < 3:
        print("Kullanım: python src/feature_engineering.py data/interim/clean.parquet data/features/features.parquet")
        sys.exit(1)
    src, dst = sys.argv[1], sys.argv[2]
    df = pd.read_parquet(src)
    out = make_features(df)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    out.to_parquet(dst, index=False)
    print(f"Özellikler kaydedildi -> {dst} | satır: {len(out)}")
