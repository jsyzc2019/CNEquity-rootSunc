"""A partially completed Windows suite must not turn a failing run green."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


@pytest.mark.skipif(shutil.which("bash") is None, reason="CI invokes pytest with bash")
@pytest.mark.parametrize("exit_status", [0, 1, 2, 3, 4, 5, 130])
def test_windows_ci_preserves_pytest_exit_status(tmp_path, exit_status):
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    step = next(s for s in workflow["jobs"]["test-windows"]["steps"] if s.get("name") == "Test")
    # Interruptions and internal errors can follow successful tests. Execute
    # the actual workflow step with that output and exit status, without
    # starting another test suite or relying on a Windows process pool.
    fake_pytest = f"pytest() {{ printf '1 passed\\n'; return {exit_status}; }}\n"

    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", fake_pytest + step["run"]],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == exit_status, result.stdout + result.stderr
