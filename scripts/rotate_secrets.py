#!/usr/bin/env python3
"""Rotate local API secrets by updating a .env file in-place.

Usage:
    python scripts/rotate_secrets.py

By default this script writes new `API_KEY` and `COMMAND_TOKEN` values to `.env`
in the repository root. Adjust the path with `--env-path` or override the number
of random bytes with `--api-bytes` / `--command-bytes`.
"""

from __future__ import annotations

import argparse
import secrets
from pathlib import Path
from typing import Dict, Iterable

DEFAULT_BYTES = 32  # -> 64 hex characters


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rotate API_KEY and COMMAND_TOKEN values in a .env file.")
    parser.add_argument(
        "--env-path",
        type=Path,
        default=Path(".env"),
        help="Path to the dotenv file to update (default: ./ .env)",
    )
    parser.add_argument(
        "--api-bytes",
        type=int,
        default=DEFAULT_BYTES,
        help=f"Number of random bytes for API_KEY (default: {DEFAULT_BYTES})",
    )
    parser.add_argument(
        "--command-bytes",
        type=int,
        default=DEFAULT_BYTES,
        help=f"Number of random bytes for COMMAND_TOKEN (default: {DEFAULT_BYTES})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and display secrets without writing to the .env file.",
    )
    return parser.parse_args()


def generate_secret(byte_count: int) -> str:
    if byte_count <= 0:
        raise ValueError("byte count must be positive")
    return secrets.token_hex(byte_count)


def update_dotenv(path: Path, updates: Dict[str, str]) -> None:
    existing_lines: list[str] = []
    seen: Dict[str, bool] = {key: False for key in updates}

    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                existing_lines.append(raw_line)
                continue
            key, _, value = raw_line.partition("=")
            key_stripped = key.strip()
            if key_stripped in updates:
                existing_lines.append(f"{key_stripped}={updates[key_stripped]}")
                seen[key_stripped] = True
            else:
                existing_lines.append(raw_line)
    for key, value in updates.items():
        if not seen.get(key, False):
            existing_lines.append(f"{key}={value}")

    path.write_text("\n".join(existing_lines) + "\n", encoding="utf-8")


def format_summary(updates: Dict[str, str], target: Path) -> str:
    rows = [f"Wrote secrets to {target.resolve()}:"]
    for key, value in updates.items():
        rows.append(f"  {key}={value}")
    rows.append("Remember to sync these values to your hosting provider (e.g. Render).")
    return "\n".join(rows)


def main() -> None:
    args = parse_args()

    updates = {
        "API_KEY": generate_secret(args.api_bytes),
        "COMMAND_TOKEN": generate_secret(args.command_bytes),
    }

    if args.dry_run:
        print("Dry run: generated secrets but did not write to disk:")
        for key, value in updates.items():
            print(f"  {key}={value}")
        return

    args.env_path.parent.mkdir(parents=True, exist_ok=True)
    update_dotenv(args.env_path, updates)
    print(format_summary(updates, args.env_path))


if __name__ == "__main__":
    main()
