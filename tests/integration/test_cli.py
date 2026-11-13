from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class CliTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        return subprocess.run(
            [sys.executable, "-m", "trovis_manager.cli", *arguments],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )

    def test_identify(self) -> None:
        result = self.run_cli("identify")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SAMSON TROVIS 5573-1", result.stdout)
        self.assertIn("Firmware: 03.09.00", result.stdout)

    def test_backup_and_validate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backup.json"
            backup = self.run_cli("backup", str(path))
            self.assertEqual(backup.returncode, 0, backup.stderr)
            validate = self.run_cli("validate", str(path))
            self.assertEqual(validate.returncode, 0, validate.stderr)
            self.assertIn("valid snapshot", validate.stdout)

    def test_hardware_mode_requires_explicit_real_transport(self) -> None:
        missing = self.run_cli("hardware", "identify")
        self.assertEqual(missing.returncode, 2)
        self.assertIn("--transport", missing.stderr)
        mock = self.run_cli("hardware", "--transport", "mock", "identify")
        self.assertEqual(mock.returncode, 2)
        self.assertIn("invalid choice", mock.stderr)
        no_host = self.run_cli("hardware", "--transport", "tcp", "identify")
        self.assertEqual(no_host.returncode, 2)
        self.assertIn("--host is required", no_host.stderr)
