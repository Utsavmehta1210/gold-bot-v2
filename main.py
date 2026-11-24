import time
import threading
import yfinance as yf
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from brain import analyze
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

BOT_TOKEN = os.getenv("BOT_TOKEN", "PASTE_YAHAN_APNA_TOKEN")

# --- RENDER FREE WEB SERVICE KE LIYE PORT FIX ---
# Ye chhota server Render ko dikhayega ki Port khula hai, taaki Deploy Fail na ho
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
    await update.message.reply_text("Bot ON hai bhai ✅\nSignal aayenge - Entry + SL + Target ke saath\n/report likh ke report dekh sakta hai")

async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    CHAT_IDS.add(update.effective_chat.id)
    await update.message.reply_text(make_report())

def get_live_price(ticker):
    try:
        df = yf.download(ticker, interval="1m", period="1d", progress=False, auto_adjust=True)
        if df is None or len(df) == 0:
            return None
        return float(df['Close'].iloc[-1])
    except:
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
    print("Bot Started...")
    # YE LINE FIX HAI - Conflict error dobara nahi aayega
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
