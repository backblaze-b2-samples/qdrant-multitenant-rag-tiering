<!-- last_verified: 2026-11-17 -->
# Feature: Restore on query

## Purpose
Make parking invisible to callers: the first query to a parked tenant loads its
snapshot from B2 into the current Qdrant node, then answers, and says what the
restore cost.

## Used By
- UI: query box on `/tenants/[tenantId]` (shows "Restored from B2 before answering"
  with download, load and total time), "Restore now"
- API: `POST /tenants/{tenant_id}/query` (`restored`, `restore` timing),
  `POST /tenants/{tenant_id}/restore`; also every edit of a parked tenant

## Core Functions
- `app/service/restore.py`: `restore_locked`, `restore_tenant`, `query_tenant`
- `app/repo/snapshot_store.py`: `download_to_spool` (streamed `get_object` into a spooled temp file, hashed)
- `app/repo/qdrant_gateway.py`: `upload_snapshot` (`POST /collections/<c>/snapshots/upload?priority=snapshot&checksum=…`)

## Canonical Files
- Pattern exemplar: `services/api/app/service/restore.py`

## Inputs
- `rag/snapshots/<tenant>/latest.json` and the object it names
- The running embedding model (must equal the manifest's `embedding_model` and `vector_size`)

## Outputs
- Collection `tenant_<tenant>` on whatever node `QDRANT_URL` points at
- `RestoreTiming {download_ms, load_ms, total_ms}`

## Flow
- Under the tenant lock: read `latest.json`; refuse with 409 if the model differs.
- Stream the snapshot from B2 into a spooled temp file, hashing it; refuse if size or
  sha256 differ from the manifest.
- Post it to Qdrant's snapshot upload API (Qdrant also checks the checksum).
- Count points; if the count differs from the manifest the collection is dropped and 502 returned.
- Qdrant's "recover from URL" is deliberately not used: it would make Qdrant fetch from B2
  itself, outside this app's S3 client and its custom user agent.

## Edge Cases
- Node has never seen the tenant (fresh storage) -> works; that is the e2e test
- Different embedding model configured -> 409, nothing loaded
- Corrupted object in B2 -> 502 before loading
- Query arrives during a park -> waits on the lock, then restores the snapshot just verified

## UX States (if applicable)
- Loading: "Restoring from B2…" on the Search button while parked
- Error: inline error under the query box

## Verification
- Test files: `services/api/tests/test_park_restore_state_machine.py`, `live_tests/test_e2e_tiering.py`
- Required cases: restore + point count, point-count mismatch, model mismatch, query restores first, concurrent query waits
- Focused verify command: `cd services/api && .venv/bin/python -m pytest tests/test_park_restore_state_machine.py`
- Default pre-PR verify command: `pnpm verify`
- Full local verify command: `pnpm test:e2e:tiering`
- Pass criteria: same hit ids and scores (within 1e-4) before parking and after restoring on a fresh node

## Related Docs
- [Tiering](tiering.md)
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
