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

with open("variables.json", "r", encoding="utf-8") as f:
    SCHEMA = json.load(f)["properties"]

GROUPS: Dict[str, list] = {
    group_name: list(group_def.get("properties", {}).keys())
    for group_name, group_def in SCHEMA.items()
}

@app.get("/api/state/{group}")
async def get_state_group(group: str):
    global current_state, last_updated

    vars_in_group = GROUPS.get(group.upper())
    if not vars_in_group:
        raise HTTPException(status_code=404, detail=f"No group '{group}' defined")

    selected = {}
    for k in vars_in_group:
        if k in current_state:
            selected[k] = _translate_value(group.upper(), k, current_state[k])

    if not selected:
        raise HTTPException(status_code=404, detail=f"No variables found for group '{group}'")

    return {"last_updated": last_updated, "data": selected}

def _translate_value(group: str, var: str, value):
    """Translate value if schema has oneOf mapping, else return raw value or 'Unknown'"""
    group_schema = SCHEMA.get(group, {}).get("properties", {})
    var_schema = group_schema.get(var)
    if not var_schema:
        return value

    one_of = var_schema.get("oneOf")
    if one_of:
        for entry in one_of:
            if "const" in entry and entry["const"] == value:
                return entry.get("description", str(value))

        for entry in one_of:
            if "type" in entry:
                return entry.get("description", "Unknown")

        return "Unknown"

    return value