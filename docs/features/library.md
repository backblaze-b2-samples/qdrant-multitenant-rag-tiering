<!-- last_verified: 2026-11-17 -->
# Feature: Library

## Purpose
Show everything this app wrote to B2, organised the way the app thinks about it:
per tenant, as corpus, snapshots or reports.

## Used By
- UI: `/library` (tenant and kind selectors, grouped cards; `?kind=reports` preselects a kind)
- API: `GET /library?tenant_id=&kind=`

## Core Functions
- `app/service/library.py` — `list_library`
- `apps/web/src/components/library/library-browser.tsx`

## Canonical Files
- Pattern exemplar: `services/api/app/service/library.py`

## Inputs
- `tenant_id` (optional, validated), `kind` (optional: `corpus`, `snapshots`, `reports`)

## Outputs
- `list[LibraryEntry {key, tenant_id, kind, size_bytes, last_modified}]`; reports have no tenant

## Flow
- One `list_objects_v2` over `RAG_PREFIX`; keys are classified by their second segment.
- Clicking an object opens it in the bucket explorer's preview (`/files?preview=<key>`),
  streamed through the API content proxy.

## Edge Cases
- Objects outside the three kinds under the prefix -> ignored
- Unknown kind -> 422

## UX States (if applicable)
- Empty: "Nothing here yet"
- Loading: skeleton
- Error: `ErrorState` with retry

## Verification
- Test files: `services/api/tests/test_library.py`
- Focused verify command: `cd services/api && .venv/bin/python -m pytest tests/test_library.py`
- Default pre-PR verify command: `pnpm verify`
- Pass criteria: every corpus, snapshot and report object appears under its tenant and kind

## Related Docs
- [Bucket explorer](file-browser.md)
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
