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

See `render.yaml` for service configuration.

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

Schema-driven value translations (for `oneOf` enumerations) still work automatically: whenever a variable is described in `variables.json`, its values are translated to human-friendly descriptions.

## Sender client
The polling script in `client/sender.py` fetches the game batch endpoint (`/?Variable=WEBSERVER_BATCH_GET&value=*`), recursively normalizes nested JSON strings, and pushes the snapshot to the API.

`client/config.json` fields:

- `GAME_URL`: Base URL for the in-game webserver (no trailing slash).
- `API_URL`: Fully-qualified URL to the Render deployment ending with `/api/state`.
- `API_KEY`: Shared secret used for request signing.
- `POLL_INTERVAL` (optional): Seconds between polls (defaults to 5).

The sender prints `API SYNC OK` on successful uploads; errors are logged to the console and retried after the poll interval.

## Privacy
This API is designed **only for simulation/gameplay purposes**.

- **What data is collected:**
  - Plant status variables exposed by the Nucleares game (e.g., temperatures, pressures, valve states).
  - A timestamp of when the data was last updated.
- **What data is not collected:**
  - No personal, sensitive, or user-identifiable data is collected, stored, or transmitted.
  - No chat content, account information, or system details are recorded.
- **How the data is used:**
  - Data is sent from the local client to the API.
  - It is stored in memory only for the current snapshot.
  - It is retrieved by the GPT "Operating Assistant" solely to answer questions about the plant simulation.
  - No logs, databases, or historical storage are kept.
- **Retention:**
  - Data is overwritten with each update.
  - If the client is not running, no new data is uploaded.

This ensures the system is safe for public GPT usage and only reflects game simulation telemetry.
