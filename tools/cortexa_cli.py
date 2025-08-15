import sys
import requests
from rich.console import Console
from rich.panel import Panel

API = "http://localhost:8081/advice"
console = Console()

def main():
    console.print("[bold cyan]Cortexa CLI[/] – çıkmak için Ctrl+C\n")

    try:
        while True:
            user_query = input("Soru: ").strip()
            goal = input("Hedef (boş geçilebilir): ").strip()
            horizon = input("Vade (boş geçilebilir): ").strip()
            risk = input("Risk (düşük/orta/yüksek, boş geçilebilir): ").strip()
            cap = input("Sermaye (örn 50000, boş geçilebilir): ").strip()
            stop = input("Stop oranı (örn 0.06, boş): ").strip()

            payload = {
                "user_query": user_query,
                "goal": goal,
                "horizon": horizon,
                "risk": risk,
                "capital": float(cap) if cap else None,
                "stop_pct": float(stop) if stop else None,
            }

            try:
                r = requests.post(API, json=payload, timeout=60)
                r.raise_for_status()
                # JSON değilse .json() patlayabilir → emniyetli parse
                try:
                    data = r.json()
                except Exception:
                    data = {"answer": r.text}
                ans = data.get("answer", r.text)
            except Exception as e:
                ans = f"Hata: {e}\nHam yanıt: {getattr(r, 'text', '<yok>')}"

            console.print(Panel.fit(ans, title="Cortexa Yanıt", border_style="green"))
            print("-" * 60 + "\n")

    except KeyboardInterrupt:
        console.print("\n[bold yellow]Çıkış yapıldı.[/] 👋")
        sys.exit(0)

if __name__ == "__main__":
    main()