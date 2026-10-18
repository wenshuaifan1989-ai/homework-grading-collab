# Software release policy

Status: release process proposal for the collaboration repository. Repository visibility is PUBLIC. This document does not approve a product release.

## Version source and scheme

The root VERSION file is the only authoritative software version. frontend/package.json and frontend/package-lock.json repeat the same value for package metadata and must stay synchronized. The version checker enforces that equality.

Use Semantic Versioning:

- 0.1.0-alpha.1: first technical collaboration pre-release; not product acceptance or production approval.
- 0.1.0-beta.1: main functionality is implemented and end-to-end testing has started.
- 0.1.0: first independently accepted stable product version.
- Patch increments such as 0.1.1 are for compatible fixes.
- Minor increments such as 0.2.0 add backward-compatible functionality.
- Breaking changes require an impact and migration plan and approval from the project owner before choosing a version.

Only an approved release PR updates VERSION and frontend/package.json. Feature commits do not increment versions. CHANGELOG.md keeps an Unreleased section and a section for each approved version. A candidate entry must be labelled as pending until it is actually released.

## Release path and responsibilities

1. Develop on a short-lived feature or fix branch from the latest origin/develop. Push only that branch and open a PR to develop.
2. The PR describes user-visible changes, affected roles and pages, shared API and database changes, compatibility, migration, tests, rollback, documentation, and licensing or source concerns.
3. CI must pass, including python-tests, frontend-build, public-content safety scan, and version-governance checks. The branch must be current with protected develop, and review discussions must be resolved.
4. A person other than the PR author reviews and approves. Do not self-approve or bypass branch protection.
5. A release PR updates VERSION, frontend/package.json, frontend/package-lock.json, and CHANGELOG.md together, and supplies the release checklist and rollback plan. A release candidate must not reuse an existing v-prefixed tag.
6. After the release PR is merged, the project owner separately approves making a release. Verify the exact develop commit and its CI results, then create an annotated v-prefixed tag on that commit and a GitHub Release from that tag. Never auto-create a tag or Release when develop changes.
7. Treat release tags as immutable. Before a formal release, check whether GitHub can enforce a v-prefixed tag ruleset that blocks updates and deletion; if enforcement is unavailable, the owner must preserve tags manually.
7. Attach only reproducible, non-sensitive build assets. Record the tag, commit SHA, CI run, asset checksums, and acceptance evidence in the release notes.
8. The manual Release metadata check workflow performs metadata and public-content checks only. It does not create tags, GitHub Releases, deployments, or database changes.

Example commands for a future, separately approved release:

    git switch develop
    git fetch origin
    git pull --ff-only origin develop
    git tag -a v0.1.0-alpha.1 -m "v0.1.0-alpha.1"
    git show --no-patch --format=fuller v0.1.0-alpha.1
    git push origin v0.1.0-alpha.1
    gh release create v0.1.0-alpha.1 --verify-tag --title "v0.1.0-alpha.1" --notes-file RELEASE_NOTES.md

These commands are documentation only; no tag or Release is created by this change.

## Release acceptance checklist

Do not mark a version stable until all applicable items have evidence:

- Product behavior and role permissions pass the agreed acceptance flow.
- Student privacy and cross-role negative tests pass.
- API, database, and published-paper compatibility is verified; migrations have a reviewed backup and rollback or compensation plan.
- Required real browser, WeChat IDE, or device acceptance is complete.
- Source ownership, upstream license terms, and every included third-party asset are cleared.
- Independent PR review and all required CI checks pass on the exact tagged commit.
- Build inputs and outputs are reproducible; release assets have recorded checksums.
- A rollback target and on-call operator are identified, and the rollback procedure has been reviewed.
- Public repository contents, commit history, PR discussion, and Actions logs contain no secrets, student information, local evidence, or restricted material.

Current limitations: upstream license evidence remains pending; product and real-device acceptance are not complete. Therefore this PR establishes governance only. It does not declare a stable product release or resolve licensing.
