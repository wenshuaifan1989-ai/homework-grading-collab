# Paper library v1: additive contract proposal

State: implemented and API-tested in a local feature branch, not released or merged here. Student endpoint changes: none. Backend/schema approval remains with the project owner. Student-side adoption and cross-device validation remain pending.

## Roles and data

The existing PaperDocument remains the only original-paper aggregate. One additive v2_paper_library_entry row per paper records school_id, subject, grade, contributor_id, source_kind, shared, primary archive and policy_revision. Existing papers without metadata remain private legacy papers; school/sharing is never inferred from their contents.

Teachers obtain scopes from active school + active class + active ClassTeacher with explicit subject codes and class grade. An empty subject list grants no library scope. Administrators use the existing platform_admin role and may maintain active schools across the supported mathematics, physics and chemistry scopes. No new role is introduced.

Teacher uploads default private. Shared visibility requires the same authorized school, subject and grade. Only the author or existing administrator may edit or withdraw sharing. Raw-file, answer/detail, list, catalog and publication access all require server checks. A teacher who teaches at two schools still cannot publish a school-A library paper to school B.

## Additive endpoints under /api/v1/paper-library

| Method and path | Request/response essentials |
|---|---|
| GET /context | administrator flag, authorized scopes, truthful AI availability/quota; no credential fields |
| GET /papers | optional school_id/subject/grade; only visible papers and permitted private legacy records |
| POST /batches | multipart files (1-9), policy JSON {school_id, subject, grade, shared}; Idempotency-Key required; same import service as teacher V2 |
| GET /papers/{id} and /source | scoped metadata/full teacher detail or hash-checked original file; inaccessible resources are 404 |
| PUT /papers/{id}/sharing | {shared, expected_policy_revision}; stale policy is 409; no copying or contributor change |
| PUT /papers/{id}/archive | {kind, node_id, catalog_version, expected_policy_revision}; only verified IDs/versions, otherwise 422 |
| PUT /papers/{id} | existing PaperEdit with expected_revision; saves a new draft revision, no published snapshot changes |
| POST /papers/{id}/confirm | original answer/source audit remains required |
| POST /papers/{id}/publish | existing Publish contract; shared read does not confer edit access; freeze original contribution metadata |
| GET /papers/{id}/suggest-requirements | class_id required; authorized school/subject/grade; evidence-backed suggestions only, never automatic tier changes |
| GET /catalog | authorized scope only; missing/uncollected catalog stays empty, never invented |
| GET /trends | Shanghai Monday-Sunday window from actual publication events with explicit UTC timestamps; distinct teacher per paper; at least three teachers; visible papers only; legacy timestamps of unknown timezone are not inferred |
| POST /ai-intent | prompt plus explicit use_current_point=false by default; current implementation returns MODEL_NOT_RUN with quota 0; no model call |

Upload source_kind is assigned by the server, not client supplied. Raw files and hashes remain immutable. Sharing withdrawal leaves existing assignments, frozen answers, original grades and publication download access intact. New source metadata is additive to a publication snapshot and is not returned by student_fields.

## Migration, tests and limits

The migration only creates the metadata table. Its immediate second run creates nothing; rollback may drop an empty table only. Nonempty metadata is retained and routes may be disabled instead. Git revert alone does not roll back a database.

Local tests cover cross-role/school/subject access, direct raw-file authorization, sharing revocation and stale versions, idempotency, legacy read compatibility, trusted catalog IDs, actual-publication trend deduplication, frozen assignments and source integrity. These are isolated API tests, not GUI/model accuracy or two-person acceptance.

The full content-edit/reorder/delete/undo and newly rendered layout artifact contract is still pending. Do not implement a student layout assumption against this proposal or treat draft UI changes as a newly generated paper. Paid AI generation, real GUI and device acceptance remain separate gates.

For library-managed papers, structural edits and old transfer endpoints return 409 until a newly rendered layout artifact exists. Current draft editing saves title and per-question attributes while retaining original question identity/order. This guards against distributing the old PDF as a rearranged paper; it is not completion of the layout editor.
