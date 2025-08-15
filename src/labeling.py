import numpy as np
import pandas as pd

def label_future_return(df: pd.DataFrame, n:int=12, thr_long:float=0.0012, thr_short:float=0.0012) -> pd.DataFrame:
    df = df.copy()
    fut = df["close"].shift(-n)
    ret = (fut / df["close"] - 1.0)

    # 1: LONG, -1: SHORT, 0: FLAT
    y = np.where(ret > thr_long, 1, np.where(ret < -thr_short, -1, 0))
    df["y_class"] = y

    # TP/SL yüzdeleri: n penceresinde dağılımdan proxy
    win = ret.rolling(n, min_periods=n).quantile(0.8)
    lose = -ret.rolling(n, min_periods=n).quantile(0.2)
    df["tp_pct"] = win.fillna(0.003).clip(0.001, 0.02)
    df["sl_pct"] = lose.fillna(0.003).clip(0.001, 0.02)

    # eğitimde NA dışla
    return df.dropna(subset=["y_class","tp_pct","sl_pct"]).reset_index(drop=True)

if __name__ == "__main__":
    import sys, os
    if len(sys.argv) < 3:
        print("Kullanım: python src/labeling.py data/features/features.parquet data/features/labeled.parquet")
        raise SystemExit(1)
    src, dst = sys.argv[1], sys.argv[2]
    feats = pd.read_parquet(src)
    out = label_future_return(feats)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    out.to_parquet(dst, index=False)
    print(f"Etiketlendi -> {dst} | satır: {len(out)} | sınıf dağılımı: ",
          dict(zip(*np.unique(out['y_class'], return_counts=True))))
