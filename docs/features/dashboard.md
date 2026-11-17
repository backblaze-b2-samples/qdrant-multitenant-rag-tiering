<!-- last_verified: 2026-11-17 -->
# Feature: Dashboard

## Purpose
Answer "how much vector memory are we spending, and how much has parking saved?"
at a glance.

## Used By
- UI: `/` page (dashboard home)
- API: `GET /tiering/stats`, `GET /tenants`, `GET /reports`

## Core Functions
- `apps/web/src/components/dashboard/stats-cards.tsx` — hot / parked / empty counts,
  vector memory in use and freed (estimates), snapshot and corpus bytes in B2
- `apps/web/src/components/dashboard/tenant-memory-chart.tsx` — per-tenant vector
  footprint; hot bars solid, parked bars faded
- `apps/web/src/components/reports/reports-list.tsx` — the five latest latency reports
- `services/api/app/service/tiering.py` — `get_stats()`

## Canonical Files
- Pattern exemplar: `apps/web/src/components/dashboard/stats-cards.tsx`

## Inputs
- None (loads automatically; tenants and stats poll every 15 s because the background
  sweep can change state without a user action)

## Outputs
- `TieringStats {hot, parked, empty, vector_bytes_hot, vector_bytes_freed, snapshot_bytes_b2, corpus_bytes_b2}`

## Flow
- Stats derive tenant states from Qdrant collections and B2 manifests, then sum
  `points * vector_size * 4 + payload bytes` per state, and list `rag/snapshots/` and
  `rag/corpus/` for bytes in B2.

## Edge Cases
- No tenants -> zero cards and an empty chart pointing to `/tenants`
- Qdrant down -> stats request fails, `ErrorState` with retry; the health banner names Qdrant

## UX States (if applicable)
- Empty: "No tenants yet" / "No reports yet"
- Loading: skeleton cards and chart
- Error: inline `ErrorState`

## Verification
- Test files: `services/api/tests/test_tiering_policy.py::test_stats_split_hot_and_parked`
- Focused verify command: `cd services/api && .venv/bin/python -m pytest tests/test_tiering_policy.py -k stats`
- Default pre-PR verify command: `pnpm verify`
- Full local verify command: `pnpm verify:full` when E2E/live prerequisites apply
- Pass criteria: hot and parked tenants are counted separately and freed memory is non-zero after a park

## Related Docs
- [Tiering](tiering.md) · [Latency report](latency-report.md)
- [README.md](../../README.md)
- [docs/app-workflows.md](../app-workflows.md)
