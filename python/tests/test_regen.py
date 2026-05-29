"""Regen-pipeline tests.

Verifies:
1. ``scripts/regen_model.py --check --skip-fetch`` is idempotent against
   the committed artefacts (would catch a generated-file edit that drifted
   from the templates, or a template edit that wasn't re-run).
2. A one-byte mutation of a generated file makes ``--check`` exit nonzero.
"""

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "regen_model.py"
GENERATED_FILE = REPO_ROOT / "python" / "src" / "yente_client" / "entities" / "_generated.py"


def _run_check() -> subprocess.CompletedProcess[str]:
    """Invoke regen_model.py --check --skip-fetch with the current interpreter.

    Using ``sys.executable`` rather than a hardcoded venv binary keeps this
    test portable across local dev (venv) and CI (system Python).
    """
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--skip-fetch"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def test_regen_check_idempotent() -> None:
    result = _run_check()
    assert result.returncode == 0, (
        f"--check failed against committed artefacts:\n"
        f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )


def test_regen_check_detects_modified_generated_file(tmp_path: Path) -> None:
    """If a generated file gets edited by hand, --check should catch it."""
    backup = tmp_path / "generated_backup.py"
    shutil.copy(GENERATED_FILE, backup)
    try:
        GENERATED_FILE.write_text(GENERATED_FILE.read_text() + "\n# intentional drift\n")
        result = _run_check()
        assert result.returncode != 0, "--check should fail when a generated file is modified"
        assert "differs" in result.stderr or "differs" in result.stdout
    finally:
        shutil.copy(backup, GENERATED_FILE)
