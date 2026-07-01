#https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv

import pandas as pd
import requests
from io import StringIO


  # For Nifty 50 symbols


def get_nifty_constituents(suffix):
    if suffix == 50:
        url = "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv"
    elif suffix == 500:
        url = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"

    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/market-data/live-equity-market"
    }

    with requests.Session() as session:
        session.headers.update(headers)
        session.get("https://www.nseindia.com", timeout=5)  # Warm-up to set cookies

        response = session.get(url, timeout=10)
        
        if response.status_code == 200:
            csv_content = response.content.decode('utf-8')
            df = pd.read_csv(StringIO(csv_content))
            return df['Symbol']
        else:
            print(f"Failed to retrieve data. Status code: {response.status_code}")