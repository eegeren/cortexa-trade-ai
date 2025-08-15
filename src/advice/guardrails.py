# src/advice/guardrails.py
from __future__ import annotations

from typing import Optional

DISCLAIMER = (
    "⚠️ Bu içerik genel bilgilendirme amaçlıdır ve yatırım tavsiyesi değildir. "
    "Karar vermeden önce kendi koşullarınızı değerlendiriniz ve gerekirse lisanslı bir uzmana danışınız."
)

PROFILE_QUESTIONS = [
    "1) Hedefin nedir? (sermaye koruma / düzenli gelir / uzun vadeli büyüme)",
    "2) Vade: paraya ne kadar sürede ihtiyaç olabilir? (aylar / yıllar)",
    "3) Risk toleransı: kısa vadede %5–15 dalgalanma rahatsız eder mi?",
    "4) Likidite ihtiyacı: hızlı nakde çevirme gerekebilir mi?",
    "5) Para birimi/vergi hassasiyeti var mı?"
]

# ------------------------------------------------------------
# Kısa giriş
# ------------------------------------------------------------
def build_intro(user_query: str) -> str:
    return (
        f"{DISCLAIMER}\n\n"
        f"Soru: {user_query}\n"
        "Kısa cevap: Seçim profilinize bağlı. Aşağıda özet ve hızlı aksiyon planını paylaşıyorum.\n"
    )

# ------------------------------------------------------------
# Seçenekler – kompakt
# ------------------------------------------------------------
def options_section() -> str:
    return (
        "• **Altın (XAU)**: Enflasyon/şoklara karşı koruma; nakit akışı yok.\n"
        "• **Nakit / Kısa vadeli tahvil**: Düşük oynaklık; reel getiri riski.\n"
        "• **Geniş hisse endeksi**: Büyüme potansiyeli; yüksek volatilite.\n"
        "• **Enflasyona endeksli tahvil / emtia**: Enflasyona karşı koruma.\n"
        "• **Kripto (küçük pay)**: Asimetrik getiri; çok yüksek risk.\n"
    )

def sample_portfolios() -> str:
    return (
        "Örnek (temsili, tavsiye değildir):\n"
        "- Koruma: %60 nakit/tahvil, %20 altın, %20 hisse\n"
        "- Dengeli: %40 tahvil, %15 altın, %45 hisse\n"
        "- Büyüme: %20 tahvil, %10 altın, %65 hisse, %5 alternatif\n"
    )

def action_checklist() -> str:
    return (
        "Aksiyon kontrol listesi:\n"
        "1) Araç seçimi ve maliyet/spread\n"
        "2) Para birimi etkisi (USD ↔ yerel)\n"
        "3) Kademeli alım (DCA)\n"
        "4) Pozisyon başına risk ≤ %1–2\n"
        "5) Günlük kayıp limiti ve kill‑switch\n"
    )

# ------------------------------------------------------------
# Profil bazlı kısa yönlendirme
# ------------------------------------------------------------
def tailor_by_profile(goal: str = "", horizon: str = "", risk: str = "") -> str:
    g = (goal or "").lower()
    h = (horizon or "").lower()
    r = (risk or "").lower()
    lines = []
    if any(k in g for k in ["koruma", "gelir"]):
        lines.append("- Hedef koruma/gelir: altın + kısa vadeli tahvil/nakit ağırlığı artırılabilir.")
    if "büyüme" in g:
        lines.append("- Hedef büyüme: hisse endeksi payı artar; altın %5–15 ile çeşitlendirme.")
    if any(k in h for k in ["uzun", "yıl"]):
        lines.append("- Uzun vade: hisse endeksi mantıklı; düşüş dönemlerine katlanma gerekir.")
    if any(k in h for k in ["kısa", "ay"]):
        lines.append("- Kısa vade: volatiliteyi azaltmak için nakit/tahvil ve altın ağırlığı artırılabilir.")
    if "düşük" in r:
        lines.append("- Düşük risk: volatilitesi düşük araçlar + altın; kripto 0–2%.")
    if "orta" in r:
        lines.append("- Orta risk: dengeli sepet; altın %10–15, hisse %40–50, tahvil %30–40.")
    if "yüksek" in r:
        lines.append("- Yüksek risk: hisse/alternatif payı yüksek; kripto en çok %3–5.")
    return "\n".join(lines) or "- Profil detaylarını paylaşırsan oranları netleştirebilirim."

