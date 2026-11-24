import os
import json
import time
import datetime
import threading
import requests
import yfinance as yf
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
    ticker_map = {
        "GOLD": "GC=F",
        "BTC": "BTC-USD",
        "ETH": "ETH-USD",
        "NIFTY": "^NSEI",
        "BANKNIFTY": "^NSEBANK"
    }
    ticker = ticker_map.get(symbol)
    if not ticker:
        return None
    try:
        for _ in range(2):
            try:
                tk = yf.Ticker(ticker)
                df = tk.history(period="1d", interval="5m", auto_adjust=True)
                if df is not None and not df.empty:
                    if hasattr(df.columns, 'nlevels') and df.columns.nlevels > 1:
                        df.columns = df.columns.get_level_values(0)
                    return round(float(df["Close"].iloc[-1]), 3)
            except:
                time.sleep(2)
                continue
        return None
    except Exception as e:
        print(f"Live Price Error {symbol}:", e)
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
                t["status"] = "WIN"
                t["pnl"] = pnl
                changed = True
                send(f"✅ <b>{t['symbol']} WIN - TP1 HIT</b>\nEntry {t['entry']:.3f} -> TP {t['tp1']:.3f}\n💰 Profit: {pnl:.3f}\nLive: {price:.3f}")
        else:
            if price >= t["sl"]:
                pnl = round(t["entry"] - t["sl"], 3)
                t["status"] = "LOSS"
                t["pnl"] = pnl
                changed = True
                send(f"❌ <b>{t['symbol']} LOSS - SL HIT</b>\nEntry {t['entry']:.3f} -> SL {t['sl']:.3f}\n💸 Loss: {pnl:.3f}\nLive: {price:.3f}")
            elif price <= t["tp1"]:
                pnl = round(t["entry"] - t["tp1"], 3)
                t["status"] = "WIN"
                t["pnl"] = pnl
                changed = True
                send(f"✅ <b>{t['symbol']} WIN - TP1 HIT</b>\nEntry {t['entry']:.3f} -> TP {t['tp1']:.3f}\n💰 Profit: {pnl:.3f}\nLive: {price:.3f}")
    if changed:
        save_trades(trades)

def scan_and_signal():
    trades = load_trades()
    for sym in SYMBOLS:
        open_exists = any(t["symbol"] == sym and t.get("status") == "OPEN" for t in trades)
        if open_exists:
            continue
        try:
            result = analyze_market(sym)
        except Exception as e:
            print(f"Analyze Error {sym}:", e)
            continue
        if not result or not result.get("signal"):
            continue
        s = result["signal"]
        new_trade = {
            "symbol": sym,
            "type": s["type"],
            "tf": s["tf"],
            "entry": round(float(s["price"]), 3),
            "sl": round(float(s["sl"]), 3),
            "tp1": round(float(s["tp1"]), 3),
            "tp2": round(float(s["tp2"]), 3),
            "status": "OPEN",
            "pnl": 0.0,
            "date": str(datetime.date.today()),
            "time": datetime.datetime.now().strftime("%H:%M:%S")
        }
        trades.append(new_trade)
        save_trades(trades)
        icon = "🟢" if s["type"] == "BUY" else "🔴"
        send(f"{icon} <b>{s['type']} {sym} | {s['tf']}</b>\n"
             f"📊 Reason: {s.get('reason','Sweep + BOS')}\n"
             f"💰 Entry: {s['price']:.3f}\n"
             f"🛑 SL: {s['sl']:.3f}\n"
             f"🎯 TP1: {s['tp1']:.3f}\n"
             f"🎯 TP2: {s['tp2']:.3f}\n\n"
             f"Bias 1h: {result.get('bias','-')}")

def bot_loop():
    print("V3 Monitor Started...")
    last_scan_min = -1
    last_report_hour = -1
    while True:
        try:
            now = datetime.datetime.now()
            check_results()
            if now.minute % 5 == 0 and now.minute != last_scan_min:
                last_scan_min = now.minute
                scan_and_signal()
            if now.hour == 21 and now.minute == 0 and last_report_hour != now.hour:
                last_report_hour = now.hour
                send(daily_report())
            time.sleep(30)
        except Exception as e:
            print("Loop Error:", e)
            time.sleep(30)

def handle_commands():
    offset = None
    print("Telegram Polling Started...")
    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
            params = {"timeout": 30}
            if offset:
                params["offset"] = offset
            r = requests.get(url, params=params, timeout=35)
            data = r.json()
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                text = msg.get("text", "").strip().lower()
                if not text.startswith("/"):
                    continue
                if text == "/start":
                    send("👋 V3 Bot Live Hai!\nCommands:\n/status - Live Price\n/open - Open Trades\n/closeall - Sab Bandh Karo\n/report - Aaj Ka Report")
                elif text == "/status":
                    lines = []
                    for sym in SYMBOLS:
                        try:
                            res = analyze_market(sym)
                            if res:
                                lines.append(f"{sym}: {res['price']:.3f} | Bias {res['bias']}")
                            else:
                                lines.append(f"{sym}: No Data")
                        except:
                            lines.append(f"{sym}: Error")
                    send("📊 <b>V3 STATUS (1h Bias)</b>\n\n" + "\n".join(lines))
                elif text == "/open":
                    trades = load_trades()
                    opens = [t for t in trades if t.get("status") == "OPEN"]
                    if not opens:
                        send("📂 Koi OPEN trade nahi. Sab FREE hai.")
                    else:
                        txt = "📂 <b>OPEN TRADES</b>\n\n"
                        for t in opens:
                            txt += f"{t['symbol']} {t['type']} {t.get('tf','')} | Entry {t['entry']:.3f} | SL {t['sl']:.3f} | TP {t['tp1']:.3f}\n"
                        send(txt)
                elif text == "/closeall":
                    trades = load_trades()
                    cnt = 0
                    for t in trades:
                        if t.get("status") == "OPEN":
                            t["status"] = "CLOSED"
                            t["pnl"] = 0.0
                            cnt += 1
                    save_trades(trades)
                    send(f"🧹 {cnt} atke hue trade bandh kar diye.")
                elif text == "/report":
                    send(daily_report())
            time.sleep(1)
        except Exception as e:
            print("Polling Error:", e)
            time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=bot_loop, daemon=True).start()
    threading.Thread(target=handle_commands, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
