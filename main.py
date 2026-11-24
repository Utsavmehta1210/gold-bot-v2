import pandas as pd
import requests

BINANCE_MAP = {
    "GOLD": "PAXGUSDT",
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
}
YAHOO_MAP = {
    "NIFTY": "%5ENSEI",
    "BANKNIFTY": "%5ENSEBANK",
}

def fetch_binance(symbol, interval):
    bin_sym = BINANCE_MAP.get(symbol)
    if not bin_sym:
        return None
    try:
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={bin_sym}&interval={interval}&limit=200"
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        if not data:
            return None
        df = pd.DataFrame(data, columns=["OpenTime","Open","High","Low","Close","Volume","CloseTime","QV","Trades","TBV","TQV","Ignore"])
        for c in ["Open","High","Low","Close","Volume"]:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        df = df.dropna()
        if len(df) < 50:
            return None
        return df
    except Exception as e:
        print(f"Binance Error {symbol}: {e}")
        return None

def fetch_yahoo(symbol, interval):
    y_sym = YAHOO_MAP.get(symbol)
    if not y_sym:
        return None
    try:
        iv = {"5m":"5m","15m":"15m","1h":"60m"}.get(interval,"15m")
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{y_sym}?interval={iv}&range=5d"
        h = {"User-Agent":"Mozilla/5.0"}
        r = requests.get(url, headers=h, timeout=15)
        if r.status_code != 200:
            print(f"Yahoo {symbol} {r.status_code}")
            return None
        j = r.json()
        res = j["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        df = pd.DataFrame({"Open":q["open"],"High":q["high"],"Low":q["low"],"Close":q["close"],"Volume":q["volume"]})
        df = df.dropna()
        if len(df) < 50:
            return None
        return df
    except Exception as e:
        print(f"Yahoo Error {symbol}: {e}")
        return None

def get_df(symbol, period, interval):
    if symbol in BINANCE_MAP:
        return fetch_binance(symbol, interval)
    if symbol in YAHOO_MAP:
        return fetch_yahoo(symbol, interval)
    return None

def analyze_one_tf(symbol, tf):
    df = get_df(symbol, "", tf)
    if df is None:
        return None
    curr = float(df["Close"].iloc[-1])
    high = df["High"]
    low = df["Low"]
    rh = float(high.iloc[-21:-1].max())
    rl = float(low.iloc[-21:-1].min())
    ph = float(high.iloc[-2])
    pl = float(low.iloc[-2])
    sl_low = float(low.iloc[-1]) < rl and curr > rl
    bos_up = curr > rh
    sw_high = float(high.iloc[-1]) > rh and curr < rh
    bos_down = curr < rl
    atr = (float(high.iloc[-20:].max()) - float(low.iloc[-20:].min())) * 0.15
    if atr <= 0:
        atr = curr * 0.002
    risk = round(atr, 3)
    if sl_low or (bos_up and pl < rl):
        sl = round(curr - risk, 3)
        rs = "Sweep Low + BOS Up" if sl_low else "BOS Up"
        return {"type":"BUY","tf":tf,"price":round(curr,3),"sl":sl,"tp1":round(curr+ risk*1.5,3),"tp2":round(curr+ risk*2.5,3),"reason":rs}
    if sw_high or (bos_down and ph > rh):
        sl = round(curr + risk, 3)
        rs = "Sweep High + BOS Down" if sw_high else "BOS Down"
        return {"type":"SELL","tf":tf,"price":round(curr,3),"sl":sl,"tp1":round(curr- risk*1.5,3),"tp2":round(curr- risk*2.5,3),"reason":rs}
    return None

def analyze_market(symbol):
    df_1h = get_df(symbol, "", "1h")
    if df_1h is None:
        return None
    curr = float(df_1h["Close"].iloc[-1])
    avg50 = float(df_1h["Close"].iloc[-50:].mean())
    bias = "BULLISH" if curr > avg50 else "BEARISH"
    signal = None
    for tf in ["15m", "5m", "1h"]:
        s = analyze_one_tf(symbol, tf)
        if s:
            if tf == "1h":
                if bias == "BULLISH" and s["type"] == "SELL":
                    continue
                if bias == "BEARISH" and s["type"] == "BUY":
                    continue
            signal = s
            break
    return {"bias":bias,"price":round(curr,3),"signal":signal,"tf":tf if signal else None}