# ------------------------------------------------------------
# Konu-özel kısa karşılaştırma (sinyal varsa)
# ------------------------------------------------------------
def topic_compare(user_query: str) -> str:
    q = (user_query or "").lower()
    def block(lines: list[str]) -> str:
        return "**Özet:**\n" + "\n".join(f"- {x}" for x in lines) + "\n"

    if "btc" in q and ("xau" in q or "altın" in q or "gold" in q):
        return block([
            "BTC = yüksek beta/dijital; XAU = değer koruma.",
            "Oynaklık: BTC ≫ XAU.",
            "Portföy: BTC küçük pay; XAU %5–15 çeşitlendirme."
        ])
    if "btc" in q and "eth" in q:
        return block([
            "BTC = temel varlık; ETH = akıllı sözleşme riski.",
            "Oynaklık: ETH genelde BTC'den yüksek.",
            "Uzun vade: birlikte küçük/orta pay sepetlenebilir."
        ])
    if ("usd" in q or "dolar" in q) and ("eur" in q or "euro" in q):
        return block([
            "USD = rezerv para; EUR = majör para.",
            "Sürücüler: Fed/ECB politikası, faiz farkı.",
            "Kısa vade: sabit getirili + döviz dengelemesi."
        ])
    if ("altın" in q or "xau" in q) and ("hisse" in q or "endeks" in q or "spx" in q or "bist" in q):
        return block([
            "Altın = koruma/çeşitlendirme; Hisse = büyüme.",
            "Döngüsel dönemlerde hisse öne çıkabilir; belirsizlikte altın.",
            "Portföy: hisse ana gövde, altın %5–15."
        ])
    return ""

# ------------------------------------------------------------
# Kısa DCA + risk planı
# ------------------------------------------------------------
def build_dca_risk_plan(
    user_query: str,
    horizon: Optional[str] = "",
    risk: Optional[str] = "",
    capital: Optional[float] = None,
    stop_pct: Optional[float] = None,
) -> str:
    steps = 6
    stop = stop_pct if (stop_pct is not None and stop_pct > 0) else 0.08
    risk_per_trade = 0.01  # %1
    lines = [
        "📅 **Örnek DCA + Risk Planı** (genel bilgi, tavsiye değildir):",
        f"- DCA periyodu: **aylık**, toplam ~**{steps}** taksit.",
        f"- Varsayılan stop mesafesi: **{stop*100:.1f}%**.",
        f"- Risk seviyesi (pozisyon başına): **{risk_per_trade*100:.1f}%** sermaye.",
    ]
    if capital and capital > 0:
        per_inst = capital / steps
        pos_cash = (capital * risk_per_trade) / stop
        lines += [
            f"- Toplam sermaye: **{capital:,.0f}**.",
            f"- Taksit başına alım (DCA): ~**{per_inst:,.0f}**.",
            f"- Pozisyon tutarı (örnek): **(sermaye × {risk_per_trade:.3f}) / {stop:.3f} ≈ {pos_cash:,.0f}**.",
        ]
    lines += [
        "- Her alımı aynı takvim gününde yap (örn. ayın 5’i/15’i).",
        "- Toplam kayıp limiti (günlük): ≤ **%5**; üç ardışık zarar → **cooldown**.",
    ]
    return "\n".join(lines)

# --- KISA, ODAKLI ÖZET ÜRETİCİSİ ---
from typing import Optional
try:
    # Aynı paket altından varlık tespiti (mevcutsa kullanılır)
    from .assets import detect_assets_in_text
except Exception:
    # Güvenli geri-dönüş: basit anahtar kelime tespiti
    def detect_assets_in_text(text: str):
        text = (text or "").lower()
        keys = []
        mapping = {
            "btc":"btc","bitcoin":"btc",
            "eth":"eth","ethereum":"eth",
            "sol":"sol","solana":"sol",
            "altın":"xau","xau":"xau","gold":"xau",
            "gümüş":"xag","xag":"xag","silver":"xag",
            "euro":"eur","eur":"eur",
            "dolar":"usd","usd":"usd",
            "sp500":"spx","s&p 500":"spx","spx":"spx",
            "nasdaq":"ndx","ndx":"ndx",
            "apple":"aapl","aapl":"aapl",
            "tesla":"tsla","tsla":"tsla",
        }
        for k,v in mapping.items():
            if k in text and v not in keys:
                keys.append(v)
        return keys

