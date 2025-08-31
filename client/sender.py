import requests
import json
import hmac
import hashlib
import os
from datetime import datetime, timezone

# Load config
with open("client/config.json") as f:
    config = json.load(f)

API_URL = config["API_URL"]
API_KEY = config["API_KEY"].encode()

game_data = { 
    "CORE_TEMP": 500.0,
    "COOLANT_CORE_PRESSURE": 72.5
}# stub

payload = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "data": game_data
}

body = json.dumps(payload).encode()
signature = hmac.new(API_KEY, body, hashlib.sha256).hexdigest()

headers = {"X-Signature": signature}
response = requests.post(API_URL, data=body, headers=headers)

print("Status:", response.status_code)
print("Response:", response.json())
