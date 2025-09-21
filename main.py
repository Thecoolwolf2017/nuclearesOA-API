from fastapi import FastAPI, Header, HTTPException, Request
from typing import Any, Dict, List

import asyncio
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone
from itertools import count
from uuid import uuid4

from pydantic import BaseModel, Field, validator

API_KEY = os.getenv("API_KEY", "changeme").encode()
COMMAND_TOKEN = os.getenv("COMMAND_TOKEN", "changeme")
app = FastAPI()

current_state: Dict[str, Any] = {}
last_updated: str | None = None  # ISO 8601 string

if API_KEY == b"changeme":
    print(
        "WARNING: API_KEY is set to default 'changeme'. Please configure it in Render environment variables.",
        file=sys.stderr,
    )

if COMMAND_TOKEN == "changeme":
    print(
        "WARNING: COMMAND_TOKEN is set to default 'changeme'. Please configure it in Render environment variables.",
        file=sys.stderr,
    )

with open("variables.json", "r", encoding="utf-8") as f:
    SCHEMA = json.load(f)["properties"]

GROUPS: Dict[str, List[str]] = {
    group_name: list(group_def.get("properties", {}).keys())
    for group_name, group_def in SCHEMA.items()
}

VAR_TO_GROUP: Dict[str, str] = {
    var: group
    for group, variables in GROUPS.items()
    for var in variables
}

command_lock = asyncio.Lock()
command_store: Dict[str, Dict[str, Any]] = {}
command_sequence = count()
COMMAND_HISTORY_LIMIT = 250


class CommandTask(BaseModel):
    operation: str = Field(
        default="set",
        description="Operation to perform against the simulator webserver (set or pulse).",
    )
    variable: str = Field(
        ..., min_length=1, description="Webserver variable name targeted by this step."
    )
    value: Any = Field(..., description="Value to apply for the operation.")
    reset_value: Any | None = Field(
        default=None,
        description="Value to apply after hold_seconds when operation is 'pulse'.",
    )
    hold_seconds: float = Field(
        default=1.0,
        ge=0.0,
        description="Delay before resetting value for pulse operations.",
    )
    comment: str | None = Field(
        default=None,
        description="Optional operator-facing note describing the intent of this step.",
    )

    @validator("operation")
    def validate_operation(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"set", "pulse"}:
            raise ValueError("operation must be 'set' or 'pulse'")
        return normalized

    @validator("value")
    def ensure_value_present(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("value is required for command tasks")
        return value

    @validator("reset_value", always=True)
    def ensure_reset_value_for_pulse(cls, reset_value: Any, values: Dict[str, Any]) -> Any:
        if values.get("operation") == "pulse" and reset_value is None:
            raise ValueError("reset_value is required when operation is 'pulse'")
        return reset_value

    @validator("hold_seconds", always=True)
    def normalize_hold_seconds(cls, hold_seconds: float, values: Dict[str, Any]) -> float:
        if values.get("operation") != "pulse":
            return 0.0
        return hold_seconds


class CreateCommandRequest(BaseModel):
    purpose: str = Field(
        ..., min_length=3, max_length=200, description="Short summary of the intended effect."
    )
    tasks: List[CommandTask] = Field(
        ..., min_items=1, description="Ordered control steps to execute against the simulator."
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Optional additional context for the client."
    )
    priority: int = Field(
        default=0, ge=-10, le=10, description="Higher priority commands are dispatched first."
    )
    guidance: str | None = Field(
        default=None, description="Long-form instructions or rationale for human review."
    )

    @validator("purpose")
    def strip_purpose(cls, value: str) -> str:
        return value.strip()


class CommandResultRequest(BaseModel):
    status: str = Field(..., description="'completed' when successful, 'failed' when not.")
    detail: str | None = Field(default=None, description="Human-readable result summary.")
    outputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional machine-readable data captured while executing the command.",
    )

    @validator("status")
    def normalize_status(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"completed", "failed"}:
            raise ValueError("status must be 'completed' or 'failed'")
        return normalized


def _normalize_name(name: str) -> str:
    """Normalize keys/groups so lookups are case and space insensitive."""
    return name.upper().replace(" ", "_")


def _translate_value(group: str, var: str, value: Any) -> Any:
    """Translate value if schema has oneOf mapping, else return raw value or 'Unknown'."""
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


