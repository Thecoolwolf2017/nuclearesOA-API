# Smoke Test Notes

This document captures operational details for `tests/smoke_test.py` so future runs behave as expected.

## Environment variables

- `NUCLEARES_API_BASE` (required): Base URL for the public API, without trailing slash.
- `NUCLEARES_COMMAND_TOKEN` (optional): Secret token for `/api/commands/next`. If omitted, the smoke test only checks anonymous access and warns when authentication fails.

## Exit codes

- `0` — All endpoints responded with healthy JSON. Workflow passes, badges show `online / pass`.
- `2` — API unreachable or `/health` reported stale telemetry. Workflow succeeds so automation continues, but the smoke badges flip to `offline / fail`.
- `1` — Any other failure (HTTP 4xx/5xx, decode errors, bad configuration). Workflow fails and badges remain `fail`.

## CI workflow behaviour

The GitHub Actions smoke job captures the exit code. Exit `2` is treated as a soft, offline state, while any other non-zero exit terminates the job. Availability and status badges are always updated to reflect the latest run.
