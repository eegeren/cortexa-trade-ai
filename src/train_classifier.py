import os
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import f1_score

FEATURES = ["ret1","ema_ratio","rsi14","atr14","vol_z","wick_upper_ratio","wick_lower_ratio"]

def undersample_flat(df, target_col="y_class", max_flat_ratio=0.6, random_state=42):
    # -1,0,1 sınıfları
    counts = df[target_col].value_counts()
    if 0 not in counts:
        return df
    n_total = len(df)
    n_flat = counts.get(0, 0)
    # FLAT çok baskınsa kıs
    if n_flat / n_total > max_flat_ratio:
        keep_flat = int(max_flat_ratio * n_total)
        flat_idx = df[df[target_col]==0].sample(keep_flat, random_state=random_state).index
        nonflat_idx = df[df[target_col]!=0].index
        df = df.loc[flat_idx.union(nonflat_idx)].sort_index()
    return df

def train_xgb(X: pd.DataFrame, y: pd.Series):
    tscv = TimeSeriesSplit(n_splits=5)
    best, best_f1 = None, -1
    for tr, va in tscv.split(X):
        trD = xgb.DMatrix(X.iloc[tr], label=y.iloc[tr])
        vaD = xgb.DMatrix(X.iloc[va], label=y.iloc[va])
        params = dict(
            max_depth=6, eta=0.05, subsample=0.9, colsample_bytree=0.8,
            objective="multi:softprob", num_class=3, eval_metric="mlogloss"
        )
        bst = xgb.train(params, trD, num_boost_round=2000,
                        evals=[(vaD,"val")], early_stopping_rounds=100, verbose_eval=False)
        pred = bst.predict(vaD).argmax(axis=1)
        f1 = f1_score(y.iloc[va], pred, average="macro")
        if f1 > best_f1:
            best, best_f1 = bst, f1
    return best, best_f1

if __name__ == "__main__":
    import sys, joblib
    if len(sys.argv) < 3:
        print("Kullanım: python src/train_classifier.py data/features/labeled.parquet models/classifier/xgb_cls.pkl")
        raise SystemExit(1)
    src, dst = sys.argv[1], sys.argv[2]
    df = pd.read_parquet(src)

    # sınıf dengesi
    df = undersample_flat(df, "y_class", max_flat_ratio=0.6)
    X = df[FEATURES]
    y = (df["y_class"] + 1).astype(int)  # -1,0,1 -> 0,1,2

    model, score = train_xgb(X, y)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    model.save_model(dst)
    print(f"Sınıflandırıcı kaydedildi -> {dst} | Macro-F1: {score:.4f} | veri: {len(df)} satır")
