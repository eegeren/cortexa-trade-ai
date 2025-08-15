import os, requests, tomli
from dotenv import load_dotenv
from exchange import DummyExchange

load_dotenv()

def load_conf(path: str):
    with open(path, "rb") as f:
        return tomli.load(f)

def decide_and_execute(api_url: str, features: list, conf_path: str = "src/live/config.example.toml"):
    conf = load_conf(conf_path)
    # 1) sınıflandır
    r = requests.post(f"{api_url}/classify", json={"features": features}, timeout=5)
    r.raise_for_status()
    cls = r.json()
    side = cls["side"]  # -1, 0, 1
    if side == 0:
        return {"action":"none","reason":"flat"}

    # 2) tp/sl al
    r2 = requests.post(f"{api_url}/tp_sl", json={"features": features}, timeout=5)
    r2.raise_for_status()
    tpsl = r2.json()

    # 3) risk yönetimi (demo)
    symbol = conf["symbol"]
    ex = DummyExchange()
    qty = 0.001  # DEMO: sabit miktar
    order_side = "BUY" if side == 1 else "SELL"
    res = ex.market_order(symbol, order_side, qty)
    return {"action":"trade","order":res.__dict__,"tp_pct":tpsl["tp_pct"],"sl_pct":tpsl["sl_pct"]}

if __name__ == "__main__":
    print("Strategy engine demo mod. Gerçek borsa entegrasyonu ekleyiniz.")
