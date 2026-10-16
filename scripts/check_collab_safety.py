from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "dist", "build", "coverage", "__pycache__", ".pytest_cache"}
FORBIDDEN_NAMES = {".env", "project.config.json", "project.private.config.json", "settings.local.json"}
FORBIDDEN_DIRS = {".claude", ".localdemo", "uploads", "数据", "证据", "输出", "总控任务", "历史", "资料"}
EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@(?!example\.com\b|example\.invalid\b|test\.invalid\b|localhost\b)[A-Z0-9.-]+\.[A-Z]{2,}\b")
MOBILE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
TOKEN_PATTERNS = (
    re.compile(r"(?i)\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\bxox[baprs]-[A-Za-z0-9-]{12,}\b"),
)
ASSIGNMENT = re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|secret|password|passwd)\s*[:=]\s*['\"]([^'\"]{8,})['\"]")
SAFE_MARKERS = ("test-only-", "test-", "example", "placeholder", "your_", "your-", "change-me", "<", "entered-value")
LOCAL_PATH = re.compile(r"(?i)(?:[A-Z]:\\Users\\[^\\\s\"']+|E:\\AI项目\\[^\r\n\"']+)")


def main() -> int:
    findings: set[tuple[str, str]] = set()
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        candidates = [ROOT / line for line in result.stdout.splitlines() if line]
    except (OSError, subprocess.CalledProcessError):
        candidates = [p for p in ROOT.rglob("*") if p.is_file()]
    for path in candidates:
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        parts = set(rel.parts)
        if parts & SKIP_DIRS:
            continue
        name = path.name.lower()
        if name == ".test-ci.sqlite3":
            continue  # isolated local test database; ignored and never staged
        if name in {n.lower() for n in FORBIDDEN_NAMES} and name != ".env.example":
            findings.add((rel.as_posix(), "private-config-path"))
        if any(part.lower() in {n.lower() for n in FORBIDDEN_DIRS} for part in rel.parts[:-1]):
            findings.add((rel.as_posix(), "local-data-path"))
        if name.endswith((".sqlite", ".sqlite3", ".db", ".log", ".pem", ".key")):
            findings.add((rel.as_posix(), "local-artifact-or-key-file"))
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            continue
        if EMAIL.search(content):
            findings.add((rel.as_posix(), "non-placeholder-email"))
        if MOBILE.search(content):
            findings.add((rel.as_posix(), "mobile-number"))
        if PRIVATE_KEY.search(content):
            findings.add((rel.as_posix(), "private-key-material"))
        if LOCAL_PATH.search(content):
            findings.add((rel.as_posix(), "personal-absolute-path"))
        if any(pattern.search(content) for pattern in TOKEN_PATTERNS):
            findings.add((rel.as_posix(), "provider-token-pattern"))
        for match in ASSIGNMENT.finditer(content):
            value = match.group(1).strip().lower()
            if not value or value.startswith(SAFE_MARKERS):
                continue
            findings.add((rel.as_posix(), "non-placeholder-credential-assignment"))
    if findings:
        for path, category in sorted(findings):
            print(f"{category}\t{path}")
        print(f"SAFETY_SCAN_FAIL={len(findings)}")
        return 1
    print("SAFETY_SCAN_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
