import pandas as pd
import requests
import time

TICKER_MAP = {
    "GOLD": "GC=F",
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK"
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def fetch_yahoo(ticker, period, interval):
    # Direct Yahoo API - yfinance se alag, Render pe bhi chalta hai
    urls = [
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={period}&interval={interval}",
        f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?range={period}&interval={interval}"
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                continue
            j = r.json()
            res = j.get("chart", {}).get("result", [])
            if not res:
                continue
            data = res[0]
            ts = data.get("timestamp", [])
            q = data.get("indicators", {}).get("quote", [{}])[0]
            if not ts or not q.get("close"):
                continue
            df = pd.DataFrame({
                "Open": q.get("open"),
                "High": q.get("high"),
                "Low": q.get("low"),
                "Close": q.get("close"),
                "Volume": q.get("volume"),
            })
            df = df.dropna()
            if len(df) >= 20:
                return df
        except Exception as e:
            print(f"Yahoo Fetch Fail {ticker}: {e}")
            continue
    return None

def get_df(symbol, period, interval):
    ticker = TICKER_MAP.get(symbol)
    if not ticker:
        return None
    return fetch_yahoo(ticker, period, interval)

def analyze_one_tf(symbol, tf):
    period_map = {"5m": "5d", "15m": "10d", "1h": "1mo"}
    interval_map = {"5m": "5m", "15m": "15m", "1h": "60m"}
    df = get_df(symbol, period_map.get(tf, "10d"), interval_map.get(tf, "15m"))
    if df is None:
        return None
    curr = float(df["Close"].iloc[-1])
    high = df["High"]
    low = df["Low"]
    recent_high = float(high.iloc[-21:-1].max())
    recent_low = float(low.iloc[-21:-1].min())
    prev_high = float(high.iloc[-2])
    prev_low = float(low.iloc[-2])
    sweep_low = float(low.iloc[-1]) < recent_low and curr > recent_low
    bos_up = curr > recent_high
    sweep_high = float(high.iloc[-1]) > recent_high and curr < recent_high
    bos_down = curr < recent_low
    atr_like = (float(high.iloc[-20:].max()) - float(low.iloc[-20:].min())) * 0.15
    if atr_like <= 0:
        atr_like = curr * 0.002
    risk = round(atr_like, 3)
    if sweep_low or (bos_up and prev_low < recent_low):
        sl = round(curr - risk, 3)
        return {"type": "BUY","tf": tf,"price": round(curr, 3),"sl": sl,"tp1": round(curr + risk * 1.5, 3),"tp2": round(curr + risk * 2.5, 3),"reason": "Sweep Low + BOS Up" if sweep_low else "BOS Up"}
    if sweep_high or (bos_down and prev_high > recent_high):
        sl = round(curr + risk, 3)
        return {"type": "SELL","tf": tf,"price": round(curr, 3),"sl": sl,"tp1": round(curr - risk * 1.5, 3),"tp2": round(curr - risk * 2.5, 3),"reason": "Sweep High + BOS Down" if sweep_high else "BOS Down"}
    return None

def analyze_market(symbol):
    df_1h = get_df(symbol, "1mo", "60m")
    if df_1h is None:
        return None
    curr = float(df_1h["Close"].iloc[-1])
    avg50 = float(df_1h["Close"].iloc[-50:].mean())
    bias = "BULLISH 🟢" if curr > avg50 else "BEARISH 🔴"
    signal = None
    for tf in ["15m", "5m", "1h"]:
        s = analyze_one_tf(symbol, tf)
        if s:
            if tf == "1h":
                if bias.startswith("BULLISH") and s["type"] == "SELL":
                    continue
                if bias.startswith("BEARISH") and s["type"] == "BUY":
                    continue
            signal = s
            break
    return {"bias": bias, "price": round(curr, 3), "signal": signal, "tf": tf if signal else None}
