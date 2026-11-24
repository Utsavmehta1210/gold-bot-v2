import os
import json
import time
import datetime
import threading
import requests
from flask import Flask
from brain import analyze_market

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
PORT = int(os.environ.get("PORT", 10000))

app = Flask(__name__)

@app.route("/")
def home():
    return "V3 Bot Running"

TRADES_FILE = "trades.json"
SYMBOLS = ["GOLD", "BTC", "ETH"]

def load_trades():
    if not os.path.exists(TRADES_FILE):
        return []
    try:
        with open(TRADES_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_trades(trades):
    with open(TRADES_FILE, "w") as f:
        json.dump(trades, f, indent=2)

def send(msg):
    if not BOT_TOKEN or not CHAT_ID:
        print("BOT_TOKEN/CHAT_ID missing")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print("Send Error:", e)

def get_live_price(symbol):
    m = {"GOLD": "PAXGUSDT", "BTC": "BTCUSDT", "ETH": "ETHUSDT"}
    s = m.get(symbol)
    if not s:
        return None
    try:
        r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={s}", timeout=10)
        if r.status_code == 200:
            return round(float(r.json()["price"]), 3)
    except:
        pass
    return None

def daily_report():
    trades = load_trades()
    today = str(datetime.date.today())
    todays = [t for t in trades if t.get("date") == today and t.get("status") != "OPEN"]
    if not todays:
        return "📊 Aaje koi trade close nathi thayo."
    wins = [t for t in todays if t["status"] == "WIN"]
    losses = [t for t in todays if t["status"] == "LOSS"]
    total = len(todays)
    win_pct = round(len(wins)/total*100, 1) if total else 0
    total_pnl = sum(t.get("pnl", 0) for t in todays)
    lines = []
    for t in todays:
        if t["status"] == "WIN":
            icon = "✅"
            exit_price = t["tp1"]
        elif t["status"] == "LOSS":
            icon = "❌"
            exit_price = t["sl"]
        else:
            icon = "⏰"
            exit_price = t.get("entry", 0)
        pnl = t.get("pnl", 0)
        lines.append(f"{icon} {t['symbol']} {t['type']} {t.get('tf','')} | Entry {t['entry']:.3f} -> {exit_price:.3f} | PnL {pnl:.3f}")
    return (f"📊 <b>DAILY REPORT - {today}</b>\n\n"
            f"Total Trades: {total}\n"
            f"✅ Win: {len(wins)} | ❌ Loss: {len(losses)}\n"
            f"🏆 Win %
