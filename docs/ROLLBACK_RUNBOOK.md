# Rollback runbook

This runbook preserves shared Git history and separates application rollback from database recovery. It documents a procedure; it does not authorize production deployment.

## Local rollback rehearsal

Run `python scripts/rehearse_rollback.py` before relying on this procedure. The script clones the current repository into an automatically removed temporary directory, creates one synthetic file and commit, reverts that commit with `git revert`, compares the resulting tree with the starting commit, and runs the version-governance checker. It has no remote push, production, database, student-data, or deployment effects. Its generated commit IDs are local rehearsal evidence only.

## Before merge

For an unmerged feature branch, stop further pushes if the change is unsafe. Keep the branch and PR for review. Correct the branch in a new commit or close the PR after the owner decides it is no longer needed. Do not reset a shared branch, force-push, or delete another developer's work.

## After merge, before deployment

Use a new revert branch and Pull Request. The revert PR must identify the original PR and merge commit, explain the effect, include regression coverage, and pass independent review and CI. GitHub's Revert action may create the revert PR. For a merge commit, the equivalent local command is:

    git switch -c revert/<task-id>-<short-reason> origin/develop
    git revert -m 1 <merge-commit-sha>
    git push -u origin revert/<task-id>-<short-reason>

Merge the revert only through the normal protected PR process. Retain the original commits and both PR records.

## After application deployment

1. Stop or pause further rollout and record the affected release tag, commit SHA, deployment identifier, time, and observed impact without copying private data into public logs.
2. Select the last known-good, independently accepted release tag and its verified build artifact. Check the artifact checksum and provenance before redeploying it.
3. Redeploy that artifact using the deployment platform's supported rollback process. Do not rebuild an old tag from an unverified machine and call it the same artifact.
4. Run health checks and focused smoke tests for login, role boundaries, assignments, submission, grading, and review states. Confirm that unresolved HOLD_REVIEW items have not become scores.
5. Record the recovery commit or tag, artifact checksum, deployment result, data checks, and follow-up repair PR.

If no verified prior artifact exists, stop and prepare a reviewed hotfix build. Do not claim rollback success based only on checking out an older commit.

## Database and user data

Git does not restore databases, student submissions, uploaded images, grades, or external storage. Before any schema change, require a verified backup and a reviewed down migration or forward compensation plan. Confirm the migration is compatible with both the old and new application during rollout. After recovery, compare row counts, foreign-key relationships, immutable publication snapshots, grades, and file references.

Never use git reset --hard, force-push, tag deletion, or history rewriting as an application rollback. Do not roll back a database automatically just because application code was reverted; assess data written by the newer application first.
