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
SYMBOLS = ["GOLD", "BTC", "ETH", "NIFTY", "BANKNIFTY"]

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
    ticker_map = {"GOLD": "GC=F","BTC": "BTC-USD","ETH": "ETH-USD","NIFTY": "^NSEI","BANKNIFTY": "^NSEBANK"}
    ticker = ticker_map.get(symbol)
    if not ticker:
        return None
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        for base in ["query1", "query2"]:
            try:
                url = f"https://{base}.finance.yahoo.com/v8/finance/chart/{ticker}?range=1d&interval=5m"
                r = requests.get(url, headers=headers, timeout=15)
                if r.status_code != 200:
                    continue
                j = r.json()
                res = j.get("chart", {}).get("result", [])
                if not res:
                    continue
                closes = res[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
                closes = [c for c in closes if c is not None]
                if closes:
                    return round(float(closes[-1]), 3)
            except:
                continue
        return None
    except:
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
            f"🏆 Win %: {win_pct}%\n"
            f"💰 Total PnL: {total_pnl:.3f}\n\n"
            f"<b>--- DETAIL ---</b>\n" + "\n".join(lines))

def check_results():
    trades = load_trades()
    changed = False
    for t in trades:
        if t.get("status") != "OPEN":
            continue
        price = get_live_price(t["symbol"])
        if price is None:
            continue
        if t["type"] == "BUY":
            if price <= t["sl"]:
                pnl = round(t["sl"] - t["entry"], 3)
                t["status"] = "LOSS"
                t["pnl"] = pnl
                changed = True
                send(f"❌ <b>{t['symbol']} LOSS - SL HIT</b>\nEntry {t['entry']:.3f} -> SL {t['sl']:.3f}\n💸 Loss: {pnl:.3f}\nLive: {price:.3f}")
            elif price >= t["tp1"]:
                pnl = round(t["tp1"] - t["entry"], 3)
               
