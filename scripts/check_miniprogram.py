from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MINIPROGRAM = ROOT / "miniprogram"


def main() -> int:
    errors: list[str] = []
    for path in sorted(MINIPROGRAM.rglob("*.json")):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            errors.append(path.relative_to(ROOT).as_posix())
    for path in sorted(MINIPROGRAM.rglob("*.js")):
        result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        if result.returncode:
            errors.append(path.relative_to(ROOT).as_posix())
    if errors:
        for name in errors:
            print(f"static-check-failed\t{name}")
        print(f"MINIPROGRAM_CHECK_FAIL={len(errors)}")
        return 1
    print("MINIPROGRAM_CHECK_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
