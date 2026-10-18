import unittest

from scripts.check_version_governance import (
    ensure_candidate_tag_unused,
    is_semver,
    validate_changelog,
    validate_package_versions,
)


class VersionGovernanceTests(unittest.TestCase):
    def test_accepts_alpha_candidate(self):
        self.assertTrue(is_semver("0.1.0-alpha.1"))

    def test_rejects_v_prefix_and_numeric_leading_zero(self):
        self.assertFalse(is_semver("v0.1.0"))
        self.assertFalse(is_semver("0.1.0-alpha.01"))

    def test_rejects_duplicate_changelog_sections(self):
        changelog = "# Changelog\n## [Unreleased]\n## [0.1.0-alpha.1]\n## [0.1.0-alpha.1]\n"
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_changelog(changelog, "0.1.0-alpha.1")

    def test_rejects_package_version_mismatch(self):
        package = {"version": "1.0.0"}
        lock = {"version": "1.0.0", "packages": {"": {"version": "1.0.0"}}}
        with self.assertRaisesRegex(ValueError, "package.json"):
            validate_package_versions("0.1.0-alpha.1", package, lock)

    def test_rejects_reusing_release_tag(self):
        with self.assertRaisesRegex(ValueError, "already exists"):
            ensure_candidate_tag_unused("0.1.0-alpha.1", ["v0.1.0-alpha.1"])


if __name__ == "__main__":
    unittest.main()
