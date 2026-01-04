# Nucleares Operating Assistant API

This project provides an API backend and client for connecting the game **Nucleares** with a GPT-powered "Operating Assistant". It collects live telemetry data from the in-game plant webserver, forwards it to a cloud API (Render), and makes it accessible to GPT agents for reasoning and operator guidance.

A stripped version of the assistant, without API capabilities, can be found [here](https://chatgpt.com/g/g-68c7033fc76c819184cb9d619d5908fc-nucleares-oa).

## How it works
The GPT is fed data stored in `GPT/documentation`. It uses this data to help and guide the player in operating the in-game nuclear power plant. A private copy of this GPT can be made by OpenAI Plus members, with the capability to query the game webserver through the API. The API receives data from the sender script running locally, which routes it from the local webserver to a public one. The server now organizes every available webserver variable on-demand so GPT can query everything that the game exposes.

## Quick start
1. **Get the code** by cloning this repository (or downloading the ZIP) onto the machine that will run the API and sender.
2. **Deploy the API server** locally or on Render using the steps in the [Deployment](#deployment) section.
3. **Run the telemetry sender** so your game webserver streams data to the API (see [Running the sender locally](#running-the-sender-locally)). Make sure the Nucleares in-game webserver is running and reachable at the URL you configure in `GAME_URL`.
4. **Connect the custom GPT action** by uploading the manifest in `GPT/action.yaml` and wiring in your API URL and command token (see [Custom GPT setup](#custom-gpt-setup)).
5. Step through the [Verify the end-to-end setup](#verify-the-end-to-end-setup) checklist to ensure telemetry and commands flow correctly.

## Prerequisites
- **Software**: Python 3.11+, the Nucleares game with its in-game webserver enabled, and either PowerShell (Windows) or a POSIX shell (macOS/Linux).
- **Accounts**: Render (for hosted deployment) and ChatGPT Plus/Team (to create the GPT). Local-only users can skip Render but still need GPT access.
- **Secrets**: Choose strong values for `API_KEY` and `COMMAND_TOKEN` and keep them outside version control.
- **Networking**: The machine running `client/sender.py` must reach both the game webserver and your API host (localhost or Render).
- **Project layout**: Keep the `GPT/` directory intact; you’ll zip it or select `GPT/action.yaml` directly when uploading the action manifest.

## Deployment
The server is designed to run on [Render](https://render.com).

- Python 3.11+
- FastAPI + Uvicorn
- HMAC signature validation for client POSTs
- Command queue secured by `COMMAND_TOKEN`

### Run locally (development/testing)
1. Create a virtual environment and install dependencies:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate
   pip install -r requirements.txt
   ```
2. Provide authentication secrets for this shell:
   ```powershell
   $env:API_KEY = "choose-a-long-random-string"
   $env:COMMAND_TOKEN = "choose-another-secret"
   ```
   > On macOS/Linux use `export API_KEY=...` / `export COMMAND_TOKEN=...`.
   > Tip: run `python scripts/rotate_secrets.py` to generate fresh values and store them in a local `.env`.
3. Launch the API with Uvicorn:
   ```powershell
   python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```
4. Visit `http://localhost:8000/docs` to explore the OpenAPI UI. While the sender is offline the state endpoints return `404` (no snapshot yet).

Point the sender at the local instance by setting `API_URL` to `http://localhost:8000/api/state` and `COMMAND_URL` to `http://localhost:8000/api/commands`.

### Deploy to Render (production)
1. Fork or import this repository into your Render account.
2. Create a **Web Service** and let Render auto-detect the `render.yaml` blueprint, or supply the following command manually:
   ```
   python -m uvicorn main:app --host 0.0.0.0 --port 10000
   ```
3. Set the environment variables in Render’s dashboard:
   - `API_KEY`: shared secret that signs `/api/state` updates from the sender.
   - `COMMAND_TOKEN`: shared secret shared by GPT and the sender for command operations.
4. Deploy the service and note the Render URL, e.g. `https://nuclearesoa-api-xxxx.onrender.com`.
5. Update `client/config.json` (`API_URL`, `COMMAND_URL`) and `GPT/action.yaml` (`servers[0].url`) to reference your Render hostname.

Configure the following environment variables on Render:

- `API_KEY`: shared secret used to sign `/api/state` updates.
- `COMMAND_TOKEN`: shared secret used by GPT (for command creation) and the local sender (for command execution).
- `HEALTH_MAX_AGE_SECONDS` (optional): maximum allowed telemetry age before `/api/health` reports `stale` (defaults to 300 seconds).
- `BUILD_SHA` / `BUILD_REF` (optional): metadata injected into `/api/status` for identifying deployments.

> **Smoke test behaviour:** The GitHub Actions smoke workflow treats exit code `2` from `tests/smoke_test.py` as an intentional “offline” state. The job still succeeds so automation continues, but the availability/status badges flip to “offline / fail”. Any other non-zero exit code fails the workflow.

Use `python scripts/rotate_secrets.py` to generate fresh `API_KEY` / `COMMAND_TOKEN` pairs and write them to your local `.env`. Remember to copy the new values into Render (or other hosting) after rotation.

### Smoke test

To exercise the API manually, run the bundled smoke script:

```powershell
python tests/smoke_test.py
```

It performs the same checks as the CI job (health, groups, state, commands) and exits with:

- `0` when every endpoint responds with healthy JSON.
- `2` when the API is unreachable or `/api/health` reports stale telemetry. Workflows treat this as “offline” and keep badges red/grey while still succeeding.
- `1` for all other failures (HTTP 4xx/5xx, decode errors, bad configuration); the GitHub Actions job fails in this case.

## API Endpoints
All endpoints are served beneath `/api`.

- `POST /api/state`
  Upload a new snapshot from the local sender. The body must be an object containing `timestamp` (ISO-8601 string) and `data` (the full values payload). The request must include an `X-Signature` header with the HMAC-SHA256 signature of the JSON body using the shared API key.
- `GET /api/state`
  Returns the latest snapshot. Pass `?flat=true` to receive a flattened dictionary where nested objects are expanded using `.` and `[index]` notation. Flattened responses are paginated by default: use `limit` (defaults to 500) to control page size, `cursor` to continue from the previous page, and `limit=0` if you explicitly need the full flattened payload.
- `GET /api/groups`
  Lists schema-defined groups (from `variables.json`) and any additional groups inferred from the live dataset (based on prefixes and nested objects).
- `GET /api/status`
  Returns metadata about the service: telemetry freshness, uptime, and build identifiers. Always responds with HTTP 200; consult the `status` field (`ok`/`stale`) to determine health.
- `GET /api/health`
  Returns a lightweight health summary, including telemetry freshness (`last_updated`) and command queue counts. Responds with HTTP 503 when telemetry is stale beyond `HEALTH_MAX_AGE_SECONDS`.
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

### Running the sender locally

1. Install Python 3.11+ and (optionally) create a virtual environment.
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate
   pip install -r requirements.txt
   ```
   > If you are only interested in the client, install `requests` instead of the full requirements list.
2. Copy the default config and set your credentials and endpoints:
   ```powershell
   Copy-Item client\config.example.json client\config.json
   ```
   Edit `client\config.json` so that `API_URL`, `COMMAND_URL`, `API_KEY`, `COMMAND_TOKEN`, and `GAME_URL` point to your Render deployment and local webserver.
3. Start the sender from the repository root:
   ```powershell
   python client\sender.py
   ```
   The process prints `API SYNC OK` on successful telemetry uploads and logs command execution summaries such as `CMD[abc123] OK Start condenser pump`. Errors are retried after `POLL_INTERVAL` seconds.

`client/config.json` fields:
> Copy `client/config.example.json` to `client/config.json` and fill in your Render URL, API key, and command token before running the sender.

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

## Custom GPT setup
1. Edit `GPT/action.yaml` and replace the placeholder server URL (`https://your-render-service.onrender.com/api`) with your deployed hostname (for local testing use `http://localhost:8000/api`).
2. Optional: drop additional reference material into `GPT/documentation` so the assistant can cite it.
3. Create a zip of the `GPT` directory:
   ```powershell
   Compress-Archive -Path GPT\* -DestinationPath nucleares-gpt.zip -Force
   ```
   > On macOS/Linux use `zip -r nucleares-gpt.zip GPT`.
4. In ChatGPT (Plus / Team), open **Explore GPTs → Create** and switch to the **Configure** tab.
5. Under **Actions**, choose **Upload action** and select `nucleares-gpt.zip` (or directly upload `GPT/action.yaml`).
6. When prompted for authentication, add a secret named `CommandToken` with the same value you configured in the API (`COMMAND_TOKEN`). This ensures command endpoints require the shared header `X-Command-Token`.
7. Save the GPT and use the built-in tester to call `/groups` or `/state` with a small `limit` to confirm the connection before sharing it with others.
8. Update the GPT description/instructions so human operators know they must approve real-world control actions manually.

## Verify the end-to-end setup
- With the sender running, hit `GET /api/state` (optionally `?flat=true&limit=5`) and confirm the response shows `last_updated` and a handful of variables.
- Trigger a test command through the GPT or a manual `POST /api/commands` and watch the sender log (`CMD[...] OK/FAIL`) to make sure the command loop is functioning.
- If the GPT reports pagination warnings, supply `limit`/`cursor` parameters as documented above.

## Privacy
This API is designed **only for simulation/gameplay purposes**.

- **What data is collected:**
  - Plant status variables exposed by the Nucleares game (e.g., temperatures, pressures, valve states).
  - A timestamp of when the data was last updated.
  - Execution summaries for issued commands.
- **What data is not collected:**
  - API keys, command tokens, and other credentials stay in Render environment variables or local config files and are never exposed via the public API.
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
