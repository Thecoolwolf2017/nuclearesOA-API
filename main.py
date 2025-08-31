from fastapi  import FastAPI, Request, HTTPException
from pydantic import BaseModel
from typing   import Dict
from datetime import datetime, timezone

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

@app.get("/api/state")
async def get_state():
    return {
        "last_updated": last_updated,
        "data": current_state
    }