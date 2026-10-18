# V2 responsibilities and review ownership

Status: proposed working agreement; an invitation or document does not prove two-person acceptance.

| Area | Primary owner | Actual paths | Review boundary |
|---|---|---|---|
| Admin and teacher Web | wenshuaifan1989-ai | frontend/src/views/PlatformAdminView.vue, TeacherV2WorkspaceView.vue, TeacherWorkspaceView.vue, TeacherMistakesView.vue, KnownAssignmentsView.vue, LearningAdviceView.vue, AssignmentPlansView.vue | Another authorized developer approves the PR |
| Student Web | santaozy123-hub | frontend/src/views/StudentWorkspaceView.vue, StudentMistakesView.vue; frontend/src/api/student.ts | Owner reviews API, identity and submission compatibility |
| Student mini-program | santaozy123-hub | miniprogram/pages/student/ (bind, homework, detail, submit, result, mistakes) | No separate tracked components directory currently; shared auth/upload helpers require owner review |
| Public contracts, auth, database | wenshuaifan1989-ai | app/v1/, schemas/, models/, services/, utils/; frontend/src/api/client.ts, frontend/src/stores/auth.ts; miniprogram/utils/ | Owner arbitration; a student UI change does not grant schema or permission changes |
| Shared shell and build | joint, owner arbitrates | frontend/src/components/AppLayout.vue, frontend/src/router/index.ts, frontend/src/styles/, .github/workflows/, requirements.txt | Coordinate before editing shared files |

The collaborator's GitHub Write permission is repository-wide. These boundaries are review responsibilities, not directory-level access controls. CODEOWNERS.proposed is a suggestion, not an active server restriction.

Use separate clones/worktrees and short-lived feature branches. Fetch develop before starting. Do not overwrite another checkout's changes. Each PR states affected endpoints, compatibility window, tests, UI evidence and rollback. Keep the existing immutable publication and HOLD_REVIEW behavior.

PR #1 contains the CI prerequisite and collaboration rules. Its checks passing on a feature branch does not make develop green. The author cannot supply the required independent approval. Wait for the invited account to accept Write and review from its own environment.

New upstream-derived business changes remain local while LICENSE_PENDING is unresolved. Do not add private papers, catalog exports, governance evidence, credentials or database snapshots to public Git.
