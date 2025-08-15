# src/advice/advice.py
from typing import Optional, Dict, Any, List
from src.advice.assets import detect_assets_in_text, default_stop_for

def _parse_numbers(text: str) -> Dict[str, Any]:
    t = (text or "").lower()
    out: Dict[str, Any] = {}
    # kaba bir parser: "6 ay", "%2", "100k/100.000"
    import re
    m = re.search(r"(\d{1,2})\s*ay", t)
    if m: out["months"] = int(m.group(1))
    m = re.search(r"%\s*([0-9]+(?:\.[0-9]+)?)\s*stop", t)
    if m: out["stop_pct"] = float(m.group(1)) / 100.0
    m = re.search(r"(\d[\d\.\,]*)(?:\s*k)", t)
    if m:
        val = m.group(1).replace(".", "").replace(",", "")
        out["capital"] = float(val) * 1000
    m = re.search(r"(\d[\d\.\,]+)\s*(?:tl|try|usd|eur|$)", t)
    if "capital" not in out and m:
        val = m.group(1).replace(".", "").replace(",", "")
        try: out["capital"] = float(val)
        except: pass
    return out

def build_recommendation(user_query: str,
                         horizon: str = "",
                         risk: str = "",
                         capital: Optional[float] = None,
                         stop_pct: Optional[float] = None) -> str:
    keys: List[str] = detect_assets_in_text(user_query)
    parsed = _parse_numbers(user_query)
    months = parsed.get("months")
    cap = capital or parsed.get("capital")
    sp = stop_pct or parsed.get("stop_pct")

    # varsayılanlar
    horizon_str = (horizon or (f"{months} ay" if months else "")).strip()
    risk_str = (risk or "orta").strip()
    sp = sp if sp is not None else (0.08 if ("btc" in keys or "eth" in keys) else 0.02)

    # dağılım kuralları (çok basit)
    alloc_btc = alloc_eur = alloc_xau = None
    notes = []
    if "btc" in keys and "eur" in keys:
        # Soruya özel: BTC + EUR
        alloc_btc = " %10–15"
        alloc_eur = " %35–45"
        notes.append("6 ay/orta risk: ana ağırlık EUR’de; BTC’ye küçük, kademeli pay.")
    elif "btc" in keys:
        alloc_btc = " %10–20" if risk_str == "yüksek" else " %5–15"
        notes.append("Kripto oynak; DCA ve küçük pay.")
    elif "eur" in keys or "usd" in keys:
        alloc_eur = " %30–60"
        notes.append("Kur tarafı daha düşük volatil; kademeli geçiş önerilir.")
    else:
        # genel fallback
        alloc_xau = " %5–15"
        notes.append("Genel: altın 5–15, hisse/tahvil hedefe göre ayarlanır.")

    # risk/miktar örneği
    sizing = []
    if cap:
        risk_per_trade = 0.01 if risk_str != "yüksek" else 0.02
        stop_for_calc = sp
        pos_cash = (cap * risk_per_trade) / max(stop_for_calc, 1e-9)
        sizing.append(f"Risk başına ≈ {risk_per_trade*100:.0f}% → pozisyon nakdi ≈ {pos_cash:,.0f} (stop {stop_for_calc*100:.1f}%)")

    # canlı fiyat tablosu zaten server tarafında ekleniyor
    lines = []
    lines.append(f"— Hızlı Değerlendirme —")
    if "btc" in keys:
        lines.append("• BTC: Yüksek oynaklık; kısa vadede şoklara açık.")
    if "eur" in keys:
        lines.append("• EUR/TRY: Faiz farkı + kur dinamiği; BTC’ye göre düşük oynaklık.")
    if "xau" in keys:
        lines.append("• Altın: Reel faiz ve belirsizlikte koruma eğilimi.")

    lines.append("")
    lines.append("— Önerilen Dağılım (temsili) —")
    if alloc_btc: lines.append(f"• BTC:{alloc_btc} (DCA ile 6 taksit)")
    if alloc_eur: lines.append(f"• EUR:{alloc_eur}")
    if alloc_xau: lines.append(f"• Altın:{alloc_xau}")
    lines.append("• Kalan: hedefe uygun nakit/bono/hisse karması")

    lines.append("")
    lines.append("— Pozisyonlama —")
    if sizing: lines.append(f"• {sizing[0]}")
    else: lines.append("• Risk başına %1–2; DCA ve günlük toplam kayıp limiti ≤ %5.")
    lines.append("• 3 ardışık zarar → 1 ay ‘cooldown’")

    lines.append("")
    lines.append("— Neden böyle? —")
    if notes:
        lines.append("• " + " ".join(notes))
    else:
        lines.append("• Vade/risk profilin kısa vadede düşük oynaklık ağırlığına işaret ediyor.")

    prefix = f"Soru: {user_query} — Vade: {horizon_str or 'belirtilmedi'} | Risk: {risk_str}" + (f" | Sermaye: {cap:,.0f}" if cap else "")
    return prefix + "\n\n" + "\n".join(lines) + "\n"