# src/advice/assets.py

"""
Varlık sözlüğü + eşanlamlar.
Her varlık için:
- feed: "coingecko" veya "yfinance"
- code: beslemede kullanılan sembol/kimlik
- default_stop: örnek risk planı için varsayılan stop oranı
"""

ASSETS = {
    # --- Kripto (CoinGecko kimlikleri) ---
    "btc": {
        "name": "Bitcoin (BTC)",
        "class": "Kripto",
        "role": "Dijital değer deposu / beta",
        "volatility": "Çok yüksek",
        "drivers": "Benimsenme, likidite, regülasyon",
        "liquidity": "Çok yüksek",
        "portfolio_range": "%0–5",
        "default_stop": 0.08,
        "feed": "coingecko",
        "code": "bitcoin",
    },
    "eth": {
        "name": "Ethereum (ETH)",
        "class": "Kripto",
        "role": "Akıllı sözleşme platformu",
        "volatility": "Çok yüksek",
        "drivers": "DeFi, NFT, L2 ekosistemi",
        "liquidity": "Çok yüksek",
        "portfolio_range": "%0–5",
        "default_stop": 0.10,
        "feed": "coingecko",
        "code": "ethereum",
    },
    "sol": {
        "name": "Solana (SOL)",
        "class": "Kripto",
        "role": "Yüksek hızlı L1",
        "volatility": "Çok yüksek",
        "drivers": "NFT, DeFi, ekosistem büyümesi",
        "liquidity": "Yüksek",
        "portfolio_range": "%0–3",
        "default_stop": 0.12,
        "feed": "coingecko",
        "code": "solana",
    },

    # --- Emtia (Yahoo Finance) ---
    "xau": {
        "name": "Altın (XAU)",
        "class": "Emtia",
        "role": "Değer koruma/çeşitlendirme",
        "volatility": "Düşük-Orta",
        "drivers": "Reel faiz, belirsizlik, USD",
        "liquidity": "Çok yüksek (ETF/tezgahüstü)",
        "portfolio_range": "%5–15",
        "default_stop": 0.03,
        "feed": "yfinance",
        "code": "XAUUSD=X",  # fallback: GC=F -> GLD (price_feeds.py YF_FALLBACKS)
    },
    "xag": {
        "name": "Gümüş (XAG)",
        "class": "Emtia",
        "role": "Endüstriyel + değer koruma",
        "volatility": "Orta-Yüksek",
        "drivers": "Sanayi talebi, USD",
        "liquidity": "Yüksek",
        "portfolio_range": "%0–5",
        "default_stop": 0.05,
        "feed": "yfinance",
        "code": "XAGUSD=X",  # fallback: SI=F -> SLV
    },
    "wti": {
        "name": "Petrol (WTI)",
        "class": "Emtia",
        "role": "Enerji emtiası",
        "volatility": "Yüksek",
        "drivers": "Arz/jeopolitik, OPEC, talep",
        "liquidity": "Çok yüksek",
        "portfolio_range": "%0–5",
        "default_stop": 0.10,
        "feed": "yfinance",
        "code": "CL=F",
    },

    # --- Döviz (Yahoo Finance) — TRY bazlı örnekler ---
    "usd": {
        "name": "ABD Doları (USD)",
        "class": "Döviz",
        "role": "Rezerv para",
        "volatility": "Düşük-Orta",
        "drivers": "Faiz farkı, riskten kaçış",
        "liquidity": "Çok yüksek",
        "portfolio_range": "%0–100 (nakit park)",
        "default_stop": 0.02,
        "feed": "yfinance",
        "code": "USDTRY=X",  # TL bazlı
    },
    "eur": {
        "name": "Euro (EUR)",
        "class": "Döviz",
        "role": "Majör para",
        "volatility": "Düşük-Orta",
        "drivers": "ECB politikası, büyüme",
        "liquidity": "Çok yüksek",
        "portfolio_range": "%0–100 (nakit park)",
        "default_stop": 0.02,
        "feed": "yfinance",
        "code": "EURTRY=X",  # TL bazlı
    },
    "try": {
        "name": "Türk Lirası (TRY)",
        "class": "Döviz",
        "role": "Yerel para",
        "volatility": "Orta-Yüksek",
        "drivers": "TCMB politikası, enflasyon",
        "liquidity": "Yüksek",
        "portfolio_range": "—",
        "default_stop": 0.05,
        "feed": "yfinance",
        "code": "TRY=X",  # genelde kullanılmaz; pariteye göre sorgulanır
    },

    # --- Endeks/Hisse (Yahoo Finance) ---
    "spx": {
        "name": "S&P 500",
        "class": "Endeks",
        "role": "Geniş ABD hisse sepeti",
        "volatility": "Orta",
        "drivers": "Kazançlar, faiz, risk iştahı",
        "liquidity": "Çok yüksek (ETF)",
        "portfolio_range": "%30–70",
        "default_stop": 0.06,
        "feed": "yfinance",
        "code": "^GSPC",
    },
    "ndx": {
        "name": "Nasdaq 100",
        "class": "Endeks",
        "role": "Büyüme/teknoloji",
        "volatility": "Orta-Yüksek",
        "drivers": "Teknoloji kazançları, faiz",
        "liquidity": "Çok yüksek (ETF)",
        "portfolio_range": "%20–60",
        "default_stop": 0.07,
        "feed": "yfinance",
        "code": "^NDX",
    },
    "aapl": {
        "name": "Apple (AAPL)",
        "class": "Hisse",
        "role": "Mega-cap teknoloji",
        "volatility": "Orta",
        "drivers": "Satış/kâr, ürün döngüsü",
        "liquidity": "Çok yüksek",
        "portfolio_range": "Sepet içinde küçük/ağırlıkla",
        "default_stop": 0.08,
        "feed": "yfinance",
        "code": "AAPL",
    },
    "tsla": {
        "name": "Tesla (TSLA)",
        "class": "Hisse",
        "role": "Oto/enerji-büyüme",
        "volatility": "Yüksek",
        "drivers": "Satış, marj, rekabet",
        "liquidity": "Çok yüksek",
        "portfolio_range": "Sepet içinde küçük",
        "default_stop": 0.10,
        "feed": "yfinance",
        "code": "TSLA",
    },
}

