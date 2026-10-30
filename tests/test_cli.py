from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "main.py"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-B", str(MAIN), "--cli", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=90,
        check=False,
    )


class CliTests(unittest.TestCase):
    def test_indefinite_integral(self) -> None:
        completed = run_cli("x^2")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("x³/3", completed.stdout)
        self.assertIn("求导校验通过", completed.stdout)

    def test_definite_integral(self) -> None:
        completed = run_cli("x^2", "--bounds", "0", "1")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("∫₀¹ x² dx = 1/3", completed.stdout)
        self.assertIn("数值积分校验通过", completed.stdout)

    def test_json_output(self) -> None:
        completed = run_cli("sin(x)", "--bounds", "0", "pi", "--json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["kind"], "definite")
        self.assertEqual(payload["value"], "2")
        self.assertEqual(payload["variable"], "x")
        self.assertIn("steps", payload)

    def test_error_exit_code(self) -> None:
        completed = run_cli("x**")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("错误", completed.stdout)

    def test_json_error(self) -> None:
        completed = run_cli("x**", "--json")
        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])
        self.assertIn("error", payload)

    def test_no_steps(self) -> None:
        completed = run_cli("x", "--bounds", "0", "1", "--no-steps")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("【推导步骤】", completed.stdout)

    def test_help(self) -> None:
        completed = run_cli("--help")
        self.assertEqual(completed.returncode, 0)
        self.assertIn("积分求解器", completed.stdout)

    def test_version(self) -> None:
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        completed = subprocess.run(
            [sys.executable, "-B", str(MAIN), "--version"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertIn("1.0.0", completed.stdout)


if __name__ == "__main__":
    unittest.main()
