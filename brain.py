import pandas as pd
import requests
import re

BINANCE_MAP = {
    "GOLD": "PAXGUSDT",
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
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

def make_df_from_price(price):
    vals = [price]*60
    df = pd.DataFrame({"Open":vals,"High":vals,"Low":vals,"Close":vals,"Volume":[0]*60})
    return df

def fetch_nifty_price(symbol):
    try:
        s = requests.Session()
        h = {"User-Agent":"Mozilla/5.0","Accept":"application/json","Referer":"https://www.nseindia.com/"}
        s.get("https://www.nseindia.com", headers=h, timeout=10)
        r = s.get("https://www.nseindia.com/api/allIndices", headers=h, timeout=10)
        if r.status_code == 200:
            j = r.json()
            for it in j.get("data", []):
                name = it.get("index","")
                if symbol == "NIFTY" and name == "NIFTY 50":
                    return float(it["last"])
                if symbol == "BANKNIFTY" and name == "NIFTY BANK":
                    return float(it["last"])
    except Exception as e:
        print(f"NSE allIndices fail {symbol}: {e}")
    try:
        y = "%5ENSEI" if symbol == "NIFTY" else "%5ENSEBANK"
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{y}?interval=15m&range=1d"
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
        if r.status_code == 200:
            j = r.json()
            res = j["chart"]["result"][0]
            meta = res.get("meta", {})
            if "regularMarketPrice" in meta:
                return float(meta["regularMarketPrice"])
    except Exception as e:
        print(f"Yahoo2 fail {symbol}: {e}")
    try:
        g = "NIFTY_50:INDEXNSE" if symbol == "NIFTY" else "NIFTY_BANK:INDEXNSE"
        url = f"https://www.google.com/finance/quote/{g}"
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
        if r.status_code == 200:
            m = re.search(r'data-last-price="([\d,\.]+)"', r.text)
            if m:
                return float(m.group(1).replace(",",""))
    except Exception as e:
        print(f"Google fail {symbol}: {e}")
    return None

def fetch_nse(symbol, interval):
    try:
        s = requests.Session()
        h = {"User-Agent":"Mozilla/5.0","Accept":"application/json","Referer":"https://www.nseindia.com/"}
        s.get("https://www.nseindia.com", headers=h, timeout=10)
        idx = "NIFTY 50" if symbol == "NIFTY" else "NIFTY BANK"
        url = f"https://www.nseindia.com/api/chart-databyindex?index={idx}&indices=true"
        r = s.get(url, headers=h, timeout=10)
        if r.status_code == 200:
            j = r.json()
            data = j.get("grapthData", [])
            if data and len(data) >= 50:
                df = pd.DataFrame(data, columns=["Time","Close"])
                df["Open"] = df["Close"]
                df["High"] = df["Close"]
                df["Low"] = df["Close"]
                df["Volume"] = 0
                return df
    except Exception as e:
        print(f"NSE chart fail {symbol}: {e}")
    p = fetch_nifty_price(symbol)
    if p:
        print(f"{symbol} price-only fallback: {p}")
        return make_df_from_price(p)
    return None

def get_df(symbol, period, interval):
    if symbol in BINANCE_MAP:
        return fetch_binance(symbol, interval)
    if symbol in ["NIFTY", "BANKNIFTY"]:
        return fetch_nse(symbol, interval)
    return None

def check_ob(df, direction):
    try:
        closes = df["Close"].values
        opens = df["Open"].values
        lows = df["Low"].values
        highs = df["High"].values
        curr = float(closes[-1])
        for i in range(len(df)-20, len(df)-2):
            if direction == "BUY":
                if opens[i] > closes[i]:
                    ob_low = float(lows[i])
                    ob_high = float(highs[i])
                    if curr > ob_low and abs(curr - ob_high)/curr*100 < 1.5:
                        return True, ob_low
            else:
                if opens[i] < closes[i]:
                    ob_low = float(lows[i])
                    ob_high = float(highs[i])
                    if curr < ob_high and abs(curr - ob_low)/curr*100 < 1.5:
                        return True, ob_high
        return False, None
    except:
        return False, None

def analyze_one_tf(symbol, tf, bias_1h):
    df = get_df(symbol, "", tf)
    if df is None or len(df) < 50:
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
    if (sl_low or bos_up) and bias_1h == "BULLISH":
        ob_ok, ob_level = check_ob(df, "BUY")
        if not ob_ok:
            return None
        sl = round(curr - risk, 3)
        return {"type":"BUY","tf":tf,"price":round(curr,3),"sl":sl,"tp1":round(curr+ risk*1.5,3),"tp2":round(curr+ risk*3,3),"reason":"STRONG Sweep + OB + BOS Up"}
    if (sw_high or bos_down) and bias_1h == "BEARISH":
        ob_ok, ob_level = check_ob(df, "SELL")
        if not ob_ok:
            return None
        sl = round(curr + risk, 3)
        return {"type":"SELL","tf":tf,"price":round(curr,3),"sl":sl,"tp1":round(curr- risk*1.5,3),"tp2":round(curr- risk*3,3),"reason":"STRONG Sweep + OB + BOS Down"}
    return None

def analyze_market(symbol):
    df_1h = get_df(symbol, "", "1h")
    if df_1h is None:
        return None
    curr = float(df_1h["Close"].iloc[-1])
    avg50 = float(df_1h["Close"].iloc[-50:].mean())
    bias = "BULLISH" if curr > avg50 else "BEARISH"
    signal = None
    tf_found = None
    for tf in ["15m", "5m", "1h"]:
        s = analyze_one_tf(symbol, tf, bias)
        if s:
            signal = s
            tf_found = tf
            break
    return {"bias":bias,"price":round(curr,3),"signal":signal,"tf":tf_found}
