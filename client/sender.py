import json
import hmac
import time
import socket
import hashlib
import requests
from typing import Any, Dict, Iterable, List, Set
from urllib.parse import urljoin
from datetime import datetime, timezone

# Load config
with open('client/config.json') as f:
    config = json.load(f)

API_URL = config['API_URL']
API_KEY = config['API_KEY'].encode()

# Game webserver endpoints
_game_base = config['GAME_URL'].rstrip('/') + '/'
GAME_STATE_URL = urljoin(_game_base, '?Variable=WEBSERVER_BATCH_GET&value=*')
GAME_COMMAND_URL = config.get('GAME_COMMAND_URL', _game_base)
POLL_INTERVAL = config.get('POLL_INTERVAL', 5)

# Command API configuration
COMMAND_URL = config.get('COMMAND_URL')
COMMAND_TOKEN = config.get('COMMAND_TOKEN')
COMMAND_POLL_LIMIT = config.get('COMMAND_POLL_LIMIT', 3)
COMMAND_TIMEOUT = config.get('COMMAND_TIMEOUT', 10)
CLIENT_ID = config.get('CLIENT_ID') or socket.gethostname() or 'sender'


class CommandExecutor:
    def __init__(
        self,
        command_url: str,
        command_token: str,
        game_command_url: str,
        client_id: str,
        poll_limit: int,
        timeout: int,
    ) -> None:
        self.command_url = command_url.rstrip('/')
        self.command_token = command_token
        self.game_command_url = game_command_url.rstrip('/') + '/'
        self.client_id = client_id
        self.poll_limit = max(1, min(50, poll_limit))
        self.timeout = timeout
        self.allowed_post_vars: Set[str] | None = None

    def update_catalog(self, catalog: Dict[str, Any]) -> None:
        """Update the set of writable variables exposed by the webserver."""
        post_section = catalog.get('post') or catalog.get('POST')
        allowed: Set[str] = set()
        if isinstance(post_section, dict):
            post_section = post_section.values()
        if isinstance(post_section, Iterable) and not isinstance(post_section, (str, bytes)):
            for entry in post_section:
                if isinstance(entry, str):
                    allowed.add(entry.upper())
                elif isinstance(entry, dict):
                    variable = entry.get('variable') or entry.get('name')
                    if isinstance(variable, str):
                        allowed.add(variable.upper())
        if allowed:
            self.allowed_post_vars = allowed

    def poll_and_execute(self) -> None:
        """Fetch pending commands and execute them sequentially."""
        try:
            response = requests.get(
                f"{self.command_url}/next",
                headers={'X-Command-Token': self.command_token},
                params={'limit': self.poll_limit, 'client_id': self.client_id},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception as exc:
            print('CMD POLL FAIL:', exc)
            return

        try:
            payload = response.json()
        except ValueError:
            print('CMD POLL FAIL: Invalid JSON from command API')
            return

        commands = payload.get('commands') or []
        for command in commands:
            self._process_command(command)

    def _process_command(self, command: Dict[str, Any]) -> None:
        command_id = command.get('id')
        prefix = f"CMD[{str(command_id)[:6]}]"
        tasks: List[Dict[str, Any]] = command.get('tasks') or []
        if not tasks:
            self._submit_result(command_id, 'failed', 'No tasks provided', {'error': 'Missing tasks'})
            print(f"{prefix} FAIL missing tasks")
            return

        detail_lines: List[str] = []
        try:
            for idx, task in enumerate(tasks, start=1):
                detail_lines.append(self._execute_task(idx, task))
            detail = '; '.join(detail_lines) if detail_lines else 'Executed with no details'
            self._submit_result(
                command_id,
                'completed',
                detail,
                {
                    'steps': detail_lines,
                    'purpose': command.get('purpose'),
                    'metadata': command.get('metadata'),
                },
            )
            summary = command.get('purpose') or 'completed'
            print(f"{prefix} OK {summary}")
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            self._submit_result(
                command_id,
                'failed',
                detail,
                {
                    'error': detail,
                    'steps': detail_lines,
                },
            )
            print(f"{prefix} FAIL {detail}")

    def _execute_task(self, idx: int, task: Dict[str, Any]) -> str:
        operation = (task.get('operation') or 'set').lower()
        variable = task.get('variable')
        if not variable:
            raise ValueError(f'Task {idx} missing variable name')

        value = task.get('value')
        if operation == 'set':
            self._send_game_command(variable, value)
            return f"{idx}: set {variable} -> {value}"

        if operation == 'pulse':
            reset_value = task.get('reset_value')
            if reset_value is None:
                raise ValueError(f'Task {idx} missing reset_value for pulse operation')
            hold_seconds = float(task.get('hold_seconds', 1.0))
            self._send_game_command(variable, value)
            if hold_seconds > 0:
                time.sleep(hold_seconds)
            self._send_game_command(variable, reset_value)
            return f"{idx}: pulse {variable} {value}->{reset_value} ({hold_seconds}s)"

        raise ValueError(f"Task {idx} has unsupported operation '{operation}'")

    def _send_game_command(self, variable: str, value: Any) -> None:
        if self.allowed_post_vars and variable.upper() not in self.allowed_post_vars:
            raise ValueError(f"Unsupported control variable '{variable}'")

        formatted_value = self._format_value(value)
        response = requests.post(
            self.game_command_url,
            params={'Variable': variable, 'value': formatted_value},
            timeout=self.timeout,
        )
        response.raise_for_status()

        # Attempt to surface explicit webserver errors if returned
        try:
            payload = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict) and payload.get('status') not in (None, 'OK', 'Success'):
            raise RuntimeError(f"Webserver response: {payload}")

    @staticmethod
    def _format_value(value: Any) -> str:
        if isinstance(value, bool):
            return '1' if value else '0'
        if value is None:
            return ''
        return str(value)

    def _submit_result(self, command_id: Any, status: str, detail: str, outputs: Dict[str, Any]) -> None:
        if not command_id:
            return
        try:
            response = requests.post(
                f"{self.command_url}/{command_id}/result",
                json={'status': status, 'detail': detail, 'outputs': outputs},
                headers={'X-Command-Token': self.command_token},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception as exc:
            print('CMD REPORT FAIL:', exc)


def deep_parse(value):
    """Recursively parse JSON-encoded strings into Python objects."""
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except Exception:
            return value
        return deep_parse(decoded)

    if isinstance(value, dict):
        return {k: deep_parse(v) for k, v in value.items()}

    if isinstance(value, list):
        return [deep_parse(item) for item in value]

    return value


def fetch_variable_catalog(command_base: str, timeout: int) -> Dict[str, Any]:
    try:
        response = requests.get(
            command_base.rstrip('/') + '/',
            params={'Variable': 'WEBSERVER_LIST_VARIABLES_JSON'},
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            return data
    except Exception as exc:
        print('CMD CATALOG FAIL:', exc)
    return {}


def inject_catalog(target: Dict[str, Any], catalog: Dict[str, Any]) -> None:
    if not catalog:
        return
    try:
        meta = target.setdefault('_meta', {})
        meta['webserver_catalog'] = catalog
    except Exception:
        target['_webserver_catalog'] = catalog


executor = None
if COMMAND_URL and COMMAND_TOKEN:
    executor = CommandExecutor(
        COMMAND_URL,
        COMMAND_TOKEN,
        GAME_COMMAND_URL,
        CLIENT_ID,
        COMMAND_POLL_LIMIT,
        COMMAND_TIMEOUT,
    )


while True:
    print('API SYNC ', end='')

    try:
        resp = requests.get(GAME_STATE_URL, timeout=10)
        status = resp.status_code
        if status >= 400:
            print(f'WARN[{status}] ', end='')

        try:
            raw_data = resp.json()
        except ValueError as exc:
            snippet = resp.text[:200].replace(chr(10), ' ').replace(chr(13), ' ')
            raise ValueError(f'Unexpected payload (status {status}): {snippet}') from exc
        game_values = raw_data.get('values', {})
        if not isinstance(game_values, dict):
            raise ValueError('Unexpected payload structure from game webserver')

        game_data = deep_parse(game_values)
        catalog = fetch_variable_catalog(GAME_COMMAND_URL, COMMAND_TIMEOUT)
        if catalog:
            inject_catalog(game_data, catalog)
            if executor:
                executor.update_catalog(catalog)

        payload = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'data': game_data,
        }

        body = json.dumps(payload, separators=(',', ':')).encode()
        signature = hmac.new(API_KEY, body, hashlib.sha256).hexdigest()
        headers = {'X-Signature': signature, 'Content-Type': 'application/json'}

        response = requests.post(API_URL, data=body, headers=headers, timeout=10)
        response.raise_for_status()
        print('OK')

    except Exception as e:
        print('FAIL:', e)

    if executor:
        executor.poll_and_execute()

    time.sleep(POLL_INTERVAL)
