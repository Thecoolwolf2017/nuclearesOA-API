# Nucleares Operating Assistant API

This project provides an API backend and client for connecting the game **Nucleares** with a GPT-powered "Operating Assistant". It collects live telemetry data from the in-game plant webserver, forwards it to a cloud API (Render), and makes it accessible to GPT agents for reasoning and operator guidance.

A stripped version of the assistant, without API capabilities, can be found [here](https://chatgpt.com/g/g-68c7033fc76c819184cb9d619d5908fc-nucleares-oa).

## How it works
The GPT is fed data stored in `GPT/documentation`. It uses this data to help and guide the player in operating the in-game nuclear power plant. A private copy of this GPT can be made by OpenAI Plus members, with the capability to query the game webserver through the API. The API receives data from the sender script running locally, which routes it from the local webserver to a public one. The server now organizes every available webserver variable on-demand so GPT can query everything that the game exposes.

## Deployment
The server is designed to run on [Render](https://render.com).

- Python 3.11+
- FastAPI + Uvicorn
- HMAC signature validation for client POSTs
- Command queue secured by `COMMAND_TOKEN`

See `render.yaml` for service configuration.

Configure the following environment variables on Render:

- `API_KEY`: shared secret used to sign `/api/state` updates.
- `COMMAND_TOKEN`: shared secret used by GPT (for command creation) and the local sender (for command execution).

## API Endpoints
All endpoints are served beneath `/api`.

- `POST /api/state`
  Upload a new snapshot from the local sender. The body must be an object containing `timestamp` (ISO-8601 string) and `data` (the full values payload). The request must include an `X-Signature` header with the HMAC-SHA256 signature of the JSON body using the shared API key.
- `GET /api/state`
  Returns the latest snapshot. Pass `?flat=true` to receive a flattened dictionary where nested objects are expanded using `.` and `[index]` notation.
- `GET /api/groups`
  Lists schema-defined groups (from `variables.json`) and any additional groups inferred from the live dataset (based on prefixes and nested objects).
- `GET /api/state/{group}`
  Retrieves variables that belong to the specified group. Group names are case-insensitive; the helper also accepts `all`/`full` to return the entire payload. If the incoming snapshot contained objects whose keys match the requested group, the raw nested structure is returned.
- `GET /api/state/keys/{key_path}`
  Traverses nested objects or lists by path segments. For example, `/api/state/keys/VALVULA_ENTRADA_NUCLEO_02/Sector` digs into the `VALVULA_ENTRADA_NUCLEO_02` object and returns its `Sector` field. List indices are supplied as integers (e.g., `/api/state/keys/WEATHER_FORECAST_JSON/0/Day`).
- `POST /api/commands`
  Queues a new control command. The request must include the header `X-Command-Token: <COMMAND_TOKEN>` and provide a `purpose` plus `tasks` (each task targets a webserver variable and specifies an operation such as `set` or `pulse`). The endpoint returns the created command envelope.
- `GET /api/commands/next`
  Used by the local sender. Returns the oldest pending commands (ordered by priority, creation time). Commands are marked `in_progress` as soon as they are claimed.
- `POST /api/commands/{command_id}/result`
  Allows the local sender to report the final status (`completed`/`failed`) together with operator-facing details and machine-readable outputs.
- `GET /api/commands/{command_id}`
  Fetches a single command, including its status and execution result. Useful for GPT to monitor previously issued orders.

Schema-driven value translations (for `oneOf` enumerations) still work automatically: whenever a variable is described in `variables.json`, its values are translated to human-friendly descriptions.

## Sender client
The polling script in `client/sender.py` fetches the game batch endpoint (`/?Variable=WEBSERVER_BATCH_GET&value=*`), recursively normalizes nested JSON strings, and pushes the snapshot to the API. After synchronising telemetry, it optionally polls the command queue and replays the requested control actions against the local webserver.

`client/config.json` fields:

- `GAME_URL`: Base URL for the in-game webserver (no trailing slash). Used for both telemetry reads and command writes unless `GAME_COMMAND_URL` is supplied.
- `API_URL`: Fully-qualified URL to the Render deployment ending with `/api/state`.
- `API_KEY`: Shared secret used for request signing.
- `COMMAND_URL`: Base command endpoint (e.g., `https://.../api/commands`).
- `COMMAND_TOKEN`: Matches the server-side `COMMAND_TOKEN` environment variable.
- `COMMAND_POLL_LIMIT` (optional): Maximum number of commands to claim per poll (defaults to 3).
- `COMMAND_TIMEOUT` (optional): Seconds before HTTP command requests time out (defaults to 10).
- `CLIENT_ID` (optional): Identifier reported when claiming commands (defaults to the hostname).
- `POLL_INTERVAL` (optional): Seconds between telemetry polls (defaults to 5).

The sender prints `API SYNC OK` on successful uploads, followed by command execution summaries (e.g., `CMD[abc123] OK Start condenser pump`). Errors are logged to the console and retried after the poll interval.

- The sender also mirrors the game's `WEBSERVER_LIST_VARIABLES_JSON` output inside the telemetry payload (`_meta.webserver_catalog`). Command requests are validated against that list before they hit the plant, so unsupported variable names fail fast with a descriptive error.

### Command queue semantics

Commands queued through `/api/commands` follow this structure:

```json
{
  "purpose": "Start condenser circulation pump",
  "priority": 0,
  "tasks": [
    { "operation": "set", "variable": "CONDENSER_CIRCULATION_PUMP_SWITCH", "value": true },
    { "operation": "set", "variable": "CONDENSER_CIRCULATION_PUMP_ORDERED_SPEED", "value": 25 }
  ]
}
```

Supported task operations:

- `set`: send a single value to the given variable.
- `pulse`: send `value`, wait `hold_seconds` (default 1 second), then send `reset_value`.

Additional context supplied in `metadata` or `guidance` is forwarded to the client and written back in the execution result.

## Privacy
This API is designed **only for simulation/gameplay purposes**.

- **What data is collected:**
  - Plant status variables exposed by the Nucleares game (e.g., temperatures, pressures, valve states).
  - A timestamp of when the data was last updated.
  - Execution summaries for issued commands.
- **What data is not collected:**
  - No personal, sensitive, or user-identifiable data is collected, stored, or transmitted.
  - No chat content, account information, or system details are recorded.
- **How the data is used:**
  - Data is sent from the local client to the API.
  - It is stored in memory only for the current snapshot and outstanding commands.
  - It is retrieved by the GPT "Operating Assistant" solely to answer questions about the plant simulation or to dispatch operator-approved control steps.
  - No logs, databases, or historical storage are kept.
- **Retention:**
  - Telemetry data is overwritten with each update.
  - Completed command records are retained only while the in-memory buffer limit is not exceeded.
  - If the client is not running, no new data is uploaded and commands remain pending until claimed.

This ensures the system is safe for public GPT usage and only reflects game simulation telemetry.
