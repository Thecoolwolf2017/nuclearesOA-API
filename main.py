from fastapi  import FastAPI, Request, HTTPException
from typing   import Dict

import os, sys, hmac, hashlib, json

API_KEY = os.getenv("API_KEY", "changeme").encode()
app     = FastAPI()

current_state: Dict[str, float] = {}
last_updated:  str = None  # ISO 8601 string

if API_KEY == b"changeme":
    print("WARNING: API_KEY is set to default 'changeme'. Please configure it in Render environment variables.", file=sys.stderr)

@app.post("/api/state")
async def update_state(request: Request):
    global current_state, last_updated

    body = await request.body()
    signature = request.headers.get("X-Signature")

    if not signature:
        raise HTTPException(status_code=401, detail="Missing signature")

    expected = hmac.new(API_KEY, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()
    current_state = payload["data"]
    last_updated = payload.get("timestamp")

    return {"status": "updated", "updated_keys": list(payload["data"].keys())}

with open("variables.json", "r") as f:
    GROUPS: Dict[str, list] = json.load(f)

@app.get("/api/state/{group}")
async def get_state_group(group: str):
    global current_state, last_updated

    vars_in_group = GROUPS.get(group.upper())
    if not vars_in_group:
        raise HTTPException(status_code=404, detail=f"No group '{group}' defined")

    selected = {k: current_state.get(k) for k in vars_in_group if k in current_state}
    if not selected:
        raise HTTPException(status_code=404, detail=f"No variables found for group '{group}'")

    return {"last_updated": last_updated, "data": selected}