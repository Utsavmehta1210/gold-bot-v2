# main.py - V3 FINAL + PER-SYMBOL LOCK + LIVE PRICE + FORCE CLOSE
import os, time, threading, requests, json, datetime
from flask import Flask
from brain import MARKETS, analyze_all_tf, analyze_market, get_live_price

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
app = Flask(__name__)

@app.route('/')
def home(): return "V3 Bot Running - 5m 15m 1h 4h"

def send(msg):
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception as e: print("Send Error:", e)

sent_signals = set()
open_trades_memory = {}

def load_trades():
    try:
        with open("trades.json","r") as f: return json.load(f)
    except: return []

def save_trades(trades):
    try:
        with open("trades.json","w") as f: json.dump(trades,f)
    except Exception as e: print("Save Error:", e)

def is_symbol_busy(symbol):
    if symbol in open_trades_memory: return True
    trades = load_trades()
    for t in trades:
        if t.get("status") == "OPEN" and t.get("symbol") == symbol:
            return True
    return False

TIMEOUT_HOURS = {"5m": 3, "15m": 6, "1h": 24, "4h": 48}

def check_results():
    trades = load_trades()
    changed = False
    for t in trades:
        if t.get("status") != "OPEN": continue
        try:
            # FIX: Ticker se price lo, Name se nahi
            ticker = t.get("ticker") or MARKETS.get(t.get("symbol_name")) or MARKETS.get(t.get("symbol"))
            if not ticker:
                print(f"Ticker nahi mila {t['symbol']}")
                continue
            price = get_live_price(t.get("symbol_name"), ticker)
            if not price:
                print(f"Price nahi mila {t['symbol']} {ticker}")
                continue

            print(f"Checking {t['symbol']} {t['type']} Entry {t['entry']} SL {t['sl']} TP {t['tp1']} Live {price}")

            closed = False
            if t["type"]=="BUY":
                if price >= t["tp1"]:
                    t["status"]="WIN"; t["pnl"]=t["tp1"]-t["entry"]; closed=True
                    send(f"✅ <b>{t['symbol']} WIN</b>\nEntry {t['entry']} -> TP {t['tp1']}")
                elif price <= t["sl"]:
                    t["status"]="LOSS"; t["pnl"]=t["sl"]-t["entry"]; closed=True
                    send(f"❌ <b>{t['symbol']} LOSS - SL HIT</b>\nEntry {t['entry']} -> SL {t['sl']} Live {price}")
            else:
                if price <= t["tp1"]:
                    t["status"]="WIN"; t["pnl"]=t["entry"]-t["tp1"]; closed=True
                    send(f"✅ <b>{t['symbol']} WIN</b>\nEntry {t['entry']} -> TP {t['tp1']}")
                elif price >= t["sl"]:
                    t["status"]="LOSS"; t["pnl"]=t["entry"]-t["sl"]; closed=True
                    send(f"❌ <b>{t['symbol']} LOSS - SL HIT</b>\nEntry {t['entry']} -> SL {t['sl']} Live {price}")

            # TIMEOUT check
            if not closed and t.get("time"):
                try:
                    open_time = datetime.datetime.fromisoformat(t["time"])
                    hours = (datetime.datetime.now() - open_time).total_seconds()/3600
                    max_h = TIMEOUT_HOURS.get(t.get("tf","15m"), 6)
                    if hours >= max_h:
                        t["status"]="TIMEOUT"
                        if t["type"]=="BUY": t["pnl"]=price-t["entry"]
                        else: t["pnl"]=t["entry"]-price
                        closed=True
                        send(f"⏰ <b>{t['symbol']} TIMEOUT - Auto Close</b>\nPnL: {round(t['pnl'],2)}")
                except: pass

            if closed:
                changed=True
                if t["symbol"] in open_trades_memory:
                    del open_trades_memory[t["symbol"]]
        except Exception as e:
            print("Check Error:", e)
    if changed: save_trades(trades)

def daily_report():
    trades = load_trades()
    today = str(datetime.date.today())
    todays = [t for t in trades if t.get("date")==today and t.get("status")!="OPEN"]
    if not todays: return "📊 Aaje koi trade close nathi thayo."
    wins = [t for t in todays if t["status"]=="WIN"]
    losses = [t for t in todays if t["status"]=="LOSS"]
    total = len(todays)
    win_pct = round(len(wins)/total*100,1) if total else 0
    total_pnl = sum(t.get("pnl",0) for t in todays)
    max_dd = 0; cur_dd = 0
    for t in todays:
        if t["status"]=="LOSS":
            cur_dd += abs(t.get("pnl",0)); max_dd = max(max_dd, cur_dd)
        else: cur_dd = 0
    return (f"📊 <b>DAILY REPORT - {today}</b>\n\n"
            f"Total Trades: {total}\n"
            f"✅ Win: {len(wins)} | ❌ Loss: {len(losses)}\n"
            f"🏆 Win %: {win_pct}%\n"
            f"💰 Total PnL: {round(total_pnl,2)}\n"
            f"📉 Max DD: {round(max_dd,2)}")

def monitor_loop():
    print("V3 Monitor Started...")
    while True:
        try:
            for name, symbol in MARKETS.items():
                if is_symbol_busy(symbol):
                    print(f"Skip {symbol} - pehla trade OPEN che")
                    continue
                signals = analyze_all_tf(name, symbol)
                for s in signals:
                    if is_symbol_busy(s['symbol']):
                        print(f"Skip {s['symbol']} - busy")
                        continue
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
                    open_trades_memory[s['symbol']] = True
                    trades = load_trades()
                    # FIX: ticker bhi save karo
                    trades.append({"date":str(datetime.date.today()), "time":datetime.datetime.now().isoformat(), "symbol":s['symbol'], "symbol_name":name, "ticker":symbol, "type":s['type'], "entry":s['price'], "sl":s['sl'], "tp1":s['tp1'], "status":"OPEN", "pnl":0, "tf":s['tf']})
                    save_trades(trades)
                    break
                time.sleep(2)
            check_results()
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
                    send("📊 <b>V3 STATUS (1h Bias)</b>\n\n" + "\n".join(lines))
                elif "/report" in txt:
                    check_results()
                    send(daily_report())
                elif "/open" in txt:
                    trades = load_trades()
                    opens = [t for t in trades if t.get("status")=="OPEN"]
                    if not opens:
                        send("📭 Koi OPEN trade nahi. Sab FREE hai.")
                    else:
                        lines = [f"{t['symbol']} {t['type']} {t.get('tf','')} @ {t['entry']} | SL {t['sl']} TP {t['tp1']} | {t.get('date')}" for t in opens]
                        send("🔓 <b>OPEN TRADES</b>\n\n" + "\n".join(lines))
                elif "/closeall" in txt:
                    trades = load_trades()
                    cnt = 0
                    for t in trades:
                        if t.get("status")=="OPEN":
                            t["status"]="CLOSED-MANUAL"; t["pnl"]=0; cnt+=1
                            if t["symbol"] in open_trades_memory:
                                del open_trades_memory[t["symbol"]]
                    save_trades(trades)
                    sent_signals.clear()
                    send(f"✅ {cnt} atke hue trade bandh kar diye. Ab naye signal aayenge.")
                elif "/start" in txt:
                    send("👋 V3 Bot ON hai!\n5m ⚡ SCALP\n15m 📈 INTRADAY\n1h 🎯 SWING\n4h 🏔️ BIG SWING\n\n/status - check bias\n/open - open trades juo\n/closeall - atke trade bandh karo\n/report - daily report")
        except: time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=monitor_loop, daemon=True).start()
    threading.Thread(target=telegram_poll, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
