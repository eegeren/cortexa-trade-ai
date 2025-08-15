import os, joblib
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error

FEATURES = [
    "ret1","ema_ratio","rsi14","atr14","vol_z",
    "wick_upper_ratio","wick_lower_ratio"
]

def train_regressor(X: pd.DataFrame, y: pd.Series):
    tscv = TimeSeriesSplit(n_splits=5)
    best, best_mae = None, 1e9
    for tr, va in tscv.split(X):
        trD = xgb.DMatrix(X.iloc[tr], label=y.iloc[tr])
        vaD = xgb.DMatrix(X.iloc[va], label=y.iloc[va])
        params = dict(
            max_depth=6, eta=0.05, subsample=0.9, colsample_bytree=0.8,
            objective="reg:squarederror", eval_metric="mae"
        )
        bst = xgb.train(params, trD, num_boost_round=2000,
                        evals=[(vaD,"val")], early_stopping_rounds=100, verbose_eval=False)
        pred = bst.predict(vaD)
        mae = mean_absolute_error(y.iloc[va], pred)
        if mae < best_mae:
            best, best_mae = bst, mae
    return best, best_mae

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("Kullanım: python src/train_tp_sl_regressor.py data/features/labeled.parquet models/tp_regressor/xgb_tp.pkl models/sl_regressor/xgb_sl.pkl")
        sys.exit(1)
    src, dst_tp, dst_sl = sys.argv[1], sys.argv[2], sys.argv[3]
    df = pd.read_parquet(src)
    X = df[FEATURES]
    tp = df["tp_pct"].clip(0.002, 0.05)
    sl = df["sl_pct"].clip(0.002, 0.05)
    m_tp, mae_tp = train_regressor(X, tp)
    os.makedirs(os.path.dirname(dst_tp), exist_ok=True)
    m_tp.save_model(dst_tp)
    print(f"TP regressor -> {dst_tp} | MAE: {mae_tp:.5f}")
    m_sl, mae_sl = train_regressor(X, sl)
    os.makedirs(os.path.dirname(dst_sl), exist_ok=True)
    m_sl.save_model(dst_sl)
    print(f"SL regressor -> {dst_sl} | MAE: {mae_sl:.5f}")
