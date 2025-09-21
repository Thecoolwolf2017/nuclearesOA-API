import json
import hmac
import time
import hashlib
import requests
from urllib.parse import urljoin
from datetime import datetime, timezone

# Load config
with open('client/config.json') as f:
    config = json.load(f)

API_URL = config['API_URL']
API_KEY = config['API_KEY'].encode()

# Game webserver endpoint
GAME_URL = urljoin(config['GAME_URL'].rstrip('/') + '/', '?Variable=WEBSERVER_BATCH_GET&value=*')
POLL_INTERVAL = config.get('POLL_INTERVAL', 5)


def deep_parse(value):
    """Recursively parse JSON-encoded strings into Python objects."""
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except Exception:
            return value
        return deep_parse(decoded)

    if isinstance(value, dict):
        return {k: deep_parse(v) for k, v in value.items()}

    if isinstance(value, list):
        return [deep_parse(item) for item in value]

    return value


while True:
    print('API SYNC ', end='')

    try:
        resp = requests.get(GAME_URL, timeout=10)
        status = resp.status_code
        if status >= 400:
            print(f'WARN[{status}] ', end='')

        try:
            raw_data = resp.json()
        except ValueError as exc:
            snippet = resp.text[:200].replace('\n', ' ')
            raise ValueError(f'Unexpected payload (status {status}): {snippet}') from exc
        game_values = raw_data.get('values', {})
        if not isinstance(game_values, dict):
            raise ValueError('Unexpected payload structure from game webserver')

        game_data = deep_parse(game_values)
        payload = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'data': game_data,
        }

        body = json.dumps(payload, separators=(',', ':')).encode()
        signature = hmac.new(API_KEY, body, hashlib.sha256).hexdigest()
        headers = {'X-Signature': signature, 'Content-Type': 'application/json'}

        response = requests.post(API_URL, data=body, headers=headers, timeout=10)
        response.raise_for_status()
        print('OK')

    except Exception as e:
        print('FAIL:', e)

    time.sleep(POLL_INTERVAL)
