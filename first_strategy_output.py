import concurrent.futures
import os
import threading
import time
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

OUTPUT_FILE = f"strategy_output_{datetime.now():%Y%m%d_%H%M%S}.xlsx"

# Column order in the output workbook: Symbol, then all concise columns first, then all detailed columns
COLUMNS = [
    "Symbol",
    "RSI5 Value",
    "MACD Value",
    "EMA Ribbon",
    "Stochastic Value",
    "Volume Value",
    "Candle % Change",
    "RSI5",
    "MACD",
    "Stochastic",
    "Volume",
    "Candle",
    "Green Count",
    "Red Count",
    "Neutral Count",
]

# Columns whose cells should wrap onto multiple lines within a single cell
WRAP_COLUMNS = {"EMA Ribbon"}

# Fill colors for bullish / bearish; neutral gets no fill
BULLISH_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
BEARISH_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
HEADER_FILL = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")

# =========================
# CLIENT
# =========================
client = api(api_key=API_KEY, host=HOST)


def load_symbols(csv_path="all_symbols.csv"):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Symbol file not found: {csv_path}")

    df = pd.read_csv(csv_path, header=None, usecols=[0], names=["symbol"] )
    symbols = df["symbol"].astype(str).str.strip()
    symbols = symbols[symbols != ""].tolist()
    return symbols


def process_symbol(symbol, index, total):
    print(f"Processing symbol {symbol} ({index}/{total})...")
    row = analyze_stock(symbol)
    return index, row


def main():
    try:
        print("Starting the main function...")
        symbols = load_symbols()
        #symbols = ["HSCL", "WOCKPHARMA", "GOODLUCK", "MSTCLTD", "MINDACORP", "JAYBARMARU"]
        total = len(symbols)
        rows = []
        failed_symbols = []
        failed_symbols_lock = threading.Lock()

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, total or 1)) as executor:
            future_to_symbol = {
                executor.submit(process_symbol, symbol, index, total): symbol
                for index, symbol in enumerate(symbols, start=1)
            }

            for future in concurrent.futures.as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    index, row = future.result()
                except Exception as e:
                    print(f"Error processing symbol {symbol}: {e}")
                    with failed_symbols_lock:
                        failed_symbols.append(symbol)
                    continue
                if row is not None:
                    rows.append((index, row))

        rows.sort(key=lambda item: item[0])
        rows = [row for _, row in rows]
        write_excel(rows)

        if failed_symbols:
            print(f"Symbols with processing errors: {failed_symbols}")

    except Exception as e:
        print(f"Error in main: {e}\n{traceback.format_exc()}")


def analyze_stock(symbol):
    # Fetch historical data for the symbol
    end = (datetime.now()).strftime("%Y-%m-%d")
    if datetime.now().hour < 18:  # If before 6 PM, use yesterday's date
        end = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    

    start = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")  # Last 100 days
    df = client.history(symbol=symbol, exchange="NSE", interval="D", start_date=start, end_date=end)

    # Ensure required columns are present
    if not all(col in df.columns for col in required_cols):
        print(f"Data for {symbol} is missing required columns.")
        return None
    
    if df.empty or len(df) < 50:  # Ensure we have enough data points for analysis
        print(f"Not enough data for {symbol}.")
        return None

    row = {"Symbol": {"value": symbol, "sentiment": "neutral"}}

    row["RSI5"], row["RSI5 Value"] = check_rsi(symbol, df, period=5)
    row["MACD"], row["MACD Value"] = check_macd(df)
    row["EMA Ribbon"] = check_ema(symbol, df)
    row["Stochastic"], row["Stochastic Value"] = check_stochastic(symbol, df)
    row["Volume"], row["Volume Value"] = check_volume(symbol, df)
    row["Candle"], row["Candle % Change"] = check_candle(symbol, df)

    factor_keys = ["RSI5", "MACD", "EMA Ribbon", "Stochastic", "Volume", "Candle"]
    counts = count_sentiments(row, factor_keys)
    row["Green Count"] = {"value": counts["bullish"], "sentiment": "neutral"}
    row["Red Count"] = {"value": counts["bearish"], "sentiment": "neutral"}
    row["Neutral Count"] = {"value": counts["neutral"], "sentiment": "neutral"}

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
    full = {"value": value, "sentiment": sentiment}
    concise = {"value": f"{rsi:.2f}", "sentiment": sentiment}
    return full, concise


def check_macd(df):
    macd_line, signal_line, hist = ta.macd(df["close"])

    m = macd_line.iloc[-1]
    s = signal_line.iloc[-1]
    h = hist.iloc[-1]

    sentiment = "bullish" if m > s else "bearish"
    momentum = "BULLISH (MACD above signal)" if m > s else "BEARISH (MACD below signal)"
    push = "strengthening" if h > 0 else "weakening / negative"

    value = f"MACD={m:.2f}, Signal={s:.2f}, Hist={h:.2f} | {momentum}, {push}"
    full = {"value": value, "sentiment": sentiment}
    concise = {"value": f"MACD={m:.2f}, Signal={s:.2f}", "sentiment": sentiment}
    return full, concise


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

    lines = [f"Close={df['close'].iloc[-1]:.2f}"]
    lines += [f"EMA{p}={emas[p]:.2f}" for p in periods]
    lines.append(note)
    value = "\n".join(lines)
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
    full = {"value": value, "sentiment": sentiment}
    concise = {"value": f"%K={kv:.2f}, %D={dv:.2f}", "sentiment": sentiment}
    return full, concise


def count_sentiments(row, factor_keys):
    sentiments = [row[key].get("sentiment", "neutral") for key in factor_keys if isinstance(row.get(key), dict)]
    return {
        "bullish": sum(1 for s in sentiments if s == "bullish"),
        "bearish": sum(1 for s in sentiments if s == "bearish"),
        "neutral": sum(1 for s in sentiments if s == "neutral"),
    }


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
    full = {"value": value, "sentiment": sentiment}
    concise = {"value": f"Current={current_volume:,}, Prev={prev_volume:,}", "sentiment": sentiment}
    return full, concise


def check_candle(symbol, df):
    # Bullish if close is 5%+ above open, bearish if close is 5%+ below open
    last_candle = df.iloc[-1]
    open_price = last_candle["open"]
    close_price = last_candle["close"]
    high_price = last_candle["high"]
    low_price = last_candle["low"]
 
    if open_price == 0:
        na = {"value": "N/A (zero open)", "sentiment": "neutral"}
        return na, na

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
    full = {"value": value, "sentiment": sentiment}
    concise = {"value": pct_change, "sentiment": sentiment}
    return full, concise


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
            if col_name in WRAP_COLUMNS:
                cell.alignment = Alignment(wrap_text=True, vertical="top")

        # Give the EMA row enough height to show its multi-line content
        sheet.row_dimensions[row_idx].height = 90

    # Reasonable column widths: Symbol, concise columns, detailed columns, and sentiment counts
    widths = [14, 14, 14, 55, 14, 14, 14, 40, 46, 30, 30, 60, 12, 12, 12]
    for col_idx, width in enumerate(widths, start=1):
        sheet.column_dimensions[sheet.cell(row=1, column=col_idx).column_letter].width = width

    wb.save(OUTPUT_FILE)
    print(f"✅ Excel report written to {OUTPUT_FILE}")


if __name__ == "__main__":
    start_time = time.perf_counter()
    main()
    elapsed = time.perf_counter() - start_time
    print(f"⏱️ Total runtime: {elapsed:.2f} seconds")