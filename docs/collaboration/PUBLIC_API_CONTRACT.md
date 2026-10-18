# V2 compatibility contract

Owner: wenshuaifan1989-ai. Student implementation owner: santaozy123-hub.
Status: baseline contract plus explicitly marked additive proposal. No database or API was deployed by publishing this document.

## Existing identifiers and behavior

- User.id is a login identity; Student.id is the learner entity; StudentRoster.id is a roster row. They are not interchangeable. Never key per-student requirements by null or a display name.
- Assignment.id identifies the released assignment; variant_question_id identifies a published question. The source question number is a string and remains in the publication snapshot.
- uniform_mixed releases one original paper. Requirements are required/optional per student and original question; no L1/L2/L3 capability labels appear on student screens.
- One final submission contains 1-9 images and creates one HomeworkTask with multiple HomeworkImages. Preserve the existing endpoint and idempotency behavior; do not submit each photo as another task.
- Answers, analyses and teacher recommendation reasons are not student assignment-list fields. Existing result permissions remain in force.
- WAIT_REVIEW/HOLD_REVIEW is unresolved, not failed, successful or zero score. Only trusted teacher-confirmed evidence enters learning aggregation.
- Published source, answers, knowledge references and per-student requirements are immutable. Later paper editing or sharing changes must not rewrite released grades or snapshots.
- Cross-role requests return 403; hidden or other-class resources may return 404. The UI must not widen access to make a screen work.

## Change process

1. Develop candidate client/server changes independently on a feature branch and isolated test database. Document method/path, field types, ID meaning, authentication, errors and an anonymous example alongside the change; no pre-development owner approval is required.
2. Supply compatibility, migration/down or compensation and additive/breaking-change notes in the integration PR. The owner resolves the final shared contract at merge review, not as a daily development gate. Retain old fields/compatible behavior while existing clients depend on them.
3. Run contract tests including forbidden identities, cross-class resources, duplicate submissions and partial/failed results.
4. Develop and test both sides in the isolated branch without waiting for teacher/admin completion; mark unavailable real integrations pending rather than claiming mocks are live. For integration, merge the compatible backend before dependent student changes and retain the compatibility window. Only the owner confirms merges into develop.
5. Reverting source does not revert database data. Retain immutable records and separately review data compensation.

## Local additive library proposal

The planned /api/v1/paper-library endpoints add administrator/teacher library metadata, school/subject visibility and revocable sharing. They do not replace student homework, submission or result endpoints. Student-side work must continue using the baseline until this proposal is implemented, tested, reviewed and merged.

The proposed fields, permissions, compatibility and migration limits are specified in [PAPER_LIBRARY_V1_PROPOSAL.md](PAPER_LIBRARY_V1_PROPOSAL.md). Local implementation is not a deployed or merged contract.

No sample in this document is a real student record. Paid model calls remain outside this contract and require explicit authorization.
