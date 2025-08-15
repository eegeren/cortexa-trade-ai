import numpy as np
import pandas as pd
import xgboost as xgb

FEE = 0.0006
SLIP = 0.0002

def run_backtest(df: pd.DataFrame, proba: np.ndarray, tp_pct: np.ndarray, sl_pct: np.ndarray,
                 risk_per_trade: float=0.01):
    equity = 1.0
    peak = 1.0
    pnl_curve = []
    for i in range(len(df)-2):
        side = np.argmax(proba[i]) - 1  # -1,0,1
        if side == 0:
            pnl_curve.append(equity); continue
        entry = df["close"].iloc[i+1] * (1 + SLIP*np.sign(side))
        # Basit bar-sonu çıkış (gerçek bar-içi tp/sl simülasyonu eklenebilir)
        exit_price = df["close"].iloc[i+2]
        gross_ret = (exit_price/entry - 1) * side
        net_ret = gross_ret - FEE
        equity *= (1 + net_ret * (risk_per_trade/0.01))
        peak = max(peak, equity)
        pnl_curve.append(equity)
    dd = (peak - equity)/peak if peak>0 else 0
    return equity, dd, np.array(pnl_curve)

if __name__ == "__main__":
    import sys, os, joblib
    if len(sys.argv) < 5:
        print("Kullanım: python src/backtest.py data/features/labeled.parquet models/classifier/xgb_cls.pkl models/tp_regressor/xgb_tp.pkl models/sl_regressor/xgb_sl.pkl")
        sys.exit(1)
    feats_path, cls_path, tp_path, sl_path = sys.argv[1:5]
    df = pd.read_parquet(feats_path)
    X = df[["ret1","ema_ratio","rsi14","atr14","vol_z","wick_upper_ratio","wick_lower_ratio"]]
    dX = xgb.DMatrix(X)
    cls = xgb.Booster(); cls.load_model(cls_path)
    proba = cls.predict(dX)
    # TP/SL şimdilik sadece raporlama için yükleniyor (backtest'te bar-sonu çıkış kullandık)
    print("Sınıflandırıcı yüklendi. Prob şekli:", proba.shape)
    eq, dd, curve = run_backtest(df, proba, df["tp_pct"].values, df["sl_pct"].values)
    os.makedirs("reports", exist_ok=True)
    np.savetxt("reports/pnl_curve.csv", curve, delimiter=",")
    print(f"Backtest BİTTİ | Final Equity: {eq:.3f} | Max DD: {dd:.3%} | PNL noktaları: {len(curve)}")
