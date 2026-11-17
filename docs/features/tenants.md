<!-- last_verified: 2026-11-17 -->
# Feature: Tenants

## Purpose
Give each customer (tenant) an isolated retrieval index: its source documents
live in Backblaze B2 under `rag/corpus/<tenant>/`, and its vectors live in one
Qdrant collection `tenant_<tenant>` while it is hot.

## Used By
- UI: `/tenants` (table, "New tenant" dialog, "Seed demo tenants"),
  `/tenants/[tenantId]` (detail, query box, Edit sheet, danger zone)
- API: `GET/POST /tenants`, `POST /tenants/seed`, `GET/PATCH/DELETE /tenants/{tenant_id}`,
  `POST /tenants/{tenant_id}/query`

## Core Functions
- `app/service/tenants.py` — create, read, edit, delete; state derivation
- `app/service/ingest.py` — chunking (120 words, 20 overlap), deterministic point ids, upsert
- `app/service/seed.py` + `seed_corpus.py` — six synthetic tenants on distinct subjects
- `app/service/validation.py` — tenant id and document name rules
- `app/repo/embedder.py` — fastembed `BAAI/bge-small-en-v1.5`, CPU (CUDA when available)

## Canonical Files
- Pattern exemplar: `services/api/app/service/tenants.py`

## Inputs
- `tenant_id`: lowercase letters, digits and hyphens, 2 to 40 characters
- `display_name`: free text, up to 80 characters
- `documents`: 1 to 50 `.txt` / `.md` files, sent as text (the browser reads them)

## Outputs
- B2: `rag/corpus/<tenant>/<filename>` per document and `rag/corpus/<tenant>/_tenant.json`
  (display name, created time, documents with size, chunk count and payload bytes)
- Qdrant: collection `tenant_<tenant>` (cosine, vector size read from the model)
- `TenantSummary` / `TenantDetail`; state is derived, never stored:
  `hot` (collection exists), `parked` (no collection, `latest.json` in B2),
  `empty` (metadata only), plus in-memory `writing` / `embedding` / `upserting` (the create stages, also set by an
  edit that re-indexes), `snapshotting` / `uploading` / `verifying` / `dropping` (the park
  stages) and `restoring`. `GET /tenants/<id>/progress` -> `TenantProgress {tenant_id, state, done, total}` reads only
  memory (no B2), so it answers before the tenant's metadata exists; the New tenant dialog polls
  it every 500 ms and shows "Step n of 3" with "document n of N" while writing, "n of N
  chunks" while embedding (in batches of 16), and a determinate bar
- The list and detail derive each tenant's state and points from one per-tenant read (stage
  first, then the node), never from a list-wide collection snapshot, so a create or park that
  finishes mid-listing is not shown as "Empty, 0 points"
- Seed: every Seed control shows a running seed (shared mutation key), and the result toast
  fires even if the clicked control unmounted (the table's empty-state button does)

## Flow
- Create: validate, write documents to B2, write `_tenant.json`, embed and upsert, rewrite
  `_tenant.json` with chunk counts. If indexing fails the tenant still exists as `empty`.
- Edit: under the tenant lock; a parked tenant is restored first. Removed documents are
  deleted from B2 and their points from Qdrant; added ones are written and embedded. If a
  snapshot exists it is marked stale until the next park.
- Delete: requires `confirm=<tenant_id>`. Drops the collection, deletes every object under
  `rag/snapshots/<tenant>/` and `rag/corpus/<tenant>/`. Reports are kept.
- Query: under the tenant lock; restores first when parked (see [Restore](restore.md)).

## Edge Cases
- Duplicate tenant id -> 409, nothing written
- Bad id or document name -> 400/422 before any write
- Delete with the wrong confirmation -> 400, nothing deleted
- Removing every document -> 400 (a tenant keeps at least one)

## UX States (if applicable)
- Empty: "No tenants yet" with the seed control
- Loading: table skeleton; "Indexing…" on create, "Seeding…" on seed
- Error: inline `ErrorState`; toasts for mutations

## Verification
- Test files: `services/api/tests/test_tenant_crud.py`, `test_tenant_id_validation.py`
- Required cases: create indexes and stores the corpus, duplicate, edit add/remove, edit on
  a parked tenant, delete confirmation and scope, seed idempotency
- Focused verify command: `cd services/api && .venv/bin/python -m pytest tests/test_tenant_crud.py tests/test_tenant_id_validation.py`
- Default pre-PR verify command: `pnpm verify`
- Full local verify command: `pnpm verify:full` when E2E/live prerequisites apply
- Pass criteria: all listed tests green; `pnpm test:e2e:tiering` green when Docker and B2 are available

## Related Docs
- [Tiering](tiering.md) · [Restore on query](restore.md)
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
- [docs/app-workflows.md](../app-workflows.md)
