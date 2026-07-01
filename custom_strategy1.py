import os
import pandas as pd
from datetime import datetime, timedelta
import time
import csv

from openalgo import api

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


def fetch_history(symbol, start_date="2024-01-01", end_date=datetime.now().strftime("%Y-%m-%d")):
    try:

        df = client.history(
                symbol=symbol,
                exchange="NSE",
                interval="D",
                start_date=start_date,
                end_date=end_date
            )

        if df is not None and 'status' in df and df['status'] != 'error':
            if all(col in df.columns for col in required_cols):
                df = df.sort_index()

        return df

    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None


def get_stocks_with_ATH_within_last_year(symbol, output):
    start_time = time.time()
    df = fetch_history(symbol)

    if df is None:
        return

    #print(df)

    # Find ATH and ATH date
    ath_idx = df["high"].idxmax()
    ath_price = df.loc[ath_idx, "high"]

    end_time = time.time()

    elapsed_time = end_time - start_time
    time_convert(elapsed_time, symbol=symbol)

    # Check if ATH was within last 1 year
    
    print(f"Checking {symbol}...ATH Date: {ath_idx.date()}, ATH Price: {ath_price}")

    if ath_idx < one_year_ago:
        return
    print(f"ATH is within last 1 year for {symbol}.")

    output[symbol] = {
        "ATH Date": ath_idx.date(),
        "ATH Price": ath_price
    }


def check_stock(df, symbol):
    # Ensure date is datetime
    df["date"] = pd.to_datetime(df.index)

    # Sort by date
    df = df.sort_values("date").reset_index(drop=True)

    # 1. Find ATH
    ath_idx = df["high"].idxmax()
    ath_price = df.loc[ath_idx, "high"]
    ath_date = df.loc[ath_idx, "date"]

    

    # 2. Check if ATH is within last 1 year
    one_year_ago = df["date"].max() - pd.Timedelta(days=365)

    if ath_date < one_year_ago:
        print(f"For symbol {symbol}: ATH Date: {ath_date}, ATH Price: {ath_price} is NOT within last 1 year.")
        return {
            "ath_within_1_year": False,
            "price_fell_68_percent": False
        }

    # 3. Check if price fell 68% after ATH
    after_ath = df[df["date"] >= ath_date]

    lowest_after_ath_idx = after_ath["low"].idxmin()
    lowest_after_ath_price = after_ath.loc[lowest_after_ath_idx, "low"]
    lowest_after_ath_date = after_ath.loc[lowest_after_ath_idx, "date"]

    fell_68_percent = lowest_after_ath_price <= ath_price * 0.32  # 68% drop

    print(f"For symbol {symbol}: ATH Date: {ath_date}, ATH Price: {ath_price}, lowest after ATH: {lowest_after_ath_price}, Fell by: {(ath_price - lowest_after_ath_price) / ath_price * 100:.2f}%")

    return {
        "ath_price": ath_price,
        "ath_date": ath_date,
        "lowest_after_ath": lowest_after_ath_price,
        "lowest_after_ath_date": lowest_after_ath_date,
        "ath_within_1_year": True,
        "price_fell_68_percent": fell_68_percent
    }

def time_convert(seconds, symbol=None):
    mins = seconds // 60
    seconds = seconds % 60
    hours = mins // 60
    mins = mins % 60
    if symbol:
        print(f"Time Elapsed for {symbol} = {int(hours)}:{int(mins)}:{seconds:.2f}")
    else:
        print(f"Time Elapsed = {int(hours)}:{int(mins)}:{seconds:.2f}")


def get_all_symbols():
    symbols = []
    with open(r"D:\code\all_symbols.csv", "r", newline="", encoding="utf-8") as file:
        reader = csv.reader(file)

        for row in reader:
            symbols.append(row[0])  # Assuming symbol is in the first column
    return symbols

def main():
    try:
        #symbols = get_all_symbols()
    
        #symbols = client.symbols(exchange="NSE")
        #symbols = get_nifty_constituents(50)
        #symbols = ["ETERNAL", "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL"]
        symbols = ["TMPV", "TRENT"]

        # all_instruments = client.instruments(exchange="NSE")
        # all_stocks = {}
        
        # for instrument in all_instruments:
        #     if instrument['instrument_type'] == 'EQ' and instrument['lotsize'] == 1:
        #         all_stocks[instrument['symbol']] = instrument
        
        # print(list(all_stocks.keys())[:5])  # Print the first 5 symbols to verify the structure

        nse_df = client.instruments(exchange="NSE")
        print(f"Total NSE instruments: {len(nse_df)}")

        distinct_symbols = nse_df['symbol'].unique()
        print(f"Distinct NSE symbols: {len(distinct_symbols)}")

        output = {}

        start_time = time.time()
        
        for i, symbol in enumerate(symbols, start=1):
            print(f"Processing {i}/{len(symbols)}: {symbol}")
            try:
                df = df = fetch_history(symbol)
                check_result = check_stock(df, symbol)
                if check_result and check_result["ath_within_1_year"] and check_result["price_fell_68_percent"]:
                    output[symbol] = {
                        "ATH Date": check_result["ath_date"],
                        "ATH Price": check_result["ath_price"],
                        "ATL Price": check_result["lowest_after_ath"],
                        "ATL Date": check_result["lowest_after_ath_date"],
                        "Drawdown": ((check_result["ath_price"] - check_result["lowest_after_ath"]) / check_result["ath_price"]) * 100
                    }
            except Exception as e:
                print(f"Error processing {symbol}: {e}")

        end_time = time.time()

        elapsed_time = end_time - start_time
        time_convert(elapsed_time)



        result = "Symbol,ATH Date,ATH Price,ATL Price,Drawdown (%)\n"
        for symbol, details in output.items():
            result += f"{symbol},{details['ATH Date']},{details['ATH Price']},{details['ATL Price']},{details['Drawdown']:.2f}\n"

        # Save results to a CSV file
        with open(r"D:\code\openalgo-zerodha\openalgo\results.csv", "w") as f:
            f.write(result)

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    main()

