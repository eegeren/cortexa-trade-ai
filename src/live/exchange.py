# Gerçek borsa entegrasyonu için python-binance/okx SDK kullanılabilir.
# Bu iskelet, test amaçlı sahte emir akışı sağlar.
from dataclasses import dataclass

@dataclass
class OrderResult:
    status: str
    side: str
    price: float
    qty: float
    message: str = ""

class DummyExchange:
    def __init__(self, fee=0.0006):
        self.fee = fee

    def market_order(self, symbol: str, side: str, qty: float) -> OrderResult:
        # DEMO: Emir anında yürütüldü kabul edilir.
        return OrderResult(status="filled", side=side, price=0.0, qty=qty, message="demo")

# Gerçekte:
# - API anahtarlarını .env'den oku
# - Hata/yeniden bağlanma mekanizması ekle
# - Oran sınırlaması uygula
