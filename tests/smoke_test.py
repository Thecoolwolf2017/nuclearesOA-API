from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any

import requests
from requests import RequestException
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout as RequestsTimeout


class SmokeTestError(Exception):
    """Raised when the smoke test encounters a failure."""


class SmokeTestOffline(SmokeTestError):
    """Raised when the smoke test should be skipped due to offline execution."""


@dataclass
class SmokeTestConfig:
    base_url: str
    command_token: str | None = None

    @classmethod
    def from_env(cls) -> "SmokeTestConfig":
        base_url = os.getenv("NUCLEARES_API_BASE")
        if not base_url:
            raise SmokeTestError("Environment variable NUCLEARES_API_BASE is required.")
        base_url = base_url.rstrip("/")

        token = os.getenv("NUCLEARES_COMMAND_TOKEN")
        return cls(base_url=base_url, command_token=token)


def request_json(method: str, url: str, *, headers: dict[str, str] | None = None, timeout: float = 10.0) -> Any:
    try:
        response = requests.request(method, url, headers=headers, timeout=timeout)
    except (RequestsConnectionError, RequestsTimeout) as exc:
        raise SmokeTestOffline(f"Network request failed while contacting {url}: {exc}") from exc
    except RequestException as exc:
        raise SmokeTestError(f"{method} {url} failed before receiving a response: {exc}") from exc
    if response.status_code != 200:
        raise SmokeTestError(f"{method} {url} -> {response.status_code} {response.text}")
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise SmokeTestError(f"{method} {url} returned non-JSON body") from exc


def running_in_ci() -> bool:
    """Best-effort detection for CI environments."""
    ci = os.getenv("CI")
    gh = os.getenv("GITHUB_ACTIONS")
    return any(value for value in (ci, gh))


def check_groups(config: SmokeTestConfig) -> None:
    payload = request_json("GET", f"{config.base_url}/groups")
    if not isinstance(payload, dict) or "schema_groups" not in payload:
        raise SmokeTestError("Unexpected response structure from /groups")


def check_health(config: SmokeTestConfig) -> None:
    payload = request_json("GET", f"{config.base_url}/health")
    if not isinstance(payload, dict):
        raise SmokeTestError("Unexpected response from /health")
    status = payload.get("status")
    telemetry = payload.get("telemetry", {})
    if status != "ok":
        age = telemetry.get("seconds_since_update")
        raise SmokeTestError(f"/health reported status={status} (age={age})")
    if not telemetry.get("fresh"):
        raise SmokeTestError("/health indicates telemetry is stale")


def check_state(config: SmokeTestConfig) -> None:
    payload = request_json("GET", f"{config.base_url}/state?flat=true&limit=1")
    if not isinstance(payload, dict) or "data" not in payload:
        raise SmokeTestError("Unexpected response structure from /state")
    data = payload["data"]
    if not isinstance(data, dict):
        raise SmokeTestError("/state payload returned non-dict data")


def check_commands(config: SmokeTestConfig) -> None:
    headers = {}
    if config.command_token:
        headers["X-Command-Token"] = config.command_token
    try:
        payload = request_json("GET", f"{config.base_url}/commands/next?limit=1&client_id=smoke-test", headers=headers)
    except SmokeTestError as exc:
        if "401" in str(exc) or "403" in str(exc):
            raise SmokeTestError("Command endpoint rejected authentication; set NUCLEARES_COMMAND_TOKEN.") from exc
        raise
    if not isinstance(payload, dict) or "commands" not in payload:
        raise SmokeTestError("Unexpected response structure from /commands/next")


def main() -> None:
    config = SmokeTestConfig.from_env()
    check_health(config)
    check_groups(config)
    check_state(config)
    check_commands(config)
    print("Smoke test passed.")


if __name__ == "__main__":
    try:
        main()
    except SmokeTestOffline as exc:
        if running_in_ci():
            print(f"Smoke test failed: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        print(f"Smoke test skipped: {exc}", file=sys.stderr)
        raise SystemExit(0) from exc
    except SmokeTestError as exc:
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
