#!/usr/bin/env python3
"""Offline version, changelog, package, and annotated-tag consistency checks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

CORE = r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
NUMERIC_ID = r"(?:0|[1-9]\d*)"
NON_NUMERIC_ID = r"(?:[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
PRE_ID = rf"(?:{NUMERIC_ID}|{NON_NUMERIC_ID})"
SEMVER_RE = re.compile(
    rf"^{CORE}(?:-{PRE_ID}(?:\.{PRE_ID})*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
CHANGELOG_HEADING_RE = re.compile(r"^## \[([^\]]+)\](?:[ \t].*)?$", re.MULTILINE)


def is_semver(value: str) -> bool:
    return SEMVER_RE.fullmatch(value) is not None


def changelog_versions(text: str) -> list[str]:
    return CHANGELOG_HEADING_RE.findall(text)


def validate_changelog(text: str, version: str) -> None:
    if not text.startswith("# Changelog"):
        raise ValueError("CHANGELOG.md must start with the Changelog title")
    entries = changelog_versions(text)
    if entries.count("Unreleased") != 1:
        raise ValueError("CHANGELOG.md must have exactly one [Unreleased] section")
    release_entries = [entry for entry in entries if entry != "Unreleased"]
    if len(release_entries) != len(set(release_entries)):
        raise ValueError("CHANGELOG.md contains duplicate version sections")
    if entries.count(version) != 1:
        raise ValueError(f"CHANGELOG.md must have exactly one [{version}] section")
    invalid_entries = [entry for entry in release_entries if not is_semver(entry)]
    if invalid_entries:
        raise ValueError("CHANGELOG.md has invalid SemVer section(s): " + ", ".join(invalid_entries))


def validate_package_versions(version: str, package: dict, package_lock: dict) -> None:
    if package.get("version") != version:
        raise ValueError("frontend/package.json version must equal root VERSION")
    lock_versions = (
        package_lock.get("version"),
        package_lock.get("packages", {}).get("", {}).get("version"),
    )
    if any(lock_version != version for lock_version in lock_versions):
        raise ValueError("frontend/package-lock.json versions must equal root VERSION")


def ensure_candidate_tag_unused(version: str, tags: list[str]) -> None:
    candidate_tag = f"v{version}"
    if candidate_tag in tags:
        raise ValueError(f"release candidate tag already exists: {candidate_tag}")


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def validate(root: Path, release_candidate: bool = False) -> list[str]:
    version_path = root / "VERSION"
    changelog_path = root / "CHANGELOG.md"
    package_path = root / "frontend" / "package.json"
    lock_path = root / "frontend" / "package-lock.json"
    policy_path = root / "docs" / "RELEASE_POLICY.md"
    rollback_path = root / "docs" / "ROLLBACK_RUNBOOK.md"

    for path in (version_path, changelog_path, package_path, lock_path, policy_path, rollback_path):
        if not path.is_file():
            raise ValueError(f"required file is missing: {path.relative_to(root)}")

    version = version_path.read_text(encoding="utf-8").strip()
    if not is_semver(version):
        raise ValueError("VERSION must contain one valid SemVer value without a leading v")

    package = json.loads(package_path.read_text(encoding="utf-8"))
    package_lock = json.loads(lock_path.read_text(encoding="utf-8"))
    validate_package_versions(version, package, package_lock)

    changelog = changelog_path.read_text(encoding="utf-8")
    validate_changelog(changelog, version)

    for path, required in (
        (policy_path, ("## Version source and scheme", "## Release path and responsibilities", "## Release acceptance checklist")),
        (rollback_path, ("## Before merge", "## After merge, before deployment", "## After application deployment", "## Database and user data")),
    ):
        body = path.read_text(encoding="utf-8")
        missing = [heading for heading in required if heading not in body]
        if missing:
            raise ValueError(f"{path.relative_to(root)} is missing required section(s): " + ", ".join(missing))

    tag_rows = git(
        root,
        "for-each-ref",
        "--format=%(refname:strip=2)\t%(objecttype)",
        "refs/tags/v*",
    )
    tags = []
    for row in filter(None, tag_rows.splitlines()):
        tag, object_type = row.split("\t", 1)
        if not is_semver(tag[1:]):
            raise ValueError(f"release tag has invalid SemVer: {tag}")
        if object_type != "tag":
            raise ValueError(f"release tag must be annotated: {tag}")
        commit = git(root, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
        tagged_version = git(root, "show", f"{commit}:VERSION")
        if tagged_version != tag[1:]:
            raise ValueError(f"{tag} points to a commit whose VERSION is {tagged_version}")
        tagged_changelog = git(root, "show", f"{commit}:CHANGELOG.md")
        if tag[1:] not in changelog_versions(tagged_changelog):
            raise ValueError(f"{tag} has no matching CHANGELOG.md section at its target commit")
        tags.append(tag)

    checks = [
        f"SemVer format: {version}",
        "frontend package and lock metadata match VERSION",
        "CHANGELOG sections are present and unique",
        f"annotated release tags checked: {len(tags)}",
        "release and rollback policy sections are present",
    ]
    if release_candidate:
        ensure_candidate_tag_unused(version, tags)
        if git(root, "status", "--porcelain"):
            raise ValueError("release readiness requires a clean checkout")
        checks.append(f"candidate tag is unused: v{version}")
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release-candidate",
        action="store_true",
        help="also require a clean checkout and an unused v-prefixed tag; does not publish",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        checks = validate(root, release_candidate=args.release_candidate)
    except (OSError, json.JSONDecodeError, RuntimeError, ValueError) as error:
        print(f"VERSION_GOVERNANCE_FAIL: {error}", file=sys.stderr)
        return 1
    for check in checks:
        print(f"PASS: {check}")
    if args.release_candidate:
        print("READINESS_ONLY: no tag, Release, deployment, or database operation was performed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
