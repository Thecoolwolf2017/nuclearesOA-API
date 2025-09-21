from fastapi import FastAPI, Request, HTTPException
from typing import Any, Dict, List

import os
import sys
import hmac
import hashlib
import json

API_KEY = os.getenv("API_KEY", "changeme").encode()
app = FastAPI()

current_state: Dict[str, Any] = {}
last_updated: str | None = None  # ISO 8601 string

if API_KEY == b"changeme":
    print(
        "WARNING: API_KEY is set to default 'changeme'. Please configure it in Render environment variables.",
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
