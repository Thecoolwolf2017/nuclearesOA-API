import os
import unittest

from typing import Any, Dict, Optional, Tuple


# Allow importing main.py in tests without real secrets.
os.environ.setdefault("ALLOW_INSECURE_DEFAULTS", "1")

import main  # noqa: E402
from pydantic import ValidationError  # noqa: E402


class TestCoreHelpers(unittest.TestCase):
    def test_flatten_state(self) -> None:
        payload = {
            "A": {"B": 1, "C": {"D": 2}},
            "E": [{"F": 3}, 4],
            "G": 5,
        }

        flat = main._flatten_state(payload)

        self.assertEqual(flat["A.B"], 1)
        self.assertEqual(flat["A.C.D"], 2)
        self.assertEqual(flat["E[0].F"], 3)
        self.assertEqual(flat["E[1]"], 4)
        self.assertEqual(flat["G"], 5)

    def test_infer_dynamic_groups(self) -> None:
        original = main.current_state
        try:
            main.current_state = {
                "foo_bar": 1,
                "Baz": {"nested": True},
            }
            inferred = main._infer_dynamic_groups()
        finally:
            main.current_state = original

        self.assertIn("FOO", inferred)
        self.assertIn("BAZ", inferred)

    def test_command_task_validation(self) -> None:
        task = main.CommandTask(operation="SET", variable="VALVE_A", value=True, hold_seconds=5)
        self.assertEqual(task.operation, "set")
        self.assertEqual(task.hold_seconds, 0.0)

        with self.assertRaises(ValidationError):
            main.CommandTask(operation="pulse", variable="VALVE_A", value=1)

    def test_translation_oneof(self) -> None:
        found = _find_oneof_entry()
        if found is None:
            self.skipTest("No oneOf const/description found in schema.")

        group, var, const_value, description = found
        translated = main._translate_value(group, var, const_value)
        self.assertEqual(translated, description)


def _find_oneof_entry() -> Optional[Tuple[str, str, Any, str]]:
    for group, group_schema in main.SCHEMA.items():
        props: Dict[str, Any] = group_schema.get("properties", {})
        for var, var_schema in props.items():
            one_of = var_schema.get("oneOf")
            if not isinstance(one_of, list):
                continue
            for entry in one_of:
                if "const" in entry and "description" in entry:
                    return group, var, entry["const"], entry["description"]
    return None


if __name__ == "__main__":
    unittest.main()
