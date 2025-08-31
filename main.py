from fastapi  import FastAPI, Request, HTTPException, Query
from pydantic import BaseModel
from typing   import Dict

import os, sys, hmac, hashlib

app = FastAPI()

current_state: Dict[str, float] = {}
last_updated: str = None  # ISO 8601 string

API_KEY = os.getenv("API_KEY", "changeme").encode()

if API_KEY == b"changeme":
    print("WARNING: API_KEY is set to default 'changeme'. Please configure it in Render environment variables.", file=sys.stderr)

class GameState(BaseModel):
    data: Dict[str, float]

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
    current_state.update(payload["data"])
    last_updated = payload.get("timestamp")

    return {"status": "updated", "updated_keys": list(payload["data"].keys())}

@app.get("/api/state/{view}")
async def get_state_view(view: str, keys: str = Query(None)):
    global current_state, last_updated

    if keys and view:
        raise HTTPException(status_code=400, detail="Use either 'keys' query OR 'view' path, not both")

    if keys:
        selected = {k: current_state.get(k) for k in keys.split(",") if k in current_state}
        return {"last_updated": last_updated, "data": selected}

    prefix = view.upper()
    selected = {k: v for k, v in current_state.items() if k.startswith(prefix + "_")}

    if not selected:
        raise HTTPException(status_code=404, detail=f"No variables found for view '{view}'")

    return {"last_updated": last_updated, "data": selected}
