# main.py - V2 MULTI TIMEFRAME BOT
import os, time, threading, requests
from flask import Flask
from brain import MARKETS, analyze_all_tf, analyze_market

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
app = Flask(__name__)

@app.route('/')
def home(): return "V2 Bot Running - 5m 15m 1h 4h"

def send(msg):
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception as e: print("Send Error:", e)

sent_signals = set()

def monitor_loop():
    print("V2 Monitor Started...")
    while True:
        try:
            for name, symbol in MARKETS.items():
                signals = analyze_all_tf(name, symbol)
                for s in signals:
                    key = f"{s['symbol']}-{s['tf']}-{s['type']}-{s['price']}"
                    if key in sent_signals: continue
                    sent_signals.add(key)
                    emoji = "🟢" if s['type']=="BUY" else "🔴"
                    msg = (f"{emoji} <b>{s['type']} {s['symbol']} | {s['tf']}</b>\n"
                           f"📊 {s['reason']}\n\n"
                           f"💰 Entry: {s['price']}\n"
                           f"🛑 SL: {s['sl']}\n"
                           f"🎯 TP1: {s['tp1']}\n"
                           f"🎯 TP2: {s['tp2']}\n\n"
                           f"Bias: {s['bias']}")
                    send(msg)
                    print("Sent:", key)
                time.sleep(2)
            # 5m mate 60 sec ma ek vaar check
            time.sleep(60)
        except Exception as e:
            print("Loop Error:", e)
            time.sleep(30)

def telegram_poll():
    offset = None
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
            params={"offset": offset, "timeout": 30}, timeout=40).json()
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                txt = u.get("message", {}).get("text", "").lower()
                if "/status" in txt:
                    lines = []
                    for name, symbol in MARKETS.items():
                        d = analyze_market(name, symbol)
                        if d: lines.append(f"{name}: {d['bias']} @ {d['price']}")
                    send("📊 <b>V2 STATUS (1h Bias)</b>\n\n" + "\n".join(lines))
                elif "/start" in txt:
                    send("👋 V2 Bot ON hai!\n5m ⚡ SCALP\n15m 📈 INTRADAY\n1h 🎯 SWING\n4h 🏔️ BIG SWING\n\n/status - check bias")
        except: time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=monitor_loop, daemon=True).start()
    threading.Thread(target=telegram_poll, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