# Eşanlam/sözcük eşlemesi
ALIASES = {
    # kripto
    "btc": "btc", "bitcoin": "btc",
    "eth": "eth", "ethereum": "eth", "ether": "eth",
    "sol": "sol", "solana": "sol",
    # emtia
    "altın": "xau", "gold": "xau", "xau": "xau",
    "gümüş": "xag", "silver": "xag", "xag": "xag",
    "petrol": "wti", "wti": "wti", "brent": "wti",
    # döviz
    "usd": "usd", "dolar": "usd", "$": "usd", "usdt": "usd",
    "eur": "eur", "euro": "eur",
    "try": "try", "tl": "try", "₺": "try",
    # endeks/hisse
    "sp500": "spx", "s&p500": "spx", "s&p 500": "spx", "spx": "spx",
    "nasdaq": "ndx", "ndx": "ndx",
    "apple": "aapl", "aapl": "aapl",
    "tesla": "tsla", "tsla": "tsla",
}


def normalize_token(token: str) -> str:
    return token.lower().strip()


def detect_assets_in_text(text: str):
    q = (text or "").lower()
    found = []
    for alias, key in ALIASES.items():
        if alias in q and key in ASSETS:
            if key not in found:
                found.append(key)
    return found


def get_asset(key: str):
    return ASSETS.get(key)


def default_stop_for(key: str) -> float:
    a = get_asset(key)
    return a.get("default_stop", 0.05) if a else 0.05