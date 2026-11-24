import time
import threading
import yfinance as yf
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from brain import analyze
import os
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

def format_signal(name, sig):
    return (
        f"🔥 STRONG {sig['side']} - {name} - ALL FILTER PASS 🔥\n\n"
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    CHAT_IDS.add(update.effective_chat.id)
    await update.message.reply_text("Bot ON hai bhai ✅\nSignal aayenge - Entry + SL + Target ke saath\n/report likh ke report dekh sakta hai\n/price likh ke live price dekh sakta hai")

async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    CHAT_IDS.add(update.effective_chat.id)
    await update.message.reply_text(make_report())

# --- NAYA: /price, /status, /testtrade ---
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
    txt = f"Bot ON hai ✅\nScanner chal raha hai...\nActive Trades: {active if active else 'Koi nahi, Setup ka wait ho raha hai'}"
    await update.message.reply_text(txt)

async def testtrade_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    CHAT_IDS.add(update.effective_chat.id)
    await update.message.reply_text("🔥 TEST TRADE 🔥\nGOLD BUY @ 3555\nSL: 3540 | TP: 3580\n\nAgar ye aaya matlab Trade bhejne wala system OK hai ✅")

# --- NIFTY / BANKNIFTY KE LIYE 3 OPTION PRICE ---
def get_live_price(ticker):
    # Option 1: yfinance
    try:
        df = yf.download(ticker, interval="1m", period="1d", progress=False, auto_adjust=True)
        if df is not None and len(df) > 0:
            price = float(df['Close'].iloc[-1])
            print(f"Price {ticker} from yfinance: {price}")
            return price
    except Exception as e:
        print(f"yfinance fail {ticker}: {e}")

    # Option 2: Yahoo Chart API Direct
    try:
        # ^ ko %5E me convert karna padta hai URL ke liye
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

    # Option 3: yfinance fast_info (Last Try)
    try:
        t = yf.Ticker(ticker)
        price = float(t.fast_info['lastPrice'])
        print(f"Price {ticker} from fast_info: {price}")
        return price
    except Exception as e:
        print(f"fast_info fail {ticker}: {e}")
        return None

def scanner_loop(app):
    import asyncio
    while True:
        try:
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
                        for cid in list(CHAT_IDS):
                            asyncio.run_coroutine_threadsafe(app.bot.send_message(chat_id=cid, text=msg), app.loop)
                    continue

                sig = analyze(ticker)
                if sig:
                    active_trades[name] = sig
                    msg = format_signal(name, sig)
                    for cid in list(CHAT_IDS):
                        asyncio.run_coroutine_threadsafe(app.bot.send_message(chat_id=cid, text=msg), app.loop)
            time.sleep(60)
        except Exception as e:
            print(f"Scanner Error: {e}")
            time.sleep(60)

async def post_init(app):
    t = threading.Thread(target=scanner_loop, args=(app,), daemon=True)
    t.start()

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report_cmd))
    app.add_handler(CommandHandler("price", price_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("testtrade", testtrade_cmd))
    print("Bot Started...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
