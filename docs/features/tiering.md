<!-- last_verified: 2026-11-17 -->
# Feature: Tiering

## Purpose
Spend vector memory only on tenants that query: a hot tenant idle longer than a
threshold is parked as a verified Qdrant snapshot in B2 and dropped from the node.

## Used By
- UI: `/tenants` ("Run tiering sweep" dialog, "Prune snapshots" dialog),
  `/tenants/[tenantId]` ("Park now", snapshot history)
- API: `POST /tenants/{tenant_id}/park`, `POST /tiering/run`, `GET /tiering/policy`,
  `GET /tiering/stats`, `GET /tenants/{tenant_id}/snapshots`, `POST /snapshots/prune`
- Job: background sweep started in the app lifespan every `TIERING_SWEEP_INTERVAL_SECONDS`
  (300 by default, `0` disables it)

## Core Functions
- `app/service/tiering.py` — `select_candidates`, `park_locked` (the state machine), `run_policy`, `sweep_forever`, stats
- `app/repo/snapshot_store.py` — `upload_stream` (multipart + running sha256), `put_manifest`, `verify_snapshot`
- `app/repo/qdrant_gateway.py` — `create_snapshot`, `iter_snapshot` (streamed GET), `delete_snapshot`, `memory_bytes`
- `app/service/prune.py` — keep-last pruning that never touches the manifest's target

## Canonical Files
- Pattern exemplar: `services/api/app/service/tiering.py`

## Inputs
- `TieringRunRequest {idle_seconds?, dry_run = true}`; `idle_seconds` defaults to `TIERING_IDLE_SECONDS`
- `PruneRequest {keep_last: 1..5 = 1, apply = false}`
- `SNAPSHOT_PART_SIZE_BYTES` (8 MiB default, raised to the 5 MiB S3 floor)

## Outputs
- B2: `rag/snapshots/<tenant>/<snapshot-id>.snapshot` and `rag/snapshots/<tenant>/latest.json`
- `ParkResult {state, manifest, verified, reason, vector_bytes_freed, node_rss_delta_bytes, snapshot_upload_ms}`
- `TieringRunResult {candidates, parked, skipped[{tenant_id, reason}], dry_run}`

## Flow
1. `POST /collections/tenant_<t>/snapshots` on Qdrant: name, size, sha256 checksum.
2. Stream `GET .../snapshots/<name>` into a B2 multipart upload (`create_multipart_upload`,
   `upload_part`, `complete_multipart_upload`; `abort_multipart_upload` on any failure),
   hashing while streaming. The hash must equal Qdrant's checksum.
3. Write `latest.json` LAST:
   `{tenant_id, snapshot_key, snapshot_id, size_bytes, point_count, sha256, vector_size,
   distance, embedding_model, qdrant_version, created_at, payload_bytes}`.
4. Verify: `head_object` size equals `size_bytes`, then a streamed re-read sha256 equals `sha256`.
5. Only then delete the node-local snapshot and the collection.

Any failure in 1-4 leaves the tenant hot: the previous `latest.json` is put back (or the
new one removed), the unverified object is deleted, and the reason is returned (and listed
under `skipped` in a sweep).

Idle detection uses the most recent query or write seen by this process; after an API
restart every clock starts at process start, which can only delay parking.

## Edge Cases
- Upload failure -> multipart aborted, tenant hot, no new manifest
- Size or checksum mismatch at verify -> previous manifest restored, object deleted, tenant hot
- Tenant queried between selection and park -> skipped ("became active")
- Prune with `SNAPSHOT_PRUNE_ENABLED=false` -> 409, nothing deleted; without `apply` -> dry run

## UX States (if applicable)
- Empty: "No snapshots yet" in snapshot history
- Loading: badge shows `Snapshotting` / `Verifying` with a spinner; button spinners
- Error: toast with the server's reason; the tenant stays `Hot`

## Verification
- Test files: `services/api/tests/test_park_restore_state_machine.py`, `test_snapshot_manifest.py`, `test_tiering_policy.py`, `test_prune.py`
- Required cases: park only after verification; upload, size and checksum failures; manifest ordering; threshold edges; dry run; prune guards
- Focused verify command: `cd services/api && .venv/bin/python -m pytest tests/test_park_restore_state_machine.py tests/test_snapshot_manifest.py tests/test_tiering_policy.py tests/test_prune.py`
- Default pre-PR verify command: `pnpm verify`
- Full local verify command: `pnpm test:e2e:tiering` (Docker + B2)
- Pass criteria: all green; the e2e test parks through the policy and restores on a fresh node

## Related Docs
- [Restore on query](restore.md) · [Latency report](latency-report.md)
- [RELIABILITY.md](../RELIABILITY.md)
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
