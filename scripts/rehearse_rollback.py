#!/usr/bin/env python3
"""Rehearse a history-preserving revert in a disposable local repository clone."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile


def run(command: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if check and result.returncode:
        raise RuntimeError(f"{command!r} failed: {result.stderr.strip()}")
    return result


def rehearse(repository: Path) -> list[str]:
    repository = repository.resolve()
    with tempfile.TemporaryDirectory(prefix="homework-grading-rollback-") as temporary:
        clone = Path(temporary) / "repo"
        run(["git", "clone", "--quiet", "--no-hardlinks", str(repository), str(clone)])
        run(["git", "switch", "--quiet", "-c", "rollback-rehearsal"], cwd=clone)
        run(["git", "config", "user.name", "Rollback rehearsal"], cwd=clone)
        run(["git", "config", "user.email", "rollback-rehearsal@example.invalid"], cwd=clone)

        starting_commit = run(["git", "rev-parse", "HEAD"], cwd=clone).stdout.strip()
        synthetic_file = clone / "rollback-rehearsal.txt"
        synthetic_file.write_text("Synthetic rollback rehearsal only.\n", encoding="utf-8")
        run(["git", "add", "--", synthetic_file.name], cwd=clone)
        run(["git", "commit", "--quiet", "-m", "test: synthetic rollback rehearsal change"], cwd=clone)
        change_commit = run(["git", "rev-parse", "HEAD"], cwd=clone).stdout.strip()

        run(["git", "revert", "--quiet", "--no-edit", change_commit], cwd=clone)
        revert_commit = run(["git", "rev-parse", "HEAD"], cwd=clone).stdout.strip()
        if run(["git", "rev-parse", "HEAD^"], cwd=clone).stdout.strip() != change_commit:
            raise RuntimeError("revert commit did not preserve the synthetic change commit in history")
        run(["git", "diff", "--exit-code", starting_commit, revert_commit], cwd=clone)
        if run(["git", "status", "--porcelain"], cwd=clone).stdout.strip():
            raise RuntimeError("rehearsal working tree is not clean after the revert")

        version_check = run(
            [sys.executable, "scripts/check_version_governance.py"],
            cwd=clone,
        )
        return [
            f"starting commit: {starting_commit}",
            f"synthetic change commit: {change_commit}",
            f"synthetic revert commit: {revert_commit}",
            "revert commit retained the original change in history",
            "reverted tree matches the starting commit and is clean",
            "version-governance checks passed after the revert",
            *[line.removeprefix("PASS: ") for line in version_check.stdout.splitlines() if line.startswith("PASS:")],
        ]


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    try:
        results = rehearse(repository)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"ROLLBACK_REHEARSAL_FAIL: {error}", file=sys.stderr)
        return 1
    for result in results:
        print(f"PASS: {result}")
    print("LOCAL_ONLY: no remote, production, database, student-data, or deployment operation was performed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
