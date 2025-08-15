import os
import xgboost as xgb
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

CLASSIFIER_PATH = os.getenv("CLASSIFIER_PATH", "models/classifier/xgb_cls.pkl")
TP_PATH = os.getenv("TP_PATH", "models/tp_regressor/xgb_tp.pkl")
SL_PATH = os.getenv("SL_PATH", "models/sl_regressor/xgb_sl.pkl")

app = FastAPI(title="Cortexa Model Server")

# Modelleri yükle
cls = xgb.Booster(); cls.load_model(CLASSIFIER_PATH)
tp_model = xgb.Booster(); tp_model.load_model(TP_PATH)
sl_model = xgb.Booster(); sl_model.load_model(SL_PATH)

FEATURES = ["ret1","ema_ratio","rsi14","atr14","vol_z","wick_upper_ratio","wick_lower_ratio"]

class FeaturePayload(BaseModel):
    features: list  # tek satır: [ret1, ema_ratio, rsi14, atr14, vol_z, wick_upper_ratio, wick_lower_ratio]

@app.post("/classify")
def classify(payload: FeaturePayload):
    import numpy as np
    df = pd.DataFrame([payload.features], columns=FEATURES)
    dX = xgb.DMatrix(df)
    proba = cls.predict(dX)[0].tolist()  # [p(short), p(flat), p(long)]
    side = int(proba.index(max(proba)) - 1)
    return {"proba": proba, "side": side}

@app.post("/tp_sl")
def tp_sl(payload: FeaturePayload):
    df = pd.DataFrame([payload.features], columns=FEATURES)
    dX = xgb.DMatrix(df)
    tp = float(tp_model.predict(dX)[0])
    sl = float(sl_model.predict(dX)[0])
    # Güvenli aralık
    tp = float(max(0.002, min(tp, 0.05)))
    sl = float(max(0.002, min(sl, 0.05)))
    return {"tp_pct": tp, "sl_pct": sl}
