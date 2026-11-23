# brain.py - V2 MULTI TIMEFRAME BRAIN
import yfinance as yf
import pandas as pd

MARKETS = {
    "GOLD": "GC=F",
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
}

TIMEFRAMES = ["5m", "15m", "1h", "4h"]

def get_data(symbol, tf):
    if tf == "4h":
        df = yf.download(symbol, period="5d", interval="1h", progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index = pd.to_datetime(df.index)
        df = df.resample('4h').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
        return df
    else:
        period = "1d" if tf=="5m" else "2d" if tf=="15m" else "5d"
        df = yf.download(symbol, period=period, interval=tf, progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df.dropna()

def analyze_one_tf(name, symbol, tf):
    df = get_data(symbol, tf)
    if df is None or len(df) < 50:
        return None
    close, high, low = df['Close'], df['High'], df['Low']
    curr = float(close.iloc[-1])
    last_high = float(high.iloc[-20:-1].max())
    last_low = float(low.iloc[-20:-1].min())
    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]

    if ema20 > ema50 and curr > ema20: bias="BULLISH"
    elif ema20 < ema50 and curr < ema20: bias="BEARISH"
    else: bias="SIDEWAYS"

    signal=None
    sweep_low = float(low.iloc[-1]) < last_low and curr > last_low
    sweep_high = float(high.iloc[-1]) > last_high and curr < last_high
    bos_up = curr > last_high
    bos_down = curr < last_low

    tf_tag = {"5m":"⚡ SCALP","15m":"📈 INTRADAY","1h":"🎯 SWING","4h":"🏔️ BIG SWING"}[tf]

    if bias=="BULLISH" and (sweep_low or bos_up):
        sl = float(low.iloc[-1]) - (curr*0.0005) if sweep_low else last_low
        risk = curr - sl
        if 0 < risk < curr*0.01:
            signal={"symbol":name,"type":"BUY","price":round(curr,2),"sl":round(sl,2),
            "tp1":round(curr+risk*1.5,2),"tp2":round(curr+risk*2.5,2),
            "reason":f"{tf_tag} | {tf} - Bullish + Sweep/BOS","bias":bias,"tf":tf}
    elif bias=="BEARISH" and (sweep_high or bos_down):
        sl = float(high.iloc[-1]) + (curr*0.0005) if sweep_high else last_high
        risk = sl - curr
        if 0 < risk < curr*0.01:
            signal={"symbol":name,"type":"SELL","price":round(curr,2),"sl":round(sl,2),
            "tp1":round(curr-risk*1.5,2),"tp2":round(curr-risk*2.5,2),
            "reason":f"{tf_tag} | {tf} - Bearish + Sweep/BOS","bias":bias,"tf":tf}
    return {"bias":bias,"price":round(curr,2),"signal":signal,"tf":tf}

def analyze_market(name, symbol):
    return analyze_one_tf(name, symbol, "1h")

def analyze_all_tf(name, symbol):
    results=[]
    for tf in TIMEFRAMES:
        r = analyze_one_tf(name, symbol, tf)
        if r and r['signal']:
            results.append(r['signal'])
    return results
