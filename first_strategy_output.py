import os
import pandas as pd
from datetime import datetime, timedelta
import traceback

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

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

OUTPUT_FILE = "strategy_output.xlsx"

# Column order in the output workbook: Symbol, then one column per factor
COLUMNS = ["Symbol", "RSI5", "MACD", "EMA Ribbon", "Stochastic", "Volume", "Candle"]

# Fill colors for bullish / bearish; neutral gets no fill
BULLISH_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
BEARISH_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
HEADER_FILL = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")

# =========================
# CLIENT
# =========================
client = api(api_key=API_KEY, host=HOST)


def main():
    try:
        print("Starting the main function...")
        symbols = ["HSCL", "WOCKPHARMA", "GOODLUCK", "MSTCLTD", "MINDACORP", "JAYBARMARU"]
        rows = []
        for symbol in symbols:
            row = analyze_stock(symbol)
            if row is not None:
                rows.append(row)

        write_excel(rows)

    except Exception as e:
        print(f"Error in main: {e}\n{traceback.format_exc()}")


def analyze_stock(symbol):
    # Fetch historical data for the symbol
    end = (datetime.now()).strftime("%Y-%m-%d")
    if datetime.now().hour < 15:  # If before 3.30 PM, use yesterday's date
        end = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    elif datetime.now().hour == 15 and datetime.now().minute < 30:  # If before 3.30 PM, use yesterday's date
        end = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    start = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")  # Last 100 days
    df = client.history(symbol=symbol, exchange="NSE", interval="D", start_date=start, end_date=end)

    # Ensure required columns are present
    if not all(col in df.columns for col in required_cols):
        print(f"Data for {symbol} is missing required columns.")
        return None

    row = {"Symbol": {"value": symbol, "sentiment": "neutral"}}
    row["RSI5"] = check_rsi(symbol, df, period=5)
    row["MACD"] = check_macd(df)
    row["EMA Ribbon"] = check_ema(symbol, df)
    row["Stochastic"] = check_stochastic(symbol, df)
    row["Volume"] = check_volume(symbol, df)
    row["Candle"] = check_candle(symbol, df)
    return row


def check_rsi(symbol, df, period=5):
    df["RSI5"] = ta.rsi(df["close"], period)
    rsi = df["RSI5"].iloc[-1]

    if rsi > 60:
        sentiment = "bullish"
        note = "OVERBOUGHT -> momentum stretched up, watch for a pullback"
    elif rsi < 40:
        sentiment = "bearish"
        note = "OVERSOLD -> momentum stretched down, watch for a bounce"
    else:
        sentiment = "neutral"
        note = "NEUTRAL (40-60) -> no extreme; 50 is the bull/bear line"

    value = f"{rsi:.2f} ({note})"
    return {"value": value, "sentiment": sentiment}


def check_macd(df):
    macd_line, signal_line, hist = ta.macd(df["close"])

    m = macd_line.iloc[-1]
    s = signal_line.iloc[-1]
    h = hist.iloc[-1]

    sentiment = "bullish" if m > s else "bearish"
    momentum = "BULLISH (MACD above signal)" if m > s else "BEARISH (MACD below signal)"
    push = "strengthening" if h > 0 else "weakening / negative"

    value = f"MACD={m:.2f}, Signal={s:.2f}, Hist={h:.2f} | {momentum}, {push}"
    return {"value": value, "sentiment": sentiment}


def check_ema(symbol, df):
    periods = [5, 13, 26, 50]
    emas = {p: ta.ema(df["close"], p).iloc[-1] for p in periods}

    # A bullish stack means fast EMAs sit above slow EMAs, in order.
    ordered = [emas[p] for p in periods]
    stacked_up = all(ordered[i] > ordered[i + 1] for i in range(len(ordered) - 1))
    stacked_down = all(ordered[i] < ordered[i + 1] for i in range(len(ordered) - 1))

    if stacked_up:
        sentiment = "bullish"
        note = "bullish stack"
    elif stacked_down:
        sentiment = "bearish"
        note = "bearish stack"
    else:
        sentiment = "neutral"
        note = "tangled / no clear trend"

    ema_str = ", ".join(f"EMA{p}={emas[p]:.2f}" for p in periods)
    value = f"Close={df['close'].iloc[-1]:.2f} | {ema_str} | {note}"
    return {"value": value, "sentiment": sentiment}


