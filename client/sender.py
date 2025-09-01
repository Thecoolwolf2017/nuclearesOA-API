import json, hmac, time, hashlib, requests
from datetime import datetime, timezone

# Load config
with open("client/config.json") as f:
    config = json.load(f)

API_URL = config["API_URL"]
API_KEY = config["API_KEY"].encode()

# Game webserver endpoint
GAME_URL = config["GAME_URL"] + "/?Variable=WEBSERVER_BATCH_GET&value=*"

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

while True:
    print("API SYNC ", end="")
    
    try:
        resp = requests.get(GAME_URL)
        raw_data = json.loads(resp.text)
        game_data = deep_parse(raw_data.get("values", {}))
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(),"data": game_data}
        body = json.dumps(payload).encode()
        signature = hmac.new(API_KEY, body, hashlib.sha256).hexdigest()
        headers = {"X-Signature": signature}
        response = requests.post(API_URL, data=body, headers=headers)
        print("OK")

    except Exception as e:
        print("FAIL: ", e)

    time.sleep(5)