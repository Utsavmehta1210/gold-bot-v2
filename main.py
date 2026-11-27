import time
import threading
import yfinance as yf
import requests
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from brain import analyze, get_data, check_bos
import os
from datetime import datetime, time as dtime
import pytz
from http.server import BaseHTTPRequestHandler, HTTPServer

BOT_TOKEN = os.getenv("BOT_TOKEN", "PASTE_YAHAN_APNA_TOKEN")

# --- RENDER FREE WEB SERVICE KE LIYE PORT FIX ---
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is Running")
    def log_message(self, format, *args):
        return

def keep_alive():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Port Server Started on {port}")
    server.serve_forever()

threading.Thread(target=keep_alive, daemon=True).start()
# --- PORT FIX KHATAM ---

SYMBOLS = {
    "GOLD": "GC=F",
    "BTC": "BTC-USD",
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK"
}

active_trades = {name: None for name in SYMBOLS}
daily_trades = {name: [] for name in SYMBOLS}
CHAT_IDS = set()

# UPDATE 1: GOLD wala msg fix ke liye BOT_LOOP
BOT_LOOP = None

# FIX 2: Deploy pe bhi LOOSE hi rahe, taaki baar-baar /mode loose na likhna pade
MODE = "LOOSE"

def is_nifty_market_open():
    try:
        ist = pytz.timezone("Asia/Kolkata")
        now = datetime.now(ist)
        if now.weekday() >= 5:
            return False
        t = now.time()
        return dtime(9, 15) <= t <= dtime(15, 30)
    except:
        return True

def loose_analyze(ticker):
    # FIX 1: LOOSE ka matlab - Bias se match na ho to bhi Signal do, ruko mat
    df_1h = get_data(ticker, interval="1h", period="15d")
    df_5m = get_data(ticker, interval="5m", period="2d")
    if df_1h is None or df_5m is None:
        return None
    bias = "BULLISH" if float(df_1h['Close'].iloc[-1]) > float(df_1h['Close'].iloc[-20]) else "BEARISH"
    bos_5m = check_bos(df_5m)
    if bos_5m is None:
        bos_5m = bias
    # Agar 5m alag hai to 5m ko hi Bias maan lo - Signal rukega nahi
    if bos_5m != bias:
        bias = bos_5m
    entry = float(df_5m['Close'].iloc[-1])
    if bias == "BULLISH":
        sl = float(df_5m['Low'].iloc[-5:].min())
        risk = entry - sl
        if risk <= 0:
            return None
        target = entry + (risk * 3)
        side = "LONG"
    else:
        sl = float(df_5m['High'].iloc[-5:].max())
        risk = sl - entry
        if risk <= 0:
            return None
        target = entry - (risk * 3)
        side = "SHORT"
    sl_pct = abs(entry - sl) / entry * 100
    tp_pct = abs(target - entry) / entry * 100
    if sl_pct > 1.5:
        return None
    print(f"LOOSE SIGNAL {ticker} {side} @ {entry}")
    return {"side": side, "bias": bias, "entry": entry, "sl": sl, "target": target, "sl_pct": sl_pct, "tp_pct": tp_pct}

def format_signal(name, sig):
    mode_txt = "LOOSE" if MODE == "LOOSE" else "STRICT"
    return (
        f"🔥 STRONG {sig['side']} - {name} - ALL FILTER PASS 🔥\n"
        f"Mode: {mode_txt}\n\n"
        f"Bias (1H): {sig['bias']}\n"
        f"15m Sweep: ✅\n"
        f"15m OB: ✅\n"
        f"15m FVG: ✅\n"
        f"5m BOS: ✅\n\n"
        f"Entry: {sig['entry']:.2f}\n"
        f"SL: {sig['sl']:.2f} (-{sig['sl_pct']:.2f}%)\n"
        f"Target: {sig['target']:.2f} (+{sig['tp_pct']:.2f}%) (1:3)"
    )

def make_report():
    txt = "📊 DAILY REPORT 📊\n\n"
    total_wins = 0
    total_losses = 0
    total_pnl = 0.0
    for name in SYMBOLS:
        trades = daily_trades[name]
        wins = sum(1 for x in trades if x > 0)
        losses = sum(1 for x in trades if x <= 0)
        pnl = sum(trades) if trades else 0.0
        win_pct = (wins / len(trades) * 100) if trades else 0.0
        total_wins += wins
        total_losses += losses
        total_pnl += pnl
        txt += f"{name}:\nWin: {wins} | Loss: {losses}\nWin %: {win_pct:.1f}%\nPnL: {pnl:+.2f}%\n\n"
    total_trades = total_wins + total_losses
    total_win_pct = (total_wins / total_trades * 100) if total_trades > 0 else 0.0
    txt += f"TOTAL:\nWin: {total_wins} | Loss: {total_losses}\nWin %: {total_win_pct:.1f}%\nPnL: {total_pnl:+.2f}%"
    return txt