def check_stochastic(symbol, df):
    k, d = ta.stochastic(df["high"], df["low"], df["close"], k_period=5, d_period=3)

    kv = k.iloc[-1]
    dv = d.iloc[-1]

    if kv > 80:
        zone = "OVERBOUGHT (>80)"
    elif kv < 20:
        zone = "OVERSOLD (<20)"
    else:
        zone = "mid-range (20-80)"

    sentiment = "bullish" if kv > dv else "bearish"
    cross = "%K above %D -> bullish tilt" if kv > dv else "%K below %D -> bearish tilt"

    value = f"%K={kv:.2f}, %D={dv:.2f} | {zone} | {cross}"
    return {"value": value, "sentiment": sentiment}


def check_volume(symbol, df):
    prev_volume = df["volume"].iloc[-2]
    current_volume = df["volume"].iloc[-1]

    if current_volume > prev_volume and current_volume > 100000:
        sentiment = "bullish"
        note = "Volume is increasing -> bullish tilt"
    elif current_volume > prev_volume and current_volume <= 100000:
        sentiment = "neutral"
        note = "Volume increasing but below threshold -> cautious bullish tilt"
    else:
        sentiment = "bearish"
        note = "Volume is decreasing -> bearish tilt"

    value = f"Current={current_volume:,}, Prev={prev_volume:,} | {note}"
    return {"value": value, "sentiment": sentiment}


def check_candle(symbol, df):
    # Bullish if close is 5%+ above open, bearish if close is 5%+ below open
    last_candle = df.iloc[-1]
    open_price = last_candle["open"]
    close_price = last_candle["close"]
    high_price = last_candle["high"]
    low_price = last_candle["low"]
 
    if open_price == 0:
        return {"value": "N/A (zero open)", "sentiment": "neutral"}
 
    pct_change = (close_price - open_price) / open_price * 100
 
    if pct_change > 5:
        sentiment = "bullish"
        note = f"Close is {pct_change:.2f}% above open -> bullish"
    elif pct_change < -5:
        sentiment = "bearish"
        note = f"Close is {abs(pct_change):.2f}% below open -> bearish"
    else:
        sentiment = "neutral"
        note = f"Close is {pct_change:.2f}% vs open -> within +/-5% range"
 
    value = f"O={open_price:,.2f} H={high_price:,.2f} L={low_price:,.2f} C={close_price:,.2f} | {note}"
    return {"value": value, "sentiment": sentiment}


def write_excel(rows):
    wb = Workbook()
    sheet = wb.active
    sheet.title = "Strategy Output"

    # Header row
    for col_idx, col_name in enumerate(COLUMNS, start=1):
        cell = sheet.cell(row=1, column=col_idx, value=col_name)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center")

    # Data rows
    for row_idx, row in enumerate(rows, start=2):
        for col_idx, col_name in enumerate(COLUMNS, start=1):
            cell_data = row.get(col_name, {"value": "", "sentiment": "neutral"})
            cell = sheet.cell(row=row_idx, column=col_idx, value=cell_data["value"])
            if cell_data["sentiment"] == "bullish":
                cell.fill = BULLISH_FILL
            elif cell_data["sentiment"] == "bearish":
                cell.fill = BEARISH_FILL
            cell.font = Font(name="Arial")

    # Reasonable column widths
    widths = [14, 40, 55, 60, 45, 45, 60]
    for col_idx, width in enumerate(widths, start=1):
        sheet.column_dimensions[sheet.cell(row=1, column=col_idx).column_letter].width = width

    wb.save(OUTPUT_FILE)
    print(f"✅ Excel report written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()