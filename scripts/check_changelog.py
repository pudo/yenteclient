#!/usr/bin/env python3
"""Advisory check that CHANGELOG.md was touched on PRs with code changes.

Used as a CI step; emits a GitHub Actions warning when:

- The PR's diff range touches code (anything under ``python/src/`` or
  ``scripts/`` or workflow files), AND
- ``CHANGELOG.md`` was NOT touched in the same diff range, AND
- The PR body doesn't contain ``[skip changelog]``.

This is intentionally non-blocking — exits 0 either way. The warning
surfaces in the PR's Files Changed view and the workflow summary; the
human reviewer decides whether to nudge.

Inputs (from the workflow):
- BASE_SHA: the merge-base commit the PR is being compared against.
- HEAD_SHA: the PR head commit.
- PR_BODY: full body text of the PR (passed via env var).
"""

from __future__ import annotations

import os
import subprocess
import sys

CODE_PREFIXES = ("python/src/", "scripts/", ".github/workflows/")
SKIP_TAG = "[skip changelog]"


def _changed_files(base: str, head: str) -> list[str]:
    """Return the list of files changed between ``base`` and ``head``."""
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    base = os.environ.get("BASE_SHA")
    head = os.environ.get("HEAD_SHA")
    if not base or not head:
        # Not running in a PR context (push to main, scheduled, etc.) — nothing to check.
        return 0

    pr_body = os.environ.get("PR_BODY", "")
    if SKIP_TAG in pr_body:
        print(f"check_changelog: '{SKIP_TAG}' in PR body — skipping.")
        return 0

    changed = _changed_files(base, head)
    touches_code = any(f.startswith(CODE_PREFIXES) for f in changed)
    touches_changelog = "CHANGELOG.md" in changed

    if touches_code and not touches_changelog:
        # GitHub Actions warning annotation — shows up in the PR check summary.
        print(
            "::warning file=CHANGELOG.md::Code changed but CHANGELOG.md was not "
            "touched. Add an entry under [Unreleased] or include "
            f"'{SKIP_TAG}' in the PR body if the change is genuinely "
            "user-invisible (refactors, internal docs, CI tweaks).",
        )
    elif touches_code and touches_changelog:
        print("check_changelog: code + changelog both touched. OK.")
    else:
        print("check_changelog: no code changes in scope. OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
