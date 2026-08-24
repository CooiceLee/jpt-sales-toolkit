# Trip Planner Batch 3 local checkpoint — 2026-08-21

Status: **HISTORICAL CHECKPOINT — accepted and superseded by Batches 4–6**. This file records the Batch 3 acceptance state; the current release scope and validation status are maintained in `docs/v0.12.0-validation-result.md`.

## Completed and verified locally

- Batch 1 stability fixes and Batch 2 route-leg/transport-priority work remain in the working tree.
- Schema v5 adds customer-independent free stops and typed free-stop leg references.
- Free stops support create, read, update, soft archive, unified reorder, preview/generate, timeline, Markdown/CSV export, and do not create Customer, Lead, Lead Activity, visit result, or attachment records.
- Anonymous transport suggestions use server-authorized route coordinates, deterministic local estimates, allowlisted user-opened links, memory cache, manual confirmation, and a zero-write endpoint. No account or token is required.
- At this checkpoint, the frontend supported whole-day stays. Batch 4 later replaced that boundary with day / half-day scheduling.
- Unsaved personal-stop edits block route preview/save/export, suggestion search/apply, and stop removal. The protection alert is expected behavior.
- Route Save atomically persists route order, transport choices, title, region, description and travel windows.
- Candidate table headings, pagination, map action and recommendation reasons are bilingual.
- Batch 3 tests are included in `scripts/validate_v08.sh`.

## Closed audit findings

1. Customer route-location changes, spreadsheet coordinate changes and customer merges now invalidate affected itineraries and archive stale legs atomically.
2. Moving a free stop no longer restores stale archived manual leg overrides; location/identity changes clear invalid locks while stay-only changes preserve valid overrides.
3. Stale itineraries are rejected by execution and export endpoints until recalculated and saved.
4. Markdown/CSV exports include every route leg, including the final leg from the last stop to the return destination.
5. Customer and free-stop stay values survive input, preview, reordering and rerendering.
6. Visible title, region and planning notes win over an older route draft when Save route is clicked.
7. Export includes planning notes and departure/return windows.

## Browser acceptance scenario

An isolated database and local service on port 8770 were used; both were separated from the production desktop data directory and the service was stopped after validation.

- Dates: 2026-09-15 through 2026-09-30.
- Route context: China departure/return plus France, Germany and Italy customer visits.
- Personal stop: Frankfurt transfer hotel, two whole days, no customer or lead relationship.
- Verified: transport-priority reordering, manual stop reordering, per-leg suggestion apply/lock, stay recalculation, unsaved-edit guard, route save, Markdown/CSV export and final return leg.
- Final saved route stayed within the requested window and ended on 2026-09-30.

## Validation evidence

- Focused Trip Planner backend and frontend suites passed.
- Authorization boundaries, schema-v5 safe upgrade/recovery, spreadsheet/JSON exchange, Tech task packages, maps/geocoding, bilingual UI, module contracts and data-integrity suites passed.
- `bash scripts/validate_v08.sh`: **PASS — v0.11 validation completed**.
- `git diff --check`: PASS.
- Production database SHA-256 remained exactly `79bb0071decb770405f9696ac967cac640a4385f81aca59dc5c77dc516100280` before and after the isolated acceptance run.
- The isolated local service was stopped and the QA browser tabs were closed.

## Boundary at this checkpoint

Free-stop duration was 1–30 whole days at Batch 3. Batch 4 subsequently added day / half-day scheduling. Transport results remain approximate planning aids that require manual confirmation; exact real-time flight inventory is outside the product scope.

## Safety / repository state

- No Git commit, tag, push, installer build or release was made for this batch.
- The production desktop database was not opened by the current source tree.
- The working tree is intentionally dirty and contains tracked modifications and new source/test files. Do not clean, reset or checkout them.

## Subsequent work

The user accepted this checkpoint. Batches 4 and 5 added half-day schedules, visit briefings and formal XLSX / offline HTML / ICS exports. Batch 6 owns the integrated v0.12.0 release validation.