# UPDATE 2: Scanner se msg bhejne ka safe tarika - GOLD wala fix
def send_to_all(app, msg):
    if not CHAT_IDS:
        print(f"SEND SKIP - CHAT_IDS khali hai, msg: {msg[:50]}")
        return
    if BOT_LOOP is None:
        print(f"SEND FAIL - BOT_LOOP None hai")
        return
    for cid in list(CHAT_IDS):
        try:
            asyncio.run_coroutine_threadsafe(app.bot.send_message(chat_id=cid, text=msg), BOT_LOOP)
            print(f"SENT to {cid}: {msg[:50]}")
        except Exception as e:
            print(f"SEND FAIL {cid}: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    CHAT_IDS.add(update.effective_chat.id)
    await update.message.reply_text("Bot ON hai bhai ✅\nSignal aayenge - Entry + SL + Target ke saath\n/report likh ke report dekh sakta hai\n/price likh ke live price dekh sakta hai\n/why - signal kyu nahi aaya\n/mode - LOOSE / STRICT badalne ke liye\n/reset - report saaf karne ke liye\n/scan - abhi turant scan karne ke liye")

async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    CHAT_IDS.add(update.effective_chat.id)
    await update.message.reply_text(make_report())

async def price_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    CHAT_IDS.add(update.effective_chat.id)
    txt = "💰 LIVE PRICE 💰\n\n"
    for name, ticker in SYMBOLS.items():
        p = get_live_price(ticker)
        if p:
            txt += f"{name}: {p:.2f}\n"
        else:
            txt += f"{name}: Price nahi mila (Market band?)\n"
    await update.message.reply_text(txt)

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    CHAT_IDS.add(update.effective_chat.id)
    active = [k for k,v in active_trades.items() if v is not None]
    txt = f"Bot ON hai ✅\nMode: {MODE}\nScanner chal raha hai...\nActive Trades: {active if active else 'Koi nahi, Setup ka wait ho raha hai'}\nChat IDs: {len(CHAT_IDS)} | BOT_LOOP: {'OK' if BOT_LOOP is not None else 'FAIL ❌'}"
    await update.message.reply_text(txt)

async def testtrade_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    CHAT_IDS.add(update.effective_chat.id)
    await update.message.reply_text("🔥 TEST TRADE 🔥\nGOLD BUY @ 3555\nSL: 3540 | TP: 3580\n\nAgar ye aaya matlab Trade bhejne wala system OK hai ✅\n⚠️ Ye DEMO hai, Report me count nahi hoga.")

async def why_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    CHAT_IDS.add(update.effective_chat.id)
    txt = f"🔍 WHY NO SIGNAL? | Mode: {MODE}\n\n"
    for name, ticker in SYMBOLS.items():
        df_1h = get_data(ticker, interval="1h", period="15d")
        df_15m = get_data(ticker, interval="15m", period="5d")
        df_5m = get_data(ticker, interval="5m", period="2d")
        if df_1h is None or df_15m is None or df_5m is None:
            txt += f"{name}: DATA FAIL ❌\n\n"
            continue
        bias = "BULLISH" if float(df_1h['Close'].iloc[-1]) > float(df_1h['Close'].iloc[-20]) else "BEARISH"
        b15 = check_bos(df_15m)
        b5 = check_bos(df_5m)
        txt += f"{name}: Bias={bias} | 15m={b15} | 5m={b5}\n"
        if MODE == "LOOSE":
            txt += f"  -> LOOSE me Signal banna chahiye ✅ (5m ko follow karega)\n\n"
        else:
            if b15 != bias:
                txt += f"  -> Ruka: 15m BOS Bias se match nahi\n\n"
            elif b5 != bias:
                txt += f"  -> Ruka: 5m BOS Bias se match nahi\n\n"
            else:
                txt += f"  -> SIGNAL BANNA CHAHIYE ✅\n\n"
    await update.message.reply_text(txt)

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    CHAT_IDS.add(update.effective_chat.id)
    for name in SYMBOLS:
        daily_trades[name] = []
        active_trades[name] = None
    await update.message.reply_text("✅ Report saaf ho gaya. Ab se sirf Real Trades gine jayenge.")

async def mode_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MODE
    CHAT_IDS.add(update.effective_chat.id)
    args = context.args
    if args and args[0].lower() in ["loose", "strict"]:
        MODE = args[0].upper()
        await update.message.reply_text(f"✅ Mode badal gaya: {MODE}\nLOOSE = jaldi signal, sirf 5m BOS\nSTRICT = pakka signal, 15m + 5m dono")
    else:
        await update.message.reply_text(f"Current Mode: {MODE}\n\nBadalne ke liye likh:\n/mode loose - jaldi signal ke liye\n/mode strict - pakka signal ke liye")

# UPDATE 3: /scan add kiya - pehle tha hi nahi isliye reply nahi aata tha
async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    CHAT_IDS.add(update.effective_chat.id)
    await update.message.reply_text("🔍 Scan shuru... GOLD / BTC dekh raha hu, 15 sec ruk ja")
    for name in ["GOLD", "BTC"]:
        ticker = SYMBOLS[name]
        try:
            if MODE == "LOOSE":
                sig = loose_analyze(ticker)
            else:
                sig = analyze(ticker)
            if sig:
                await update.message.reply_text(format_signal(name, sig))
            else:
                await update.message.reply_text(f"{name}: Abhi Setup nahi bana ❌")
        except Exception as e:
            await update.message.reply_text(f"{name}: Error - {e}")
    await update.message.reply_text("✅ Scan khatam")

def get_live_price(ticker):
    try:
        df = yf.download(ticker, interval="1m", period="1d", progress=False, auto_adjust=True)
        if df is not None and len(df) > 0:
            if hasattr(df.columns, "get_level_values"):
                try:
                    import pandas as pd
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                except:
                    pass
            price = float(df['Close'].iloc[-1])
            print(f"Price {ticker} from yfinance: {price}")
            return price
    except Exception as e:
        print(f"yfinance fail {ticker}: {e}")
    try:
        sym = ticker.replace("^", "%5E").replace("=", "%3D")
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1m&range=1d"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        result = r.json()['chart']['result'][0]
        price = float(result['meta']['regularMarketPrice'])
        print(f"Price {ticker} from Yahoo API: {price}")
        return price
    except Exception as e:
        print(f"Yahoo API fail {ticker}: {e}")
    try:
        t = yf.Ticker(ticker)
        price = float(t.fast_info['lastPrice'])
        print(f"Price {ticker} from fast_info: {price}")
        return price
    except Exception as e:
        print(f"fast_info fail {ticker}: {e}")
        return None

def scanner_loop(app):
    while True:
        try:
            print(f"Scanner tick... CHAT_IDS={CHAT_IDS} MODE={MODE} BOT_LOOP={'OK' if BOT_LOOP else 'None'}")
            for name, ticker in SYMBOLS.items():
                if active_trades[name] is not None:
                    trade = active_trades[name]
                    price = get_live_price(ticker)
                    if price is None:
                        continue
                    hit = None
                    pnl = 0.0
                    if trade['side'] == "LONG":
                        if price <= trade['sl']:
                            hit = "SL"
                            pnl = -trade['sl_pct']
                        elif price >= trade['target']:
                            hit = "TP"
                            pnl = trade['tp_pct']
                    else:
                        if price >= trade['sl']:
                            hit = "SL"
                            pnl = -trade['sl_pct']
                        elif price <= trade['target']:
                            hit = "TP"
                            pnl = trade['tp_pct']
                    if hit:
                        daily_trades[name].append(pnl)
                        active_trades[name] = None
                        emoji = "✅" if hit == "TP" else "❌"
                        msg = f"{emoji} {hit} HIT - {trade['side']} - {name} {emoji}\nPnL: {pnl:+.2f}%"
                        send_to_all(app, msg)
                    continue
                if name in ["NIFTY", "BANKNIFTY"] and not is_nifty_market_open():
                    continue
                if MODE == "LOOSE":
                    sig = loose_analyze(ticker)
                else:
                    sig = analyze(ticker)
                if sig:
                    active_trades[name] = sig
                    msg = format_signal(name, sig)
                    print(f"SENDING SIGNAL {name} to {CHAT_IDS}")
                    send_to_all(app, msg)
            time.sleep(60)
        except Exception as e:
            print(f"Scanner Error: {e}")
            time.sleep(60)

async def post_init(app):
    global BOT_LOOP
    BOT_LOOP = asyncio.get_running_loop()
    print(f"BOT_LOOP SET: {BOT_LOOP}")
    t = threading.Thread(target=scanner_loop, args=(app,), daemon=True)
    t.start()

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report_cmd))
    app.add_handler(CommandHandler("price", price_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("testtrade", testtrade_cmd))
    app.add_handler(CommandHandler("why", why_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CommandHandler("mode", mode_cmd))
    app.add_handler(CommandHandler("scan", scan_cmd))
    print("Bot Started...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
