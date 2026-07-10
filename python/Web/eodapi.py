import requests
import json
from datetime import datetime, timedelta

# 1. Define your core parameters
# You get this token from your EODData account dashboard.
API_TOKEN = "xNrqzn9LHldoTDrvin683LoM"
EXCHANGE = "NASDAQ"
TICKER = "AAPL"

# 2. Dynamically calculate the date range for the last 6 weeks
end_date = datetime.now()
# timedelta is used to subtract a period of time from a date
# start_date =   #end_date - timedelta(days=1000)

# Format the dates into the YYYY-MM-DD string format that most APIs expect
end_date_str = end_date.strftime('%Y-%m-%d')
start_date_str = "2026-01-02"
# start_date_str = start_date.strftime('%Y-%m-%d')

# 3. Construct the URL for the HISTORICAL data endpoint
# Use EODData's actual REST API endpoint for historical quote lists.
# Note that EODData uses 'apiKey=' instead of 'api_token='.
url = (
    f"https://api.eoddata.com/Quote/List/{EXCHANGE}/{TICKER}?ApiKey={API_TOKEN}&Interval=d&FromDateStamp={start_date_str}&ToDateStamp={end_date_str}")

print(f"Making request to: {url}")

try:
    # 4. Make the GET request
    # Add a standard browser User-Agent header to avoid being blocked as a bot.
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    # Add a timeout (in seconds) to prevent the script from hanging indefinitely.
    response = requests.get(url, timeout=15, headers=headers)

    # 5. Check if the request was successful
    if response.status_code == 200:
        # For a date range, the API will return a LIST of daily records, not a single object.
        historical_data = response.json()

        print("\n--- Success! ---")
        print(f"Successfully retrieved {len(historical_data)} trading days of data.")

        # Let's inspect the first and last records to see the structure
        if historical_data:
            print("\n--- Earliest Record (from ~6 weeks ago) ---")
            print(json.dumps(historical_data[0], indent=4))

            print("\n--- Most Recent Record ---")
            print(json.dumps(historical_data[-1], indent=4))

    else:
        # If it failed, print the error status and any response text
        print(f"\n--- Error! ---")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")

except requests.exceptions.RequestException as e:
    print(f"\n--- Request Failed! ---")
    print(f"An error occurred: {e}")
