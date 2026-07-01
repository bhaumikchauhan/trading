import requests
from openalgo import api
import os

# Configuration
API_KEY = os.getenv("OPENALGO_API_KEY")
HOST = os.getenv("HOST_SERVER") or os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")  # If authentication is enabled

def get_all_stocks():
    """
    Fetches the complete stock list from OpenAlgo.
    This assumes your OpenAlgo instance is connected to a broker
    that provides the instrument list.
    """
    try:
        headers = {}
        if API_KEY:
            headers["Authorization"] = f"Bearer {API_KEY}"

        # Endpoint for instruments (varies by broker integration)
        url = f"{HOST}/api/instruments"

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        data = response.json()

        if not data:
            print("No stock data received.")
            return []

        # Example: Extract symbol names
        stock_list = [item.get("symbol") for item in data if "symbol" in item]
        return stock_list

    except requests.exceptions.RequestException as e:
        print(f"Error fetching stock list: {e}")
        return []

if __name__ == "__main__":
    stocks = get_all_stocks()
    print(f"Total stocks fetched: {len(stocks)}")
    if stocks:
        print("Sample symbols:", stocks[:10])  # Show first 10