def _translate_for_var(var: str, value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value

    group = VAR_TO_GROUP.get(var)
    if group:
        return _translate_value(group, var, value)

    return value


def _collect_schema_group(normalized_group: str) -> Dict[str, Any]:
    selected: Dict[str, Any] = {}
    for var in GROUPS.get(normalized_group, []):
        if var in current_state:
            selected[var] = _translate_for_var(var, current_state[var])
    return selected


def _find_exact_key(normalized_group: str) -> str | None:
    for key in current_state.keys():
        if _normalize_name(key) == normalized_group:
            return key
    return None


def _collect_prefix_matches(normalized_group: str) -> Dict[str, Any]:
    matches: Dict[str, Any] = {}
    prefix = f"{normalized_group}_"
    for key, value in current_state.items():
        key_norm = _normalize_name(key)
        if key_norm.startswith(prefix):
            matches[key] = _translate_for_var(key, value)
    return matches


def _infer_dynamic_groups() -> List[str]:
    discovered = set(GROUPS.keys())
    for key, value in current_state.items():
        normalized = _normalize_name(key)
        if isinstance(value, dict):
            discovered.add(normalized)
        else:
            prefix = normalized.split("_", 1)[0]
            discovered.add(prefix)
    return sorted(discovered)


def _flatten(value: Any, parent_key: str = "") -> Dict[str, Any]:
    items: Dict[str, Any] = {}
    if isinstance(value, dict):
        for k, v in value.items():
            new_key = f"{parent_key}.{k}" if parent_key else str(k)
            items.update(_flatten(v, new_key))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            new_key = f"{parent_key}[{idx}]" if parent_key else f"[{idx}]"
            items.update(_flatten(item, new_key))
    else:
        if parent_key:
            items[parent_key] = value
    return items


def _flatten_state(state: Dict[str, Any]) -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    for key, value in state.items():
        key_str = str(key)
        if isinstance(value, (dict, list)):
            nested = _flatten(value, key_str)
            if not nested:
                flat[key_str] = value
            else:
                flat.update(nested)
        else:
            flat[key_str] = value
    return flat


def _resolve_dict_key(d: Dict[str, Any], target: str) -> str | None:
    normalized = _normalize_name(target)
    for key in d.keys():
        if _normalize_name(key) == normalized:
            return key
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _verify_command_token(token: str | None) -> None:
    if not token or token != COMMAND_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing command token")


def _public_command_view(command: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in command.items()
        if not key.startswith("_")
    }


def _trim_history_locked() -> None:
    if len(command_store) <= COMMAND_HISTORY_LIMIT:
        return

    removable = sorted(
        (
            entry
            for entry in command_store.values()
            if entry["status"] in {"completed", "failed"}
        ),
        key=lambda entry: entry["_sequence"],
    )

    while len(command_store) > COMMAND_HISTORY_LIMIT and removable:
        oldest = removable.pop(0)
        command_store.pop(oldest["id"], None)


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
    data = payload.get("data")
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Payload 'data' must be an object")

    current_state = data
    last_updated = payload.get("timestamp")

    return {"status": "updated", "updated_keys": list(data.keys())}


@app.get("/api/state")
async def get_full_state(flat: bool = False):
    if not current_state:
        raise HTTPException(status_code=404, detail="State has not been populated yet")

    data = _flatten_state(current_state) if flat else current_state
    return {"last_updated": last_updated, "data": data}


@app.get("/api/groups")
async def list_groups():
    if not current_state:
        return {
            "last_updated": last_updated,
            "schema_groups": sorted(GROUPS.keys()),
            "inferred_groups": [],
        }

    inferred = _infer_dynamic_groups()
    inferred_only = [g for g in inferred if g not in GROUPS]
    return {
        "last_updated": last_updated,
        "schema_groups": sorted(GROUPS.keys()),
        "inferred_groups": inferred_only,
    }


@app.get("/api/state/keys/{key_path:path}")
async def get_value_by_path(key_path: str):
    if not current_state:
        raise HTTPException(status_code=404, detail="State has not been populated yet")

    parts = [p for p in key_path.split("/") if p]
    if not parts:
        raise HTTPException(status_code=400, detail="Key path must not be empty")

    node: Any = current_state
    traversed: List[str] = []

    for part in parts:
        traversed.append(part)
        if isinstance(node, dict):
            resolved_key = _resolve_dict_key(node, part)
            if resolved_key is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Path segment '{part}' not found at {'/'.join(traversed[:-1]) or 'root'}",
                )
            node = node[resolved_key]
        elif isinstance(node, list):
            try:
                index = int(part)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"List index expected at {'/'.join(traversed[:-1]) or 'root'} but got '{part}'",
                ) from exc

            if index < 0 or index >= len(node):
                raise HTTPException(
                    status_code=404,
                    detail=f"Index {index} out of range at {'/'.join(traversed[:-1]) or 'root'}",
                )
            node = node[index]
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Cannot descend into non-container at {'/'.join(traversed[:-1]) or 'root'}",
            )

    if isinstance(node, str):
        translation_key = _resolve_dict_key(current_state, parts[0])
        if translation_key and len(parts) == 1:
            node = _translate_for_var(translation_key, node)

    return {"last_updated": last_updated, "data": node}


