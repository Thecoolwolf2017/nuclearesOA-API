from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict
from datetime import datetime, timezone

app = FastAPI()

current_state: Dict[str, float] = {}
last_updated: str = None  # ISO 8601 string

class GameState(BaseModel):
    data: Dict[str, float]

@app.post("/api/state")
async def update_state(payload: GameState):
    global current_state, last_updated
    current_state.update(payload.data)
    last_updated = datetime.now(timezone.utc).isoformat()
    return {"status": "updated", "updated_keys": list(payload.data.keys())}

@app.get("/api/state")
async def get_state():
    return {
        "last_updated": last_updated,
        "data": current_state
    }