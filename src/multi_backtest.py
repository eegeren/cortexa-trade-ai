#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import re
import csv
from pathlib import Path

import pandas as pd

# --------- Parametreler ---------
symbols = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD"]

start = "2021-01-01"
end = "2024-01-01"
interval = "1d"
horizon = 5
threshold = 0.03
signal_threshold = 0.60
test_size = 0.20
cost = 0.001
cap = 0.30

script_path = Path("src/crypto_model_backtest.py")  # backtest scriptin konumu
out_csv = Path("results.csv")
out_xlsx = Path("results.xlsx")  # İstersen kapatabilirsin


# --------- Yardımcı: metin satırından ilk sayıyı çek ---------
_num = re.compile(r"[-+]?\d+(?:\.\d+)?")
def first_num(s: str, default="-"):
    m = _num.findall(s)
    return m[0] if m else default


# --------- Koşu & Parse ---------
rows = []
for sym in symbols:
    print(f"\n=== {sym} backtest başlıyor ===")

    cmd = [
        "python", str(script_path),
        "--symbol", sym,
        "--start", start,
        "--end", end,
        "--interval", interval,
        "--horizon", str(horizon),
        "--threshold", str(threshold),
        "--signal-threshold", str(signal_threshold),
        "--test-size", str(test_size),
        "--cost", str(cost),
        "--cap", str(cap),
    ]

    run = subprocess.run(cmd, capture_output=True, text=True)
    out = run.stdout
    if run.returncode != 0:
        print(f"[!] {sym} hata (kod {run.returncode}). stderr:\n{run.stderr}")

    # Varsayılanlar
    acc = hit_rate = win_avg = loss_avg = total_return = mdd = equity = "-"

    for line in out.splitlines():
        L = line.strip()
        if L.startswith("Accuracy:"):
            acc = first_num(L)
        elif L.startswith("Hit rate"):
            hit_rate = first_num(L)          # yüzde değerin ilk sayısı
        elif "Ortalama kazanç" in L:
            win_avg = first_num(L)
        elif "Ortalama kayıp" in L:
            loss_avg = first_num(L)
        elif "Toplam bileşik getiri" in L:
            total_return = first_num(L)
        elif "Maks. düşüş" in L:
            mdd = first_num(L)
        elif L.startswith("Equity"):
            equity = first_num(L)

    rows.append({
        "Symbol": sym, "Start": start, "End": end, "Interval": interval,
        "Horizon": horizon, "Threshold": threshold, "Signal Thresh": signal_threshold,
        "Test Size": test_size, "Cost": cost, "Cap": cap,
        "Accuracy": acc, "Hit Rate": hit_rate, "Win Avg": win_avg,
        "Loss Avg": loss_avg, "Total Return": total_return,
        "MDD": mdd, "Equity": equity
    })

# --------- DataFrame & Kaydet ---------
df = pd.DataFrame(rows, columns=[
    "Symbol","Start","End","Interval","Horizon","Threshold","Signal Thresh",
    "Test Size","Cost","Cap","Accuracy","Hit Rate","Win Avg","Loss Avg",
    "Total Return","MDD","Equity"
])

# Sayısal kolonları güzelleştir (yüzdeleri % olarak tutmak istersen bu kısmı değiştirme)
for col in ["Accuracy","Hit Rate","Win Avg","Loss Avg","Total Return","MDD","Equity"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

df.to_csv(out_csv, index=False)
print(f"\n✅ Sonuçlar CSV: {out_csv.resolve()}")

try:
    df.to_excel(out_xlsx, index=False)
    print(f"✅ Sonuçlar Excel: {out_xlsx.resolve()}")
except Exception as e:
    print(f"ℹ️ Excel kaydı atlandı: {e}")

# Konsolda tablo
print("\n=== Özet Tablo ===")
print(df.to_string(index=False, justify='center', col_space=12))