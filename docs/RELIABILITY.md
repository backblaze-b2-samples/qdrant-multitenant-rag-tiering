<!-- last_verified: 2026-11-17 -->
# Reliability

Reliability expectations and practices for this project.

## Verify Before Park

The one rule that protects tenant data: a collection is dropped only after its
snapshot is safely in B2 and checked.

1. Qdrant creates the snapshot and reports its sha256 checksum.
2. The snapshot streams into a B2 multipart upload, hashed on the way; the hash
   must equal Qdrant's checksum. Any failure aborts the multipart upload, so no
   partial object ever becomes visible.
3. `latest.json` is written **last**. A previously good manifest is never
   overwritten before the new snapshot object is fully uploaded.
4. Verification reads B2 back: `head_object` size, then a streamed re-read
   sha256, both against the manifest.
5. Only then are the node-local snapshot and the collection deleted.

Any failure in steps 1-4 leaves the tenant hot: the previous manifest is put
back (or the new one removed), the unverified object is deleted, the reason is
logged at WARNING and returned (a sweep lists it under `skipped`). Each failure
mode (upload error, size mismatch, checksum mismatch) has its own test in
`tests/test_park_restore_state_machine.py`.

## Restore Integrity

- The snapshot is hashed while it streams from B2; a size or sha256 mismatch with
  the manifest refuses the load (502).
- Qdrant's upload API is also given the checksum.
- The restored point count must equal the manifest's, or the collection is dropped
  again and the tenant stays parked.
- A manifest built with another embedding model or vector size is refused (409)
  instead of returning wrong neighbours.

## Concurrency

- One `asyncio.Lock` per tenant serialises park, restore, edit, delete and query.
  A query that arrives mid-park waits, then restores from the snapshot the park just
  verified (tested).
- The background sweep re-checks idleness under the lock, so a tenant queried after
  selection is skipped rather than parked.
- Blocking B2 and Qdrant calls run in worker threads (`asyncio.to_thread`); the
  event loop keeps serving other tenants.

## Health Checks

- `GET /health` reports `b2_connected` and `qdrant {ok, version}`; `status` is
  `healthy` only when both answer. It is always HTTP 200, so read the fields.
- The B2 client bounds connection attempts to 5 seconds, socket reads to 30
  seconds, and standard retries to 3 total attempts.
- The web app shows a banner when B2 or Qdrant is unreachable.

## Error Handling

- Service errors carry their HTTP status (`app/service/errors.py`): 400 invalid input, 404 not found, 409 conflict (duplicate tenant, model mismatch, prune disabled, park failed during a benchmark), 502 storage or integrity failure
- Uncaught exceptions become a typed JSON 500 (`{"detail": "Internal server error"}`) in `timing_middleware`
- **Error responses carry CORS headers.** `CORSMiddleware` is registered LAST in `main.py` so it wraps every response, including the catch-all 500. Regression-guarded by `tests/test_error_handling.py::test_unhandled_exception_500_carries_cors_headers`.

## Logging

- Structured JSON logging via Python stdlib, with a `request_id` per request
- ERROR for failures, WARNING for aborted parks and degraded state, INFO for requests and sweeps that found candidates

## Observability

- `/metrics` exposes request counts and durations plus `tenant_parks_total` and `tenant_restores_total`
- Latency reports in B2 record warm, restore and post-restore latency and memory freed per run

## Stateful Counters: durability caveats

The download counter, the `/metrics` counters, the per-tenant idle clocks and the transitional states are **in-process, per replica**:

- **Idle clocks** reset on restart to the process start time, which can only delay parking, never park early. Tenant state itself is never lost: it is derived from Qdrant collections and B2 manifests.
- **Download counter** (`app/repo/counter.py`) persists to `DOWNLOAD_COUNT_FILE` (default `.data/download_count.json`); in a container without a volume it resets on every restart.
- **`/metrics` counters** reset on restart.
- Running more than one API replica against one Qdrant node is unsupported: the locks are per process.

## Rate Limiting

- Per-IP fixed-window limiter; `RATE_LIMIT_PER_MINUTE` / `RATE_LIMIT_WRITE_PER_MINUTE`. Rejected requests get `429` with `Retry-After`.

## Graceful Degradation

- B2 unreachable: the explorer and tenant pages show error states; parks fail safe (tenant stays hot)
- Qdrant unreachable: health is degraded, tenant routes fail with an error, nothing is deleted from B2
- Embedding model download fails at startup: logged; the first ingest or query retries the load
- The bucket explorer's full listing is cached, warmed at startup and served stale-while-revalidate (`LIST_CACHE_TTL_SECONDS`, default 300)

## Deployment

- Docker Compose is the supported runtime. Named volumes keep Qdrant storage and
  the fastembed model cache across restarts; `docker compose down -v` deletes them
  (hot tenants that were never parked lose their vectors, but their corpus stays in
  B2 and can be re-ingested by editing the tenant).
- The Qdrant image is pinned (`qdrant/qdrant:v1.20.2`). After changing it, run
  `docker compose down -v` before `up`, and bump `qdrant-client` to the same minor.
- Environment-specific configuration uses environment variables; no values are committed.
