import os
import pandas as pd
from datetime import datetime, timedelta
import time
import csv
import traceback

from openalgo import api, ta

from retrieve_nifty_symbols import get_nifty_constituents

print("🔁 OpenAlgo Python Bot is running.")

# =========================
# CONFIG
# =========================
API_KEY = os.getenv("OPENALGO_API_KEY")
HOST = os.getenv("HOST_SERVER") or os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

required_cols = ["open", "high", "low", "close", "volume"]
one_year_ago = pd.Timestamp(datetime.now() - timedelta(days=365))


# =========================
# CLIENT
# =========================
client = api(api_key=API_KEY, host=HOST)


def main():
    try:
        print("Starting the main function...")
        symbols = ["DELHIVERY"]
        for symbol in symbols:  
            analyze_stock(symbol)

    except Exception as e:
        print(f"Error in main: {e}\n{traceback.format_exc()}")



def analyze_stock(symbol):
        #check market close
        # Fetch historical data for the symbol
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")  # Last 100 days
        df = client.history(symbol=symbol, exchange="NSE", interval="D", start_date=start, end_date=end)

        # Ensure required columns are present
        if not all(col in df.columns for col in required_cols):
            print(f"Data for {symbol} is missing required columns.")
            return None

        is_rsi_neutral = False
        check_rsi(symbol, df, period=5)
        is_macd_positive_crossover = False
        check_macd(df)
        is_ema_positive_crossover = False
        check_ema(symbol, df)
        is_stochastic_positive_crossover = False
        check_stochastic(symbol, df)
        is_volume_higher = False
        check_volume(symbol, df)
        is_candle_big_green = False
        check_candle(symbol, df)



def check_rsi(symbol, df, period=5):
    df["RSI5"] = ta.rsi(df["close"], period)
    rsi = df["RSI5"].iloc[-1]
    print(f"RSI5 for {symbol}: {rsi:.2f}")
    if rsi > 60:
        print_with_seperator("RSI: Zone: OVERBOUGHT -> momentum stretched up, watch for a pullback")
    elif rsi < 40:
        print_with_seperator("RSI: Zone: OVERSOLD -> momentum stretched down, watch for a bounce")
    else:
        print_with_seperator("RSI: Zone: NEUTRAL (40-60) -> no extreme; 50 is the bull/bear line")


def check_macd(df):
    macd_line, signal_line, hist = ta.macd(df["close"])

    m = macd_line.iloc[-1]
    s = signal_line.iloc[-1]
    h = hist.iloc[-1]

    print(f"MACD line   : {m:8.2f}")
    print(f"Signal line : {s:8.2f}")
    print(f"Histogram   : {h:8.2f}  (MACD minus signal)")
    print_with_seperator("Momentum:" + "BULLISH (MACD above signal)" if m > s else "BEARISH (MACD below signal)")
    print_with_seperator("Push:" + "strengthening" if h > 0 else "weakening / negative")


def check_ema(symbol, df):
    periods = [5,13,26,50]
    emas = {p: ta.ema(df["close"], p).iloc[-1] for p in periods}

    print(f"{symbol} close:", round(df["close"].iloc[-1], 2))
    for p in periods:
        print(f"  EMA{p:<3d} = {emas[p]:8.2f}")

    # A bullish stack means fast EMAs sit above slow EMAs, in order.
    ordered = [emas[p] for p in periods]
    stacked_up = all(ordered[i] > ordered[i + 1] for i in range(len(ordered) - 1))
    stacked_down = all(ordered[i] < ordered[i + 1] for i in range(len(ordered) - 1))
    print_with_seperator(f"{symbol} Ribbon:" + "bullish stack" if stacked_up else "bearish stack" if stacked_down else "tangled / no clear trend")


def check_stochastic(symbol, df):
    k, d = ta.stochastic(df["high"], df["low"], df["close"], k_period=5, d_period=3)

    kv = k.iloc[-1]
    dv = d.iloc[-1]
    print(f"{symbol} close:", round(df["close"].iloc[-1], 2))
    print(f"%K = {kv:6.2f}   %D = {dv:6.2f}")

    if kv > 80:
        print("Zone: OVERBOUGHT (>80) -> close near top of its range")
    elif kv < 20:
        print("Zone: OVERSOLD (<20) -> close near bottom of its range")
    else:
        print("Zone: mid-range (20-80)")
    print_with_seperator("Cross:" + "%K above %D -> bullish tilt" if kv > dv else "%K below %D -> bearish tilt")


def check_volume(symbol, df):
    prev_volume = df["volume"].iloc[-2]
    current_volume = df["volume"].iloc[-1]

    print(f"{symbol} current volume: {current_volume}, previous volume: {prev_volume}")
    if current_volume > prev_volume and current_volume > 100000:
        print_with_seperator("Volume is increasing -> bullish tilt")
    elif current_volume > prev_volume and current_volume <= 100000:
        print_with_seperator("Volume is increasing but below threshold -> cautious bullish tilt")
    else:
        print_with_seperator("Volume is decreasing -> bearish tilt")


def check_candle(symbol, df):
    #+5% green, -5% red

    last_candle = df.iloc[-1]
    open_price = last_candle["open"]#100
    close_price = last_candle["close"]#105
    high_price = last_candle["high"]#107
    low_price = last_candle["low"]#98

    candle_body = abs(close_price - open_price)#5
    candle_range = high_price - low_price#9

    print(f"{symbol} last candle: Open={open_price}, Close={close_price}, High={high_price}, Low={low_price}")
    print(f"Candle body: {candle_body:.2f}, Candle range: {candle_range:.2f}")

    if candle_body > 0.7 * candle_range and close_price > open_price:
        print_with_seperator("Big green candle -> strong bullish sentiment")
    elif candle_body > 0.7 * candle_range and close_price < open_price:
        print_with_seperator("Big red candle -> strong bearish sentiment")
    else:
        print_with_seperator("No strong candle pattern detected")



def print_with_seperator(s):
    print("-------------------------------------------------------------------------------")
    print(s)
    print("-------------------------------------------------------------------------------")


if __name__ == "__main__":
    main()