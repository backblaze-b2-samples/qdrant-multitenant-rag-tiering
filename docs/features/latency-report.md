<!-- last_verified: 2026-11-17 -->
# Feature: Latency report

## Purpose
Turn "should we park idle tenants?" into numbers: warm latency, restore time,
first-query-after-restore and post-restore latency, and memory freed, per tenant.

## Used By
- UI: `/reports` (benchmark form, report list), `/reports/[runId]` (charts and figures),
  dashboard "Latency reports" card
- API: `POST /reports`, `GET /reports`, `GET /reports/{run_id}`

## Core Functions
- `app/service/reports.py` — `run_benchmark`, `probe_queries`, `latency_stats`, `results_match`, `write_report`
- `apps/web/src/lib/report-chart.ts` — chart data shaping (latency, memory, restore penalty)

## Canonical Files
- Pattern exemplar: `services/api/app/service/reports.py`

## Inputs
- `BenchmarkRequest {tenant_ids (1..6), queries_per_phase: 5 | 10 | 20 = 10}`

## Outputs
- B2: `rag/reports/<run-id>/report.json`
- `LatencyReport {run_id, created_at, qdrant_version, embedding_model, tenants[...]}`, per tenant:
  `point_count, warm {n, p50_ms, p95_ms, mean_ms}, snapshot_bytes, snapshot_upload_ms,
  restore {download_ms, load_ms, total_ms}, first_query_after_restore_ms, post_restore,
  memory_freed {vector_bytes_estimate, node_rss_delta_bytes?}, results_match`
- Side effect: each measured tenant ends hot (it was parked and restored by the run)

## Flow
- Probe queries are the tenant's own corpus sentences, in document order, cycled to N.
- Warm-up query (restores a parked tenant, loads the model), then N timed warm queries.
- Park through the full verify-before-drop path.
- First query (timed end to end) restores from B2; then the same N probes again.
- Compare hit ids and scores (tolerance 1e-4); write `report.json`.

Percentiles are nearest-rank, so every reported figure is a real sample.
`vector_bytes_estimate` is `points * vector_size * 4 + payload bytes`;
`node_rss_delta_bytes` is Qdrant's `memory_resident_bytes` before minus after the drop,
labelled "observed" because the allocator may not return memory immediately.

## Edge Cases
- Unknown tenant -> 404 before anything runs
- A park that fails verification -> 409 with the reason; no report written
- More than six tenants -> 422

## UX States (if applicable)
- Empty: "No reports yet"
- Loading: "Benchmarking…" (runs inside the request)
- Error: toast with the reason

## Verification
- Test files: `services/api/tests/test_report_writer.py`, `apps/web/src/lib/report-chart.test.ts`
- Required cases: percentiles, tolerance, report.json written and listed, unknown tenant
- Focused verify command: `cd services/api && .venv/bin/python -m pytest tests/test_report_writer.py`
- Default pre-PR verify command: `pnpm verify`
- Full local verify command: `pnpm test:e2e:tiering` (runs a real benchmark)
- Pass criteria: a person running the demo can read warm and post-restore figures on `/reports/[runId]`

## Related Docs
- [Tiering](tiering.md) · [Restore on query](restore.md)
- [docs/app-workflows.md](../app-workflows.md)
