import os, json, time, datetime, threading, requests
from flask import Flask
from brain import analyze_market, get_df

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
PORT = int(os.environ.get("PORT", 10000))
app = Flask(__name__)

@app.route("/")
def home():
    return "V3 Bot Running"

TRADES_FILE = "trades.json"
SYMBOLS = ["GOLD", "BTC", "ETH", "NIFTY", "BANKNIFTY"]
MAP = {"GOLD": "PAXGUSDT", "BTC": "BTCUSDT", "ETH": "ETHUSDT"}
last_signal = {}

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
    if symbol in MAP:
        s = MAP[symbol]
        try:
            u = f"https://data-api.binance.vision/api/v3/ticker/price?symbol={s}"
            r = requests.get(u, timeout=10)
            if r.status_code == 200:
                return round(float(r.json()["price"]), 3)
        except:
            pass
        return None
    if symbol in ["NIFTY", "BANKNIFTY"]:
        try:
            df = get_df(symbol, "", "5m")
            if df is not None:
                return round(float(df["Close"].iloc[-1]), 3)
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
    total_pct = 0
    txt = f"DAILY REPORT {today}\n"
    txt += f"Total: {total} Win: {len(wins)} Loss: {len(losses)}\n"
    txt += f"Win%: {wp}%\n"
    for t in todays:
        pct = round((t.get("pnl",0)/t["entry"]*100), 3) if t["entry"] else 0
        total_pct += pct
        txt += f"{t['symbol']} {t['type']} PnL {pct}% ({t.get('pnl',0):.3f} pts)\n"
    txt += f"Total PnL: {total_pct:.3f}%"
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
        e = t["entry"]; sl = t["sl"]; tp = t["tp1"]; sym = t["symbol"]
        hit = None
        if t["type"] == "BUY":
            if price <= sl:
                t["status"] = "LOSS"; t["pnl"] = round(sl - e, 3); hit = "LOSS"
            elif price >= tp:
                t["status"] = "WIN"; t["pnl"] = round(tp - e, 3); hit = "WIN"
        else:
            if price >= sl:
                t["status"] = "LOSS"; t["pnl"] = round(e - sl, 3); hit = "LOSS"
            elif price <= tp:
                t["status"] = "WIN"; t["pnl"] = round(e - tp, 3); hit = "WIN"
        if hit:
            changed = True
            t["close_time"] = datetime.datetime.now().strftime("%H:%M:%S")
            m = f"{sym} {hit} {'SL' if hit=='LOSS' else 'TP'} HIT\nEntry {e} Live {price}"
            send(m)
    if changed:
        save_trades(trades)

def scan_and_signal():
    trades = load_trades()
    for sym in SYMBOLS:
        has = any(t["symbol"] == sym and t.get("status") == "OPEN" for t in trades)
        if has:
            continue
        now_dt = datetime.datetime.now()
        for t in reversed(trades):
            if t["symbol"] == sym and t.get("status") in ["WIN","LOSS"] and t.get("date") == str(datetime.date.today()) and t.get("close_time"):
                try:
                    ct = datetime.datetime.strptime(t["close_time"], "%H:%M:%S").replace(year=now_dt.year, month=now_dt.month, day=now_dt.day)
                    if (now_dt - ct).total_seconds() < 1800:
                        has = True
                        break
                except:
                    pass
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
        if sym in last_signal:
            lp, lt = last_signal[sym]
            if (now_dt - lt).total_seconds() < 3600 and abs(s["price"]-lp)/lp*100 < 0.1:
                continue
        last_signal[sym] = (float(s["price"]), now_dt)
        nt = {}
        nt["symbol"] = sym; nt["type"] = s["type"]; nt["tf"] = s["tf"]
        nt["entry"] = round(float(s["price"]), 3); nt["sl"] = round(float(s["sl"]), 3)
        nt["tp1"] = round(float(s["tp1"]), 3); nt["tp2"] = round(float(s["tp2"]), 3)
        nt["status"] = "OPEN"; nt["pnl"] = 0.0; nt["date"] = str(datetime.date.today())
        nt["time"] = now_dt.strftime("%H:%M:%S")
        trades.append(nt); save_trades(trades)
        m = f"{s['type']} {sym} {s['tf']}\nEntry {s['price']:.3f}\nSL {s['sl']:.3f}\nTP1 {s['tp1']:.3f}\nTP2 {s['tp2']:.3f}\nBias {res.get('bias','-')}"
        send(m)

def bot_loop():
    print("V3 Monitor Started...")
    last_scan = -1; last_rep = -1
    while True:
        try:
            now = datetime.datetime.now()
            check_results()
            if now.minute % 5 == 0 and now.minute != last_scan:
                last_scan = now.minute; scan_and_signal()
            if now.hour == 21 and now.minute == 0 and last_rep != now.hour:
                last_rep = now.hour; send(daily_report())
            time.sleep(30)
        except Exception as e:
            print("Loop Error:", e); time.sleep(30)

def handle_commands():
    offset = None
