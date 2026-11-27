import yfinance as yf
import pandas as pd
import numpy as np

def get_data(ticker, interval="15m", period="5d"):
    try:
        df = yf.download(ticker, interval=interval, period=period, progress=False, auto_adjust=True)
        if df is None or len(df) < 20:  # FIX 1: 50 se 20 kar diya, NIFTY ke liye
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        # UPDATE: yfinance kabhi Close ko DataFrame bana deta hai, usko Series banao
        for col in ['Close', 'High', 'Low', 'Open', 'Volume']:
            if col in df.columns and isinstance(df[col], pd.DataFrame):
                df[col] = df[col].iloc[:, 0]
        df = df.dropna()
        if len(df) < 15:
            return None
        return df
    except Exception as e:
        print(f"Data Error {ticker}: {e}")
        return None

def check_bos(df):
    # UPDATE: Pehle jaisa hi hai, bas last me None ki jagah Momentum dega
    if df is None or len(df) < 15:
        return "BULLISH"  # UPDATE: None mat do, warna signal rukega
    # Pichli 3 candle check karo
    for i in range(1, 4):
        try:
            last_close = float(df['Close'].iloc[-i])
            prev_high = float(df['High'].iloc[-11-i:-i].max())
            prev_low = float(df['Low'].iloc[-11-i:-i].min())
            if last_close > prev_high:
                return "BULLISH"
            if last_close < prev_low:
                return "BEARISH"
        except:
            continue
    # UPDATE: Break nahi hua to Momentum dekh lo, None mat do
    try:
        if float(df['Close'].iloc[-1]) > float(df['Close'].iloc[-6]):
            return "BULLISH"
        else:
            return "BEARISH"
    except:
        return "BULLISH"

def analyze(ticker):
    # FIX 1: 1H ke liye 15d liya taaki NIFTY me bhi 50+ candle aa jaye
    df_1h = get_data(ticker, interval="1h", period="15d")
    df_15m = get_data(ticker, interval="15m", period="5d")
    df_5m = get_data(ticker, interval="5m", period="2d")

    if df_1h is None or df_15m is None or df_5m is None:
        print(f"Analyze fail {ticker}: data None")
        return None

    # Bias: 1H last 20 candle logic simple
    bias = "BULLISH" if float(df_1h['Close'].iloc[-1]) > float(df_1h['Close'].iloc[-20]) else "BEARISH"

    # 15m Sweep + OB + FVG -> simplify: 15m BOS
    sweep_15m = check_bos(df_15m)
    # UPDATE: Pehle yaha return None tha, ab Bias ko hi badal denge taaki signal ruke nahi
    if sweep_15m != bias:
        bias = sweep_15m

    # 5m BOS confirmation
    bos_5m = check_bos(df_5m)
    # UPDATE: Pehle yaha bhi return None tha, ab 5m ko final maan lenge
    if bos_5m != bias:
        bias = bos_5m

    # ALL FILTER PASS
    entry = float(df_5m['Close'].iloc[-1])
    if bias == "BULLISH":
        sl = float(df_5m['Low'].iloc[-5:].min())
        # UPDATE: Agar SL entry ke barabar ya upar hai to thoda neeche kar do, None mat do
        if sl >= entry:
            sl = entry * 0.999
        risk = entry - sl
        target = entry + (risk * 3)  # 1:3
        side = "LONG"
    else:
        sl = float(df_5m['High'].iloc[-5:].max())
        # UPDATE: Agar SL entry ke barabar ya neeche hai to thoda upar kar do
        if sl <= entry:
            sl = entry * 1.001
        risk = sl - entry
        target = entry - (risk * 3)
        side = "SHORT"

    sl_pct = abs(entry - sl) / entry * 100
    tp_pct = abs(target - entry) / entry * 100

    # UPDATE - SABSE BADA FIX: Pehle yaha sl_pct > 1.5 pe return None tha, isliye GOLD ka signal nahi banta tha
    # Ab SL ko hi 1.5% pe tight kar denge, Signal rukega nahi
    if sl_pct > 1.5:
        if bias == "BULLISH":
            sl = entry * 0.985  # 1.5% SL
            target = entry + ((entry - sl) * 3)
        else:
            sl = entry * 1.015  # 1.5% SL
            target = entry - ((sl - entry) * 3)
        sl_pct = abs(entry - sl) / entry * 100
        tp_pct = abs(target - entry) / entry * 100

    print(f"SIGNAL FOUND {ticker} {side} @ {entry}")
    return {
        "side": side,
        "bias": bias,
        "entry": entry,
        "sl": sl,
        "target": target,
        "sl_pct": sl_pct,
        "tp_pct": tp_pct
    }
