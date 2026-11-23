# main.py - V2 MULTI TIMEFRAME BOT + DAILY REPORT
import os, time, threading, requests, json, datetime
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

# --- DAILY TRACKING - NAVU ADD KARYU ---
def load_trades():
    try:
        with open("trades.json","r") as f: return json.load(f)
    except: return []

def save_trades(trades):
    try:
        with open("trades.json","w") as f: json.dump(trades,f)
    except Exception as e: print("Save Error:", e)

def check_results():
    trades = load_trades()
    changed = False
    for t in trades:
        if t.get("status") != "OPEN": continue
        try:
            d = analyze_market(t["symbol_name"], t["symbol"])
            if not d: continue
            price = d['price']
            if t["type"]=="BUY":
                if price >= t["tp1"]:
                    t["status"]="WIN"; t["pnl"]=t["tp1"]-t["entry"]; changed=True
                elif price <= t["sl"]:
                    t["status"]="LOSS"; t["pnl"]=t["sl"]-t["entry"]; changed=True
            else: # SELL
                if price <= t["tp1"]:
                    t["status"]="WIN"; t["pnl"]=t["entry"]-t["tp1"]; changed=True
                elif price >= t["sl"]:
                    t["status"]="LOSS"; t["pnl"]=t["entry"]-t["sl"]; changed=True
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
# --- TRACKING PATYU ---

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
                    # Trade save karo hisab mate
                    trades = load_trades()
                    trades.append({"date":str(datetime.date.today()), "symbol":s['symbol'], "symbol_name":name, "type":s['type'], "entry":s['price'], "sl":s['sl'], "tp1":s['tp1'], "status":"OPEN", "pnl":0})
                    save_trades(trades)
                time.sleep(2)
            # OPEN trade nu result check karo
            check_results()
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
                elif "/report" in txt:
                    check_results()
                    send(daily_report())
                elif "/start" in txt:
                    send("👋 V2 Bot ON hai!\n5m ⚡ SCALP\n15m 📈 INTRADAY\n1h 🎯 SWING\n4h 🏔️ BIG SWING\n\n/status - check bias\n/report - daily report")
        except: time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=monitor_loop, daemon=True).start()
    threading.Thread(target=telegram_poll, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
