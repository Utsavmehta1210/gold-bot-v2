import pandas as pd
import requests

# GOLD = PAXG (Binance pe Gold ka coin), BTC, ETH - sab Binance se
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
        url = f"https://api.binance.com/api/v3/klines?symbol={bin_sym}&interval={interval}&limit=200"
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            print(f"Binance Fail {symbol}: {r.status_code}")
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

def get_df(symbol, period, interval):
    # period ignore karte hai, Binance se direct interval lete hai
    interval_map = {"5m": "5m", "15m": "15m", "1h": "1h", "60m": "1h"}
    bi = interval_map.get(interval, interval)
    return fetch_binance(symbol, bi)

def analyze_one_tf(symbol, tf):
    interval_map = {"5m": "5m", "15m": "15m", "1h": "1h"}
    df = get_df(symbol, "", interval_map.get(tf, "15m"))
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
    df_1h = get_df(symbol, "", "1h")
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
