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
MAP = {"GOLD": "PAXGUSDT", "BTC": "BTCUSDT", "ETH": "ETHUSDT"}

def load_trades():
    if not os.path.exists(TRADES_FILE):
        return []
    try:
        with open(TRADES_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_trades(t):
    with open(TRADES_FILE, "w") as f:
        json.dump(t, f, indent=2)

def send(msg):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print("Send Error:", e)

def get_live_price(symbol):
    s = MAP.get(symbol)
    if not s:
        return None
    try:
        u = f"https://api.binance.com/api/v3/ticker/price?symbol={s}"
        r = requests.get(u, timeout=10)
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
        return "Aaje koi trade close nathi thayo."
    wins = [t for t in todays if t["status"] == "WIN"]
    losses = [t for t in todays if t["status"] == "LOSS"]
    total = len(todays)
    wp = round(len(wins)/total*100, 1) if total else 0
    pnl = sum(t.get("pnl", 0) for t in todays)
    txt = f"DAILY REPORT {today}\n"
    txt += f"Total: {total} Win: {len(wins)} Loss: {len(losses)}\n"
    txt += f"Win%: {wp}% PnL: {pnl:.3f}\n"
    for t in todays:
        txt += f"{t['symbol']} {t['type']} PnL {t.get('pnl',0):.3f}\n"
    return txt

def check_results():
    trades = load_trades()
    changed = False
    for t in trades:
        if t.get("status") != "OPEN":
            continue
        price = get_live_price(t["symbol"])
        if price is None:
            continue
        e = t["entry"]
        sl = t["sl"]
        tp = t["tp1"]
        sym = t["symbol"]
        if t["type"] == "BUY":
            if price <= sl:
                t["status"] = "LOSS"
                t["pnl"] = round(sl - e, 3)
                changed = True
                m = f"{sym} LOSS SL HIT\n"
                m += f"Entry {e} SL {sl} Live {price}"
                send(m)
            elif price >= tp:
                t["status"] = "WIN"
                t["pnl"] = round(tp - e, 3)
                changed = True
                m = f"{sym} WIN TP HIT\n"
                m += f"Entry {e} TP {tp} Live {price}"
                send(m)
        else:
            if price >= sl:
                t["status"] = "LOSS"
                t["pnl"] = round(e - sl, 3)
                changed = True
                m = f"{sym} LOSS SL HIT\n"
                m += f"Entry {e} SL {sl} Live {price}"
                send(m)
            elif price <= tp:
                t["status"] = "WIN"
                t["pnl"] = round(e - tp, 3)
                changed = True
                m = f"{sym} WIN TP HIT\n"
                m += f"Entry {e} TP {tp} Live {price}"
                send(m)
    if changed:
        save_trades(trades)

def scan_and_signal():
    trades = load_trades()
    for sym in SYMBOLS:
        has = any(t["symbol"] == sym and t.get("status") == "OPEN" for t in trades)
        if has:
            continue
        try:
            res = analyze_market(sym)
        except Exception as e:
            print("Err", sym, e)
            continue
        if not res or not res.get("signal"):
            continue
        s = res["signal"]
        nt = {}
        nt["symbol"] = sym
        nt["type"] = s["type"]
        nt["tf"] = s["tf"]
        nt["entry"] = round(float(s["price"]), 3)
        nt["sl"] = round(float(s["sl"]), 3)
        nt["tp1"] = round(float(s["tp1"]), 3)
        nt["tp2"] = round(float(s["tp2"]), 3)
        nt["status"] = "OPEN"
        nt["pnl"] = 0.0
        nt["date"] = str(datetime.date.today())
        nt["time"] = datetime.datetime.now().strftime("%H:%M:%S")
        trades.append(nt)
        save_trades(trades)
        m = f"{s['type']} {sym} {s['tf']}\n"
        m += f"Entry {s['price']:.3f}\n"
        m += f"SL {s['sl']:.3f}\n"
        m += f"TP1 {s['tp1']:.3f}\n"
        m += f"TP2 {s['tp2']:.3f}\n"
        m += f"Bias {res.get('bias','-')}"
        send(m)

def bot_loop():
    print("V3 Monitor Started...")
    last_scan = -1
    last_rep = -1
    while True:
        try:
            now = datetime.datetime.now()
            check_results()
            if now.minute % 5 == 0 and now.minute != last_scan:
                last_scan = now.minute
                scan_and_signal()
            if now.hour == 21 and now.minute == 0 and last_rep != now.hour:
                last_rep = now.hour
                send(daily_report())
            time.sleep(30)
        except Exception as e:
            print("Loop Error:", e)
            time.sleep(30)

def handle_commands():
    offset = None
    print("Polling Started...")
    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
            p = {"timeout": 30}
            if offset:
                p["offset"] = offset
            r = requests.get(url, params=p, timeout=35)
            data = r.json()
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                text = msg.get("text", "").strip().lower()
                if not text.startswith("/"):
                    continue
                if text == "/start":
                    send("V3 Bot Live\n/status /open /closeall /report")
                elif text == "/status":
                    lines = []
                    for sym in SYMBOLS:
                        try:
                            res = analyze_market(sym)
                            if res:
                                lines.append(f"{sym}: {res['price']} Bias {res['bias']}")
                            else:
                                lines.append(f"{sym}: No Data")
                        except:
                            lines.append(f"{sym}: Error")
                    send("STATUS\n" + "\n".join(lines))
                elif text == "/open":
                    trades = load_trades()
                    opens = [t for t in trades if t.get("status") == "OPEN"]
                    if not opens:
                        send("Koi OPEN trade nahi")
                    else:
                        txt = "OPEN TRADES\n"
                        for t in opens:
                            txt += f"{t['symbol']} {t['type']} E {t['entry']} SL {t['sl']} TP {t['tp1']}\n"
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
                    send(f"{cnt} trade bandh kiye")
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
