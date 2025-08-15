import os, math
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Optional

SYMBOL_FILES = {
    # Anahtar: assets.py’deki key  -> data/market dosya adı
    "btc": "btc.csv",   # date,close
    "eth": "eth.csv",
    "sol": "sol.csv",
    "xau": "xau.csv",
    "xag": "xag.csv",
    "wti": "wti.csv",
    "usd": "usdtry.csv",  # ör.: USD/TRY kapanış
    "eur": "eurtry.csv",  # ör.: EUR/TRY kapanış
    "spx": "spx.csv",
    "ndx": "ndx.csv",
    "aapl":"aapl.csv",
    "tsla":"tsla.csv",
}

def _load_series(path:str) -> Optional[pd.Series]:
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    # Beklenen şema: date, close
    if not {"date","close"}.issubset(df.columns):
        return None
    s = df.sort_values("date")["close"].astype(float).reset_index(drop=True)
    return s

def _last_30d_metrics(s: pd.Series) -> Dict[str, float]:
    if s is None or len(s) < 30:
        return {}
    # Son 30 gözlem (gün) al
    s30 = s.iloc[-30:]
    ret_30 = (s30.iloc[-1]/s30.iloc[0]) - 1.0
    # Günlük log getiriler
    import numpy as np
    r = np.log(s30/s30.shift(1)).dropna()
    vol_daily = r.std() if len(r)>0 else 0.0
    vol_annual = vol_daily * math.sqrt(365)
    # Basit trend: 5SMA vs 20SMA
    sma5 = s30.rolling(5).mean().iloc[-1]
    sma20 = s30.rolling(20).mean().iloc[-1]
    trend = "yukarı" if (sma5 is not None and sma20 is not None and sma5 > sma20) else "aşağı/kararsız"
    # Max drawdown (rolling high üzerinden)
    cummax = s30.cummax()
    dd = (s30/cummax - 1.0).min()
    return {
        "ret_30d": float(ret_30),
        "vol_ann": float(vol_annual),
        "trend": trend,
        "mdd_30d": float(dd),
    }

def summarize_assets(keys: List[str]) -> str:
    rows = []
    for k in keys[:4]:  # en fazla 4 varlık göster (UI sade kalsın)
        fname = SYMBOL_FILES.get(k)
        if not fname:
            continue
        s = _load_series(os.path.join("data","market",fname))
        m = _last_30d_metrics(s) if s is not None else {}
        if not m:
            rows.append((k, "Veri yok", "-", "-", "-"))
            continue
        rows.append((
            k,
            f"{m['ret_30d']*100:,.2f}%",
            f"{m['vol_ann']*100:,.2f}%",
            m["trend"],
            f"{m['mdd_30d']*100:,.2f}%"
        ))
    if not rows:
        return ""  # veri bulunamayınca hiç basma

    header = "| Varlık | 30g Getiri | Yıllıklaştırılmış Vol | Trend | 30g Max DD |\n|---|---:|---:|---|---:|\n"
    lines = []
    for k, r, v, t, d in rows:
        lines.append(f"| {k.upper()} | {r} | {v} | {t} | {d} |")
    return "**📈 Son 30 Gün Piyasa Özeti (temsili):**\n" + header + "\n".join(lines)