@app.get("/api/state/{group}")
async def get_state_group(group: str):
    if not current_state:
        raise HTTPException(status_code=404, detail="State has not been populated yet")

    normalized = _normalize_name(group)
    if normalized in {"ALL", "FULL"}:
        return {"last_updated": last_updated, "data": current_state}

    selected = _collect_schema_group(normalized)

    exact_key = _find_exact_key(normalized)
    if exact_key is not None:
        value = current_state[exact_key]
        if isinstance(value, dict):
            return {"last_updated": last_updated, "data": value}
        selected.setdefault(exact_key, _translate_for_var(exact_key, value))

    prefix_matches = _collect_prefix_matches(normalized)
    for key, value in prefix_matches.items():
        selected.setdefault(key, value)

    if not selected:
        raise HTTPException(status_code=404, detail=f"No variables found for group '{group}'")

    return {"last_updated": last_updated, "data": selected}


@app.post("/api/commands")
async def create_command(
    request: CreateCommandRequest,
    command_token: str | None = Header(default=None, alias="X-Command-Token"),
):
    _verify_command_token(command_token)

    command_id = uuid4().hex
    now = _now_iso()
    entry = {
        "id": command_id,
        "purpose": request.purpose,
        "guidance": request.guidance,
        "tasks": [task.dict() for task in request.tasks],
        "metadata": request.metadata,
        "priority": request.priority,
        "status": "pending",
        "created_at": now,
        "claimed_at": None,
        "claimed_by": None,
        "result": None,
        "_sequence": next(command_sequence),
    }

    async with command_lock:
        command_store[command_id] = entry
        _trim_history_locked()

    return {"status": "queued", "command": _public_command_view(entry)}


@app.get("/api/commands/next")
async def get_next_commands(
    limit: int = 1,
    client_id: str = "default",
    command_token: str | None = Header(default=None, alias="X-Command-Token"),
):
    _verify_command_token(command_token)

    if limit <= 0 or limit > 50:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 50")

    now = _now_iso()
    claimed: List[Dict[str, Any]] = []

    async with command_lock:
        pending = [
            entry for entry in command_store.values() if entry["status"] == "pending"
        ]
        pending.sort(key=lambda entry: (-entry["priority"], entry["_sequence"]))

        for entry in pending[:limit]:
            entry["status"] = "in_progress"
            entry["claimed_at"] = now
            entry["claimed_by"] = client_id
            claimed.append(_public_command_view(entry))

    return {"commands": claimed}


@app.post("/api/commands/{command_id}/result")
async def submit_command_result(
    command_id: str,
    request: CommandResultRequest,
    command_token: str | None = Header(default=None, alias="X-Command-Token"),
):
    _verify_command_token(command_token)

    async with command_lock:
        entry = command_store.get(command_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Command not found")

        if entry["status"] not in {"in_progress", "pending"}:
            raise HTTPException(
                status_code=409,
                detail=f"Command is already marked as {entry['status']}",
            )

        entry["status"] = request.status
        entry["result"] = {
            "detail": request.detail,
            "outputs": request.outputs,
            "reported_at": _now_iso(),
        }

    return {"command": _public_command_view(entry)}


@app.get("/api/commands/{command_id}")
async def get_command(
    command_id: str,
    command_token: str | None = Header(default=None, alias="X-Command-Token"),
):
    _verify_command_token(command_token)

    entry = command_store.get(command_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Command not found")

    return {"command": _public_command_view(entry)}

