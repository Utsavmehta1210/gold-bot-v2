import os, time, threading, requests
from flask import Flask
import yfinance as yf

TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
PORT = int(os.environ.get("PORT", 10000))
API = f"https://api.telegram.org/bot{TOKEN}"
app = Flask(__name__)

@app.route("/")
def home():
    return "GOLD BOT V3 LIVE", 200

def send(msg):
    try:
        requests.post(f"{API}/sendMessage", json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print("send error:", e)

def get_price():
    try:
        d = yf.download("GC=F", period="1d", interval="1m", progress=False)
        return float(d["Close"].iloc[-1])
    except Exception as e:
        print("price error:", e)
        return 0

def bot_loop():
    print("V3 Monitor Started...", flush=True)
    while True:
        try:
            p = get_price()
            print(f"Price: {p}", flush=True)
            if p:
                send(f"🟡 *GOLD LIVE:* ${p:.2f}")
        except Exception as e:
            print("loop error:", e, flush=True)
        time.sleep(300)

def handle_commands():
    print("Polling Started...", flush=True)
    offset = 0
    while True:
        try:
            r = requests.get(f"{API}/getUpdates", params={"offset": offset, "timeout": 30}, timeout=40).json()
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message", {})
                text = msg.get("text", "")
                if text == "/start":
                    send("Bot Live ✅\n/start - check\n/price - gold price")
                elif text == "/price":
                    send(f"🟡 *GOLD:* ${get_price():.2f}")
        except Exception as e:
            print("poll error:", e, flush=True)
            time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=bot_loop, daemon=True).start()
    threading.Thread(target=handle_commands, daemon=True).start()
    print("Starting Flask...", flush=True)
    app.run(host="0.0.0.0", port=PORT)
