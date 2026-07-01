# The workhorse call: download daily OHLCV candles into a DataFrame.
import os
from datetime import datetime, timedelta

from openalgo import api

from retrieve_nifty_symbols import get_nifty_constituents

client = api(
    api_key=os.getenv("OPENALGO_API_KEY", "your_api_key_here"),
    host=os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000"),
)

end = '2026-06-25'
start='2026-06-24'




# df = client.history(symbol="RELIANCE", exchange="NSE", interval="D", start_date=start, end_date=end)
# # print("Shape  :", df.shape)
# # print("Columns:", df.columns.tolist())
# t = df["volume"].iloc[0]
# print(t)  # print the volume column


instruments = get_nifty_constituents(50)
for instrument in instruments:
        try:
            df = client.history(symbol=instrument, exchange="NSE", interval="D", start_date=start, end_date=end)
            if df['volume'].iloc[0] > 100000:
                 print(f"  {instrument} volume: {df['volume'].iloc[0]}")
        except Exception as e:
            print(f"  [{instrument}] Error: {e}")