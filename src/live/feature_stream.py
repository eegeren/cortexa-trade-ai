import pandas as pd
from feature_engineering import make_features

def last_row_features(df: pd.DataFrame):
    feats = make_features(df)
    last = feats.iloc[-1]
    order = ["ret1","ema_ratio","rsi14","atr14","vol_z","wick_upper_ratio","wick_lower_ratio"]
    return last[order].tolist()

# Not: Canlıda, son bar kapandığında OHLCV'yi güncelleyip last_row_features() çağır.