def build_brief_answer(
    user_query: str,
    horizon: str = "",
    risk: str = "",
    capital: Optional[float] = None,
    stop_pct: Optional[float] = None,
    leverage: Optional[float] = None,
) -> str:
    """
    Sorunun bağlamına göre 4–6 satırlık, kısa ve odaklı bir özet döner.
    * Burada kesin yatırım tavsiyesi verilmez; uygulanabilir, kompakt rehber dili kullanılır.
    * Disclaimer metni içermez (UI 'suppress_disclaimer' ile yönetiliyor).
    """
    q = (user_query or "").strip()
    hz = (horizon or "").strip()
    rk = (risk or "").strip()

    keys = detect_assets_in_text(q)
    lev = leverage or 1.0

    # Pozisyon/riske dair tek satırlık yardımcı formül (kapasite varsa)
    pos_hint = ""
    if capital and stop_pct and stop_pct > 0:
        # Varsayılan örnek risk: %1 (UI tarafında daha detaylı plan var)
        risk_per_trade = 0.01
        pos_cash = (capital * risk_per_trade) / stop_pct * lev
        pos_hint = f" • Pozisyon limiti≈ {(pos_cash):,.0f} (riske göre)."

    # Başlık satırı (soru + filtreler)
    tags = []
    if hz: tags.append(hz)
    if rk: tags.append(rk)
    tag_str = f" _( {', '.join(tags)} )_" if tags else ""

    # İçerik üretimi
    if len(keys) >= 2:
        a, b = keys[:2]
        lines = [
            f"**Soru:** {q}{tag_str}",
            f"**Özet:** {a.upper()} ↔ {b.upper()} karşılaştırması; hedefe göre seçim yap.",
            "- **Volatilite** ve **taşıma maliyeti/faiz** farklarını dikkate al.",
            "- **Zamanlama riski** için DCA; **pozisyon başına risk ≤ %1** (kaldıraç varsa daha düşük).",
        ]
        if pos_hint:
            lines.append(pos_hint)
        lines.append("- **Kural:** Üç ardışık zarar → 1 kademe ara / pozisyon azalt.")
        return "\n".join(lines)

    if len(keys) == 1:
        a = keys[0]
        lines = [
            f"**Soru:** {q}{tag_str}",
            f"**Özet:** {a.upper()} için kısa değerlendirme.",
            "- **Tetikleyiciler:** trend, volatilite, likidite, haber akışı.",
            "- **Uygulama:** DCA + **pozisyon başına risk ≤ %1**; stop mesafesini oynaklığa göre ayarla.",
        ]
        if pos_hint:
            lines.append(pos_hint)
        return "\n".join(lines)

    # Varlık tespit edilemediyse yönlendir
    lines = [
        f"**Soru:** {q}{tag_str}",
        "**Özet:** Varlık tespit edemedim. Şöyle deneyebilirsin:",
        "- `btc vs euro (6 ay, orta risk, 100k, %2 stop)`",
        "- `altın almalı mıyım? (12 ay, düşük risk)`",
    ]
    return "\n".join(lines)

# --- KALDIRAÇLI MOD: niyet tespiti ve kısa plan üretici -----------------------

def detect_leverage_intent(text: str) -> bool:
    """Soruda kaldıraç/perp/vadeli anahtarları var mı?"""
    if not text:
        return False
    t = text.lower()
    keys = ["kaldıraç", "kaldirac", "leverage", "perp", "perpetual", "vadeli", "futures"]
    return any(k in t for k in keys)

def normalize_risk(risk: str) -> str:
    r = (risk or "").strip().lower()
    if r in ("dusuk","düşük","low"): return "dusuk"
    if r in ("orta","medium","mid"): return "orta"
    if r in ("yuksek","yüksek","high"): return "yuksek"
    return ""

def leverage_by_risk(risk: str) -> int:
    r = normalize_risk(risk)
    return {"dusuk": 2, "orta": 3, "yuksek": 5}.get(r, 3)

def risk_per_trade_by_risk(risk: str) -> float:
    """Sermayeye göre işlem başı risk oranı (varsayılanlar)"""
    r = normalize_risk(risk)
    return {"dusuk": 0.005, "orta": 0.010, "yuksek": 0.015}.get(r, 0.010)

def fmt_money(v: float) -> str:
    try:
        return f"{float(v):,.0f}".replace(",", ".")
    except Exception:
        return str(v)

def build_leverage_answer(
    asset_key: str,
    risk: str,
    capital: float,
    stop_pct: float,
    *,
    leverage: int | None = None,
    entry_price: float | None = None,
) -> str:
    """
    Odaklı, kısa kaldıraçlı plan çıktısı.
    """
    lev = leverage or leverage_by_risk(risk)
    rpt = risk_per_trade_by_risk(risk)

    stop_pct = max(float(stop_pct or 0), 1e-6)
    capital = float(capital or 0)

    # Pozisyon nakit limiti ve kaldıraçlı notional
    pos_cash = (capital * rpt) / stop_pct      # marj/teminat olarak ayırılacak nakit
    notional = pos_cash * lev                  # kaldıraçla toplam pozisyon büyüklüğü

    qty = None
    if entry_price and entry_price > 0:
        qty = notional / entry_price

    lines = []
    lines.append(f"**{asset_key.upper()} Kaldıraçlı Plan (özet)**")
    lines.append(f"- **Risk seviyesi:** {normalize_risk(risk) or 'orta'}")
    lines.append(f"- **Sermaye:** {fmt_money(capital)} ₺")
    lines.append(f"- **Kaldıraç:** {lev}x")
    lines.append(f"- **Stop:** %{stop_pct*100:.2f}")
    lines.append(f"- **İşlem başı risk:** %{rpt*100:.2f} sermaye")
    lines.append(f"- **Teminat (nakit) limiti:** ~{fmt_money(pos_cash)} ₺")
    lines.append(f"- **Pozisyon (notional):** ~{fmt_money(notional)} ₺")
    if entry_price:
        lines.append(f"- **Anlık fiyat:** ~{entry_price:,.2f}")
    if qty:
        lines.append(f"- **Tahmini adet:** ~{qty:,.4f} {asset_key.upper()}")

    lines.append("\n**Uygulama**")
    lines.append("- Giriş: kademeli (2–3 parça); ilk kademede yarım teminat.")
    lines.append("- Çıkış: TP1 %3, TP2 %5; SL tetiklenince tam çık.")
    lines.append("- Günlük toplam zarar limiti: ≤ %3; aşıldığında gün sonuna kadar işlem yapma.")

    return "\n".join(lines) + "\n"