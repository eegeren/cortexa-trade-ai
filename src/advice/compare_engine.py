# src/advice/compare_engine.py
from typing import Optional, List
from .assets import detect_assets_in_text, get_asset
# build_dca_risk_plan importunu kaldırıyoruz
# from .guardrails import build_dca_risk_plan

def render_table(a:dict, b:dict)->str:
    rows = [
        ("Varlık", f"{a['name']}", f"{b['name']}"),
        ("Sınıf", a["class"], b["class"]),
        ("Rol", a["role"], b["role"]),
        ("Volatilite", a["volatility"], b["volatility"]),
        ("Getiri Kaynağı", a["drivers"], b["drivers"]),
        ("Likidite", a["liquidity"], b["liquidity"]),
        ("Portföy Aralığı", a["portfolio_range"], b["portfolio_range"]),
    ]
    out = ["| Özellik | A | B |","|---|---|---|"]
    for k, va, vb in rows:
        out.append(f"| {k} | {va} | {vb} |")
    return "\n".join(out)

def quick_assessment(a:dict, b:dict)->List[str]:
    tips = []
    if a["volatility"] != b["volatility"]:
        tips.append("- **Oynaklık farkı** var; daha oynak tarafa ayıracağın payı düşük tut.")
    if a["class"] != b["class"]:
        tips.append(f"- **Çeşitlendirme:** {a['class']} + {b['class']} birlikte küçük paylarla portföyü dengeleyebilir.")
    if "ETF" in a["liquidity"] or "ETF" in b["liquidity"]:
        tips.append("- **Uygulama:** ETF/tezgahüstü ürünlerin maliyet ve vergilerini karşılaştır.")
    if "Kripto" in (a["class"]+b["class"]):
        tips.append("- **Kripto için** kademeli alım (DCA) ve düşük pozisyon riski kullan.")
    return tips

def compare_or_empty(user_query:str, horizon:str="", risk:str="", capital:Optional[float]=None, stop_pct:Optional[float]=None)->str:
    keys = detect_assets_in_text(user_query)
    if len(keys) < 2:
        return ""
    a_key, b_key = keys[0], keys[1]
    a, b = get_asset(a_key), get_asset(b_key)
    if not (a and b): 
        return ""
    hdr = f"**Hızlı Karşılaştırma (genel bilgi, tavsiye değildir):**\n"
    tbl = render_table(a, b)
    assess = "\n".join(quick_assessment(a, b)) or "- Profiline göre dağılımı küçük adımlarla artır."
    # Artık DCA planını burada üretmiyoruz; sadece tablo + kısa değerlendirme var
    return f"{hdr}\n{tbl}\n\n{assess}"