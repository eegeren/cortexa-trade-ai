import os, sys, time
import pandas as pd

def read_ohlcv_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Beklenen kolonlar: timestamp, open, high, low, close, volume
    required = {"timestamp","open","high","low","close","volume"}
    if not required.issubset(df.columns):
        raise ValueError(f"CSV kolonları eksik. Gerekli: {required}")
    # timestamp -> pandas datetime
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Kullanım: python src/fetch_data.py data/raw/input.csv data/interim/clean.parquet")
        sys.exit(1)
    src, dst = sys.argv[1], sys.argv[2]
    df = read_ohlcv_csv(src)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    df.to_parquet(dst, index=False)
    print(f"Kaydedildi -> {dst} | satır: {len(df)}")
