import requests
import json
import hmac
import hashlib
from datetime import datetime, timezone

# Load config
with open("client/config.json") as f:
    config = json.load(f)

API_URL = config["API_URL"]
API_KEY = config["API_KEY"].encode()

# Game webserver endpoint
GAME_URL = "http://localhost:8785/?Variable=WEBSERVER_BATCH_GET&value=*"

def deep_parse(d):
    """Recursively parse JSON strings into dicts where possible"""
    for k, v in list(d.items()):
        if isinstance(v, str):
            try:
                d[k] = json.loads(v)
            except Exception:
                pass
        elif isinstance(v, dict):
            deep_parse(v)
    return d

resp = requests.get(GAME_URL)
print("Game WebServer HTTP response code: ", resp.status_code)

try:
    raw_data = json.loads(resp.text)
    game_data = deep_parse(raw_data.get("values", {}))
except Exception as e:
    print("Failed to parse game response:", e)
    game_data = {}

payload = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "data": game_data
}

body = json.dumps(payload).encode()
signature = hmac.new(API_KEY, body, hashlib.sha256).hexdigest()

headers = {"X-Signature": signature}
response = requests.post(API_URL, data=body, headers=headers)

print("API response code:", response.status_code)