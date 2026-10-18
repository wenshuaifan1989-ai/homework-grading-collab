import subprocess
import sys
import unittest
from pathlib import Path


class RollbackRehearsalTests(unittest.TestCase):
    def test_local_revert_rehearsal(self):
        repository = Path(__file__).resolve().parents[1]
        script = repository / "scripts" / "rehearse_rollback.py"
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=repository,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("revert commit retained the original change in history", result.stdout)
        self.assertIn("reverted tree matches the starting commit and is clean", result.stdout)
        self.assertIn("version-governance checks passed after the revert", result.stdout)
        self.assertIn("LOCAL_ONLY:", result.stdout)


if __name__ == "__main__":
    unittest.main()
