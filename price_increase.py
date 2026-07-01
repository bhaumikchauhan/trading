# The workhorse call: download daily OHLCV candles into a DataFrame.
import os
from datetime import datetime, timedelta

from openalgo import api

from retrieve_nifty_symbols import get_nifty_constituents

client = api(
    api_key=os.getenv("OPENALGO_API_KEY", "your_api_key_here"),
    host=os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000"),
)

end1 = '2026-03-25'
start1='2026-03-24'

end2 = '2026-06-25'
start2='2026-06-24'


column = 'close'

instruments = get_nifty_constituents(50)
for instrument in instruments:
        try:
            df1 = client.history(symbol=instrument, exchange="NSE", interval="D", start_date=start1, end_date=end1)
            df2 = client.history(symbol=instrument, exchange="NSE", interval="D", start_date=start2, end_date=end2)
            price1 = df1[column].iloc[0]
            price2 = df2[column].iloc[0]

            if price2 > price1:
                print(f"  [{instrument}] {column} price increased from {price1} to {price2} by percentage: {((price2 - price1) / price1) * 100:.2f}%")
        except Exception as e:
            print(f"  [{instrument}] Error: {e}")