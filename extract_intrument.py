import json
import requests

def load_instruments(json_file):
    with open(json_file, "r") as f:
        data = json.load(f)

    return {
        item["trading_symbol"]: item["instrument_key"]
        for item in data
    }

def get_instrument_key(ticker, lookup_dict):
    return lookup_dict.get(ticker.upper())


ticker_lookup = load_instruments("instruments.json")

print(get_instrument_key("ADANIENT", ticker_lookup))
print(get_instrument_key("RELIANCE", ticker_lookup))



ACCESS_TOKEN = 'eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI1UUNBOVQiLCJqdGkiOiI2YTI1NzgwOTFjNGM3YTE0YmVjMmQxNGYiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc4MDg0MDQ1NywiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzgwODY5NjAwfQ.cirwCKxvOCtSBoiRtC21EX4TLZ9ZMm4HUYIBqptrp4A'

headers = {
    "Accept": "application/json",
    "Authorization": f"Bearer {ACCESS_TOKEN}"
}

instrument_keys = [
    "NSE_EQ|INE002A01018",  # Reliance
    "NSE_EQ|INE423A01024",  # Adani Enterprises
    "NSE_EQ|INE674K01013"   # Aditya Birla Capital
]

url = (
    "https://api.upstox.com/v3/market-quote/ltp"
    f"?instrument_key={','.join(instrument_keys)}"
)

response = requests.get(url, headers=headers)

print(response.json())