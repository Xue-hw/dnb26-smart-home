import subprocess
import sys
from pathlib import Path


def test_check_environment_runs_as_direct_script() -> None:
    project_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/check_environment.py"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "python:" in result.stdout
    assert "model:" in result.stdout
