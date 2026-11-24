import yfinance as yf
import pandas as pd

TICKER_MAP = {
    "GOLD": "GC=F",
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK"
}

def get_df(symbol, period, interval):
    ticker = TICKER_MAP.get(symbol)
    if not ticker:
        return None
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty or len(df) < 50:
            return None
        if hasattr(df.columns, 'nlevels') and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)
        return df
    except:
        return None

def analyze_one_tf(symbol, tf):
    # tf: 5m, 15m, 1h
    period_map = {"5m": "5d", "15m": "10d", "1h": "1mo"}
    interval_map = {"5m": "5m", "15m": "15m", "1h": "1h"}
    df = get_df(symbol, period_map.get(tf, "10d"), interval_map.get(tf, "15m"))
    if df is None:
        return None

    curr = float(df["Close"].iloc[-1])
    high = df["High"]
    low = df["Low"]

    # Last 20 candle ka High/Low
    recent_high = float(high.iloc[-21:-1].max())
    recent_low = float(low.iloc[-21:-1].min())
    prev_high = float(high.iloc[-2])
    prev_low = float(low.iloc[-2])

    # Sweep + BOS Logic
    # BUY: Price ne neeche ka Low sweep kiya (wick neeche gaya) phir upar close hua + BOS upar
    sweep_low = float(low.iloc[-1]) < recent_low and curr > recent_low
    bos_up = curr > recent_high

    # SELL: Price ne upar ka High sweep kiya phir neeche close hua + BOS neeche
    sweep_high = float(high.iloc[-1]) > recent_high and curr < recent_high
    bos_down = curr < recent_low

    # Risk = last 20 candle ka range ka 0.4%
    atr_like = (float(high.iloc[-20:].max()) - float(low.iloc[-20:].min())) * 0.15
    if atr_like <= 0:
        atr_like = curr * 0.002
    risk = round(atr_like, 3)

    if sweep_low or (bos_up and prev_low < recent_low):
        sl = round(curr - risk, 3)
        return {
            "type": "BUY",
            "tf": tf,
            "price": round(curr, 3),
            "sl": sl,
            "tp1": round(curr + risk * 1.5, 3),
            "tp2": round(curr + risk * 2.5, 3),
            "reason": "Sweep Low + BOS Up" if sweep_low else "BOS Up"
        }

    if sweep_high or (bos_down and prev_high > recent_high):
        sl = round(curr + risk, 3)
        return {
            "type": "SELL",
            "tf": tf,
            "price": round(curr, 3),
            "sl": sl,
            "tp1": round(curr - risk * 1.5, 3),
            "tp2": round(curr - risk * 2.5, 3),
            "reason": "Sweep High + BOS Down" if sweep_high else "BOS Down"
        }
    return None

def analyze_market(symbol):
    # 1h Bias
    df_1h = get_df(symbol, "1mo", "1h")
    if df_1h is None:
        return None
    curr = float(df_1h["Close"].iloc[-1])
    # 50 EMA jaisa simple bias - last 50 close ka average
    avg50 = float(df_1h["Close"].iloc[-50:].mean())
    bias = "BULLISH 🟢" if curr > avg50 else "BEARISH 🔴"

    # Pehle 15m, phir 5m, phir 1h me signal dekho
    signal = None
    for tf in ["15m", "5m", "1h"]:
        s = analyze_one_tf(symbol, tf)
        if s:
            # Bias filter - Bias ke against signal mat lo (sirf 1h ke liye strict)
            if tf == "1h":
                if bias.startswith("BULLISH") and s["type"] == "SELL":
                    continue
                if bias.startswith("BEARISH") and s["type"] == "BUY":
                    continue
            signal = s
            break

    return {"bias": bias, "price": round(curr, 3), "signal": signal, "tf": tf if signal else None}
