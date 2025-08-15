# src/advice/leverage.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any
import math
import re

# Basit kaldıraç yakalama: "5x", "x10", "10 x", "kaldıraç 3" vb.
_LEV_PAT = re.compile(r"(?:(\d+)\s*[xX])|(?:[xX]\s*(\d+))|(?:kaldıra[çc]\s*(\d+))")

def parse_leverage_from_text(text: str, default: int = 3, hard_min: int = 1, hard_max: int = 20) -> int:
    if not text:
        return default
    m = _LEV_PAT.search(text.lower())
    if not m:
        return default
    for g in m.groups():
        if g:
            try:
                v = int(g)
                return max(hard_min, min(hard_max, v))
            except Exception:
                continue
    return default

@dataclass
class LeverageInputs:
    asset_key: str
    capital: float
    risk_per_trade: float   # örn 0.01 = %1
    stop_pct: float         # örn 0.02 = %2
    leverage: int           # örn 5
    entry_price: Optional[float] = None
    maintenance_margin: float = 0.01  # yaklaşık; borsaya göre değişir (%0.5–1.0+)

@dataclass
class LeveragePlan:
    notional: float                 # hedef pozisyon büyüklüğü (USD/TL karşılığı)
    initial_margin: float           # gereken başlangıç teminat (notional/leverage)
    free_cash_left: float           # sermayede kalan pay
    qty_estimate: Optional[float]   # adet (entry_price varsa)
    r_value: float                  # 1R değeri (sermaye*risk_per_trade)
    liq_buffer_pct_est: float       # yaklaşık likidasyon uzaklığı (%)
    scenarios: Dict[str, Dict[str, float]]  # {"-1R": {...}, "+1R": {...}, ...}
    warnings: list                  # metinsel uyarılar

def build_leverage_plan(inp: LeverageInputs) -> LeveragePlan:
    cap = max(0.0, float(inp.capital))
    rpt = max(0.0, float(inp.risk_per_trade))
    stop = max(1e-6, float(inp.stop_pct))
    lev  = max(1, int(inp.leverage))
    mm   = max(0.0, float(inp.maintenance_margin))

    # 1) Hedef notional (risk tabanlı) — kaldıraçtan bağımsızdır
    # risk ≈ notional * stop_pct  =>  notional ≈ risk / stop_pct
    r_value = cap * rpt
    notional = r_value / stop

    # 2) Başlangıç teminat gereksinimi
    initial_margin = notional / lev
    free_cash_left = max(0.0, cap - initial_margin)

    # 3) Adet tahmini
    qty = None
    if inp.entry_price and inp.entry_price > 0:
        qty = notional / inp.entry_price

    # 4) Yaklaşık likidasyon uzaklığı
    # Linear perp için kaba yaklaşım: liquidation buffer ≈ 1/leverage - maintenance_margin
    # (komisyon/finansman/paylaşım vb. ihmal edilmiştir)
    liq_buffer = (1.0 / lev) - mm
    if liq_buffer < 0:
        liq_buffer = 0.0

    # 5) Senaryolar (brüt PnL ~ notional * hareket yüzdesi)
    # -1R: -r_value (stop)
    # -2R: slippage/gap gibi daha kötü durum
    # +1R: +r_value (hedef)
    # +2R: +2*r_value
    scenarios = {
        "-2R": {"pnl": -2.0 * r_value, "equity_after": cap - 2.0 * r_value},
        "-1R": {"pnl": -1.0 * r_value, "equity_after": cap - 1.0 * r_value},
        "+1R": {"pnl": +1.0 * r_value, "equity_after": cap + 1.0 * r_value},
        "+2R": {"pnl": +2.0 * r_value, "equity_after": cap + 2.0 * r_value},
    }

    warnings = []
    if initial_margin > cap * 0.7:
        warnings.append("Başlangıç teminatı sermayenin %70’inden fazla — kaldıraç veya notional yüksek olabilir.")
    if liq_buffer <= stop:
        warnings.append("Stop mesafesi likidasyona çok yakın görünüyor — kaldıraç veya stop’u gözden geçir.")

    return LeveragePlan(
        notional=float(notional),
        initial_margin=float(initial_margin),
        free_cash_left=float(free_cash_left),
        qty_estimate=float(qty) if qty else None,
        r_value=float(r_value),
        liq_buffer_pct_est=float(liq_buffer * 100.0),
        scenarios=scenarios,
        warnings=warnings,
    )

def format_leverage_markdown(asset_key: str, entry_price: Optional[float], plan: LeveragePlan, leverage: int) -> str:
    price_line = f"\n• Piyasa fiyatı (yaklaşık): **{entry_price:,.4f}**" if entry_price else ""
    qty_line   = f"\n• Tahmini adet: **{plan.qty_estimate:,.6f}**" if plan.qty_estimate else ""

    rows = []
    for k in ["-2R","-1R","+1R","+2R"]:
        s = plan.scenarios[k]
        rows.append(f"| {k} | {s['pnl']:,.2f} | {s['equity_after']:,.2f} |")

    warns = ""
    if plan.warnings:
        warns = "\n\n**Uyarılar:**\n" + "\n".join([f"- {w}" for w in plan.warnings])

    md = (
        f"**{asset_key.upper()} — Kaldıraçlı Plan (x{leverage})**\n"
        f"• Hedef notional: **{plan.notional:,.2f}**\n"
        f"• Gerekli başlangıç teminatı: **{plan.initial_margin:,.2f}**\n"
        f"• Kalan serbest nakit: **{plan.free_cash_left:,.2f}**\n"
        f"• 1R (risk): **{plan.r_value:,.2f}**\n"
        f"• Yaklaşık likidasyon uzaklığı: **{plan.liq_buffer_pct_est:.2f}%**"
        f"{price_line}{qty_line}\n\n"
        f"**Senaryolar (brüt):**\n"
        f"| Senaryo | PnL | Yeni Sermaye |\n|---|---:|---:|\n" + "\n".join(rows) +
        warns +
        "\n\n_Not: Bu basitleştirilmiş bir risk taslağıdır; borsaya özgü likidasyon, bakım marjı, fonlama/komisyon farklılıkları ve kademeli marjlar dikkate alınmamıştır._"
    )
    return md