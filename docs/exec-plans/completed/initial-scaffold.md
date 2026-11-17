# Initial scaffold plan: qdrant-multitenant-rag-tiering

Starter kit: `backblaze-b2-samples/vibe-coding-starter-kit` at commit
`b1ed9b649bfb86c06432445dcd988dd4fcd4acbc`. Everything below is the delta against
that tree. The kit is the ceiling: keep what this app uses, trim the rest.

## 1. Purpose

`qdrant-multitenant-rag-tiering` is a multi-tenant retrieval service for teams
whose vector database bill grows with tenants who rarely query. Each tenant's
source documents live in Backblaze B2 under `rag/corpus/<tenant>/`, and each
tenant has one Qdrant collection. Hot tenants are served from a local Qdrant
node. A tiering policy finds tenants idle longer than a threshold, snapshots
their collection through Qdrant's snapshot API, streams the snapshot to B2 with
a multipart upload, writes a `latest.json` manifest last, verifies the upload
against that manifest, and only then drops the collection from the node. The
first query for a parked tenant downloads the latest snapshot from B2 and loads
it into a Qdrant node (including one that has never seen the tenant) through
Qdrant's snapshot upload API, then answers. Every warm query, restore and
post-restore query is timed, and a benchmark run writes
`rag/reports/<run-id>/report.json` with warm latency, restore time,
post-restore latency and memory freed per tenant. It is for platform and ML
engineers who run RAG for many customers and want to set a parking threshold
on measured numbers rather than guesses. B2 is the durable tier: snapshots and
corpora accumulate there for every tenant while vector memory is spent only on
hot tenants.

## 2. Architecture delta from the starter kit

Layering stays the kit's (`types -> config -> repo -> service -> runtime`,
enforced by `tests/test_structure.py`). All Qdrant HTTP and all boto3 code live
in `services/api/app/repo/`.

| Keep (as is or lightly adapted) | Trim (remove) | Add |
|---|---|---|
| Monorepo layout, pnpm workspaces, `scripts/*` (doctor, setup, dev, gen-api, gen-docs, check-agent-docs, wait-ready) | `apps/web/src/app/upload/` page and `components/upload/*` | `docker-compose.yml` (qdrant pinned, api, web), `services/api/Dockerfile`, `apps/web/Dockerfile`, `.dockerignore` |
| `app/repo/b2_client.py` (client factory, list, head, delete, listing cache) | `lib/upload-queue-context.tsx`, `lib/upload-file-types.ts`, `lib/upload-status.ts` and their tests | `app/repo/qdrant_gateway.py`: collection create/info/delete, upsert, search, snapshot create/download stream/delete, snapshot upload (restore), node memory metric |
| **Bucket explorer** `/files` (`components/files/*`, `lib/file-tree.ts`): full-bucket browse, kept non-removable | `app/runtime/upload.py`, `app/service/upload.py`, `app/repo/b2_upload.py`, `app/types/upload.py`, `tests/test_upload_*.py` | `app/repo/snapshot_store.py`: multipart streaming upload with running sha256, manifest put/get, verify (head size + streamed re-read sha256), snapshot download stream, prefix-scoped delete |
| Health route (extended with Qdrant status), metrics, rate limit, error types, structured logging | Presigned PUT and presigned GET usage (`get_presigned_url`), see section 3: browser traffic to B2 would not carry the custom user agent | `app/repo/embedder.py`: fastembed wrapper, model load once, device autodetect |
| Dashboard route `/` (rewritten for tiering) and `components/dashboard/*` structure | `services/api/scripts/setup_b2_cors.py` (the code must not apply bucket configuration) | `app/service/tenants.py` (CRUD + ingest), `app/service/tiering.py` (policy + park state machine), `app/service/restore.py`, `app/service/reports.py` (benchmark + report writer), `app/service/seed.py` (synthetic corpus), `app/service/prune.py` |
| Settings page and `settings-form.tsx` (theme kept; demo preference fields replaced by a read-only view of the tiering policy) | Metadata extraction (Pillow, pypdf, `service/metadata.py`, `docs/features/metadata-extraction.md`, its tests); the file detail panel keeps the basic head-object fields | `app/runtime/tenants.py`, `app/runtime/tiering.py`, `app/runtime/reports.py`, `app/runtime/library.py` routers |
| `/design` reference page, `components/ui/*`, layout, command palette, theme | `infra/vercel/`, `infra/railway/`, root and service `vercel.json`, `railway.json`, `services/api/index.py`, `tests/test_vercel_entrypoint.py` (the app needs a Qdrant node and a CPU embedding model; it runs in Docker Compose, not on serverless) | `app/types/tenants.py`, `tiering.py`, `reports.py`, `library.py` Pydantic models |
| `docs/` skeleton, generators, `docs/api/openapi.json` (regenerated) | `apps/web/e2e/upload.spec.ts` (replaced) | Web: `/tenants`, `/tenants/[tenantId]`, `/reports`, `/reports/[runId]`, `/library` pages and components |
| CI workflow (adapted: drop deploy-specific steps, keep verify) | | **Library** asset explorer `/library`: scoped to `rag/`, grouped by tenant and kind (corpus, snapshots, reports) |
| | | `services/api/live_tests/test_e2e_tiering.py` (Docker + B2 end-to-end), offline unit tests listed in section 4 |
| | | Background tiering sweep (asyncio task started in `lifespan`, interval configurable, 0 disables) |

Tension note: the bucket explorer stays even though the Library view covers the
app's own objects. It is the kit's non-removable full-bucket browse and also
the place to inspect objects the app did not write.

### Runtime topology

`docker compose up` starts:

- `qdrant`: `qdrant/qdrant:v1.20.2`, the newest stable release at scaffold time
  (never `latest`), with `qdrant-client` pinned to the matching 1.20 minor. Named volume for storage, port 6333.
- `api`: FastAPI on Python 3.12, `QDRANT_URL=http://qdrant:6333`, a named volume
  for the fastembed model cache, reads the repo-root `.env`.
- `web`: Next.js production build, `NEXT_PUBLIC_API_URL` set at build time.

Local dev without Compose still works: `docker compose up qdrant` plus
`pnpm dev`.

### Tenant state (derived, not stored twice)

- `hot`: the collection `tenant_<tenant_id>` exists on the node.
- `parked`: no collection on the node, and `rag/snapshots/<tenant>/latest.json`
  exists in B2.
- `empty`: tenant metadata exists, no collection, no snapshot (created but not
  ingested; ingest makes it hot).
- Transitional, in memory only: `snapshotting`, `verifying`, `restoring`.

A per-tenant `asyncio.Lock` serialises park, restore, edit, delete and query, so
a query that arrives during a park waits and then restores if needed. Last
query time is kept in memory; after a backend restart the idle clock starts
from startup, which can only delay parking, never park early.

Tenant metadata (display name, created time, document list) lives at
`rag/corpus/<tenant>/_tenant.json`; documents at
`rag/corpus/<tenant>/<filename>`.

### Park state machine (the safety rule)

1. `POST /collections/tenant_<t>/snapshots` on Qdrant, read the returned name,
   size and sha256 checksum.
2. Stream `GET /collections/tenant_<t>/snapshots/<name>` into a B2 multipart
   upload at `rag/snapshots/<t>/<snapshot-id>.snapshot`
   (`create_multipart_upload`, `upload_part` with `SNAPSHOT_PART_SIZE_BYTES`,
   default 8 MiB, minimum 5 MiB except the last part, `complete_multipart_upload`;
   `abort_multipart_upload` on any failure), hashing sha256 while streaming.
   The streamed hash must equal Qdrant's checksum.
3. Write `rag/snapshots/<t>/latest.json` LAST:
   `{tenant_id, snapshot_key, snapshot_id, size_bytes, point_count,
   sha256, vector_size, distance, embedding_model, qdrant_version, created_at}`.
4. Verify: `head_object` size equals manifest `size_bytes`, then re-read the
   object from B2 as a stream and recompute sha256, which must equal the
   manifest `sha256`.
5. Only if step 4 passes: delete the collection and the node-local snapshot
   file; tenant becomes `parked`. Any failure in 1 to 4 leaves the tenant hot,
   logs the reason, and the tiering result lists it under `skipped` with that
   reason. A previously good `latest.json` is never overwritten before the new
   snapshot object has been fully uploaded.

### Restore

Under the tenant lock: read `latest.json`, stream the snapshot object from B2
(`get_object`) into Qdrant's
`POST /collections/tenant_<t>/snapshots/upload?priority=snapshot` (multipart
form, streamed from a spooled temp file), then check the collection's point
count equals the manifest `point_count`. Timings recorded: download ms, load ms,
total ms. Works against any `QDRANT_URL`, including a node with empty storage.
Qdrant's "recover from URL" is deliberately not used: it would make Qdrant fetch
from B2 itself, outside the backend's boto3 client.

### Memory freed

Reported two ways per tenant, both in the report:

- `vector_bytes_estimate`: `points * vector_size * 4` plus the payload bytes from
  collection info (deterministic, what the dashboard sums).
- `node_rss_delta_bytes`: the node's resident memory from Qdrant's `/metrics`
  before and after the drop. Labelled "observed" in the UI and nullable, because
  the allocator may not return memory immediately and the metric name must be
  verified against the pinned version.

## 3. B2 surface

All B2 traffic goes through the backend's single boto3 client built in
`app/repo/b2_client.py` with
`Config(user_agent_extra="b2ai-qdrant-multitenant-rag-tiering")`. Endpoint is
derived from `B2_REGION` (`https://s3.<region>.backblazeb2.com`). No b2-native
API call anywhere in source. No presigned URLs are handed to the browser, so
file preview and download in the bucket explorer are proxied by the backend.
No bucket configuration (lifecycle, CORS, Object Lock) is applied by the code.

| Operation | Why |
|---|---|
| `put_object` | tenant documents, `_tenant.json`, `latest.json` (written last), `report.json` |
| `create_multipart_upload` / `upload_part` / `complete_multipart_upload` / `abort_multipart_upload` | stream a Qdrant snapshot to B2 without holding it in memory |
| `head_object` | verify snapshot size against the manifest; `/health` probe via `head_bucket`; file metadata |
| `get_object` | re-read snapshot for checksum verification; download snapshot for restore; read corpus, manifests and reports; proxy file preview and download |
| `list_objects_v2` | bucket explorer, Library view, tenant discovery, snapshot history, report list |
| `delete_object` / `delete_objects` | bucket explorer delete; tenant delete (scoped to that tenant's corpus and snapshot prefixes); snapshot prune when explicitly applied; end-to-end test cleanup of only the keys the run wrote |

All app keys live under `RAG_PREFIX` (default `rag/`). The end-to-end test sets
`RAG_PREFIX=e2e/<run-id>/rag/`.

### API endpoints (the single list)

Kept from the kit: `GET /health` (adds `qdrant: {ok, version}`), `GET /metrics`,
`GET /files`, `GET /files/stats`, `GET /files/stats/activity`,
`GET /files-by-key/metadata`, `GET /files-by-key/detail`, `DELETE /files-by-key`,
and the `/files/{key:path}` equivalents.

Changed: `GET /files-by-key/download` and `GET /files-by-key/preview` (and their
`/files/{key:path}/...` equivalents) keep `FileUrlResponse` but return a backend
URL to the new content route instead of a presigned B2 URL.

Removed: `POST /upload/presign`, `POST /upload/verify`.

Added:

| Path | Method | Request model | Response model |
|---|---|---|---|
| `/files-by-key/content` | GET | query `key`, `disposition` (`attachment`/`inline`) | streamed bytes |
| `/tenants` | GET | none | `list[TenantSummary]` |
| `/tenants` | POST | `TenantCreate {tenant_id, display_name, documents: list[DocumentIn{filename, text}]}` | `TenantDetail` (201) |
| `/tenants/seed` | POST | `SeedRequest {tenant_count: 2..6 = 4}` | `SeedResult {created, skipped}` |
| `/tenants/{tenant_id}` | GET | none | `TenantDetail` |
| `/tenants/{tenant_id}` | PATCH | `TenantUpdate {display_name?, add_documents?: list[DocumentIn], remove_documents?: list[str]}` | `TenantDetail` (restores first if parked, re-embeds changed docs, marks snapshot stale) |
| `/tenants/{tenant_id}` | DELETE | query `confirm` must equal `tenant_id` | `DeleteTenantResult {deleted_keys, collection_dropped}` |
| `/tenants/{tenant_id}/query` | POST | `QueryRequest {query, top_k: 1..20 = 5}` | `QueryResponse {hits: list[QueryHit{doc, chunk, score, text}], latency_ms, restored, restore: RestoreTiming?}` |
| `/tenants/{tenant_id}/park` | POST | none | `ParkResult {tenant_id, state, manifest: SnapshotManifest?, verified, reason?}` |
| `/tenants/{tenant_id}/restore` | POST | none | `RestoreResult {tenant_id, state, timing: RestoreTiming, point_count}` |
| `/tenants/{tenant_id}/snapshots` | GET | none | `list[SnapshotEntry {key, size_bytes, created_at, is_latest}]` |
| `/tiering/policy` | GET | none | `TieringPolicy {idle_seconds, sweep_interval_seconds, prune_enabled}` |
| `/tiering/run` | POST | `TieringRunRequest {idle_seconds?, dry_run: bool = true}` | `TieringRunResult {candidates, parked, skipped: list[{tenant_id, reason}], dry_run}` |
| `/tiering/stats` | GET | none | `TieringStats {hot, parked, empty, vector_bytes_hot, vector_bytes_freed, snapshot_bytes_b2, corpus_bytes_b2}` |
| `/snapshots/prune` | POST | `PruneRequest {keep_last: 1..5 = 1, apply: bool = false}` | `PruneResult {enabled, applied, candidates: list[str], deleted: list[str]}` (409 when `SNAPSHOT_PRUNE_ENABLED` is false; never deletes the key in `latest.json`) |
| `/reports` | POST | `BenchmarkRequest {tenant_ids: list[str] (1..6), queries_per_phase: 5/10/20 = 10}` | `LatencyReport` |
| `/reports` | GET | none | `list[ReportSummary {run_id, created_at, tenant_count}]` |
| `/reports/{run_id}` | GET | none | `LatencyReport` |
| `/library` | GET | query `tenant_id?`, `kind?` (`corpus`/`snapshots`/`reports`) | `list[LibraryEntry {key, tenant_id, kind, size_bytes, last_modified}]` |

`LatencyReport`: `{run_id, created_at, qdrant_version, embedding_model,
tenants: [{tenant_id, point_count, warm: LatencyStats{n, p50_ms, p95_ms,
mean_ms}, snapshot_bytes, snapshot_upload_ms, restore: RestoreTiming{download_ms,
load_ms, total_ms}, first_query_after_restore_ms, post_restore: LatencyStats,
memory_freed: {vector_bytes_estimate, node_rss_delta_bytes?}, results_match}]}`.
A benchmark per tenant: run the fixed probe queries warm, record hits; park;
restore; run the same queries; compare hit ids and scores (tolerance 1e-4);
write `rag/reports/<run-id>/report.json`.

## 4. Key features

- **Tenants**: create a tenant from uploaded text or Markdown files, or seed four
  synthetic tenants; documents land in `rag/corpus/<tenant>/` and are chunked and
  embedded into one Qdrant collection per tenant. Doc: `docs/features/tenants.md`.
- **Tiering policy and parking**: idle detection, snapshot, multipart upload,
  manifest-last, verify, then drop. Manual park per tenant; dry run by default
  for a policy sweep. Doc: `docs/features/tiering.md`.
- **Restore on query**: the first query to a parked tenant restores it from B2
  into the current node and reports the restore cost inline. Doc:
  `docs/features/restore.md`.
- **Latency report**: benchmark run with warm, restore and post-restore figures
  and memory freed, charted on `/reports/[runId]`. Doc:
  `docs/features/latency-report.md`.
- **Library**: asset explorer scoped to `rag/`, grouped by tenant and kind. Doc:
  `docs/features/library.md`.
- **Bucket explorer** (kept from the kit) and **Dashboard** (rewritten). Docs:
  `docs/features/file-browser.md`, `docs/features/dashboard.md`.

### Local model (no external API)

| Feature | Provider / model | deployment | Est. cost per demo run | Key env var |
|---|---|---|---|---|
| Embeddings (ingest, query) | `fastembed` with `BAAI/bge-small-en-v1.5` (ONNX, 384 dimensions, about 67 MB download from the Hugging Face Hub, no account or key) | local | $0 | none |

Device rule: CPU by default; at startup pick CUDA if `onnxruntime` reports
`CUDAExecutionProvider` (needs `fastembed-gpu`, documented as optional), else
CPU. onnxruntime has no MPS provider, so on Apple silicon this sample falls back
CUDA -> CPU; the model is small enough that CPU is the intended path. The README
names the model, its size and where it is cached. `EMBEDDING_MODEL` env var
allows another fastembed model; vector size is read from the model, and
`latest.json` records it so a restore into a different model configuration
fails with a clear error instead of returning wrong results.

No Genblaze: the description names no Genblaze stack and there are no AI
provider calls.

### Primary entity: Tenant (lifecycle in the UI)

| Verb | UI |
|---|---|
| create | `/tenants` "New tenant" dialog (form) plus "Seed demo tenants" button |
| read | `/tenants` table (state badge, points, last query, snapshot size) and `/tenants/[tenantId]` detail |
| edit | `/tenants/[tenantId]` "Edit" sheet: display name, add documents, remove documents |
| delete | `/tenants/[tenantId]` danger zone, `AlertDialog` that requires typing the tenant id; deletes only that tenant's collection and `rag/corpus/<t>/`, `rag/snapshots/<t>/` objects; reports are kept |
| run | query box on the detail page (auto-restores), "Park now", "Restore now", plus `/tiering` sweep and `/reports` benchmark run |

No verb is omitted.

### Form UX conventions

Create tenant form:

| Field | Control | Default hint (placeholder / FormDescription) |
|---|---|---|
| `tenant_id` | text input (free-form identifier) | placeholder `acme-legal`; "lowercase letters, digits and hyphens, 2 to 40 characters" |
| `display_name` | text input | placeholder `Acme Legal` |
| `documents` | file input, `.txt` and `.md` | "Two to twenty short text files is enough for a test run; or use Seed demo tenants" |

Edit tenant form (pre-filled): display name text input; documents to remove as
a checkbox list (finite set: current documents); add documents file input.

Other forms:

| Form | Field | Control | Default |
|---|---|---|---|
| Query | `top_k` | `Select` 3 / 5 / 10 | 5 |
| Tiering run | `idle_seconds` | `Select` 30 s / 5 min / 1 h / 1 day / 7 days | policy value |
| Tiering run | `dry_run` | `Switch` | on |
| Benchmark | `tenant_ids` | checkbox list of existing tenants | first hot tenant |
| Benchmark | `queries_per_phase` | `Select` 5 / 10 / 20 | 10 |
| Seed | `tenant_count` | `Select` 2 / 4 / 6 | 4 |
| Prune | `keep_last` | `Select` 1 / 2 / 3 | 1 |
| Prune | `apply` | `Switch` | off (dry run) |

`settings-form.tsx` is the in-repo exemplar for both rules.

### Configuration (new env vars, all optional)

| Name | Default | Note |
|---|---|---|
| `QDRANT_URL` | `http://localhost:6333` | Compose sets `http://qdrant:6333` |
| `RAG_PREFIX` | `rag/` | key prefix for everything the app writes |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | any fastembed text model |
| `TIERING_IDLE_SECONDS` | `604800` (7 days) | tests use seconds |
| `TIERING_SWEEP_INTERVAL_SECONDS` | `300` | `0` disables the background sweep |
| `SNAPSHOT_PART_SIZE_BYTES` | `8388608` | at least 5 MiB |
| `SNAPSHOT_PRUNE_ENABLED` | `false` | prune also requires `apply=true` per call |

### Tests

Offline unit tests (`services/api/tests/`, no network, stubbed storage and a fake
Qdrant gateway behind the same interfaces as the real repo modules):

- `test_tiering_policy.py`: idle selection by last query time, threshold edges,
  `empty` and already parked tenants excluded, dry run parks nothing.
- `test_snapshot_manifest.py`: manifest round trip, required fields, written
  after the snapshot object (order asserted on the fake store), checksum and
  size mismatch detection.
- `test_park_restore_state_machine.py`: park succeeds only after verification;
  upload failure, size mismatch and checksum mismatch each leave the collection
  in place and the tenant hot with no new `latest.json`; restore loads the
  snapshot and checks point count; query on a parked tenant restores first;
  concurrent query during park waits on the lock.
- `test_prune.py`: disabled returns 409 with no deletes; enabled without `apply`
  deletes nothing; never deletes the `latest.json` target.
- `test_tenant_crud.py`, `test_tenant_id_validation.py`, `test_report_writer.py`,
  `test_content_proxy.py`, `test_user_agent.py` (client config carries
  `b2ai-qdrant-multitenant-rag-tiering`), plus the kit's retained tests.
- Web: vitest for new libs (state badge mapping, report chart data shaping).

End-to-end (`services/api/live_tests/test_e2e_tiering.py`, marker `e2e`, run
with `pnpm test:e2e:tiering`): requires Docker and real B2 credentials. Starts a
Qdrant container (pinned image, random port, empty storage), sets
`RAG_PREFIX=e2e/<uuid>/rag/`, ingests a small corpus for two tenants, records
query results, parks one tenant via the policy with a seconds-level idle
threshold, starts a second fresh Qdrant container, restores into it, asserts the
same queries return the same hit ids and scores, runs a benchmark and asserts
`report.json` exists with warm and post-restore figures, then deletes only the
keys the run recorded as written and asserts the run prefix is empty, and
removes both containers. Playwright `e2e/tenants.spec.ts` replaces the upload
spec (seed, query, park, query restores).

Validation: a person runs the demo and reviews the latency report (warm and
post-restore figures) on `/reports/[runId]`.

## 5. Doc transforms

- Rewrite: `README.md` (generator regions plus hand-written: what it shows,
  Compose quickstart, model name and size, how tiering works, the safety rule,
  reading the report, "Alternative: Qdrant's built-in S3 snapshot storage"
  section showing `storage.snapshots_config.snapshots_storage: s3` with
  `s3_config` pointed at `https://s3.<region>.backblazeb2.com`, noting those
  requests carry Qdrant's own user agent and are not the path the tests use),
  `ARCHITECTURE.md`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `PRODUCT.md`,
  `docs/app-workflows.md`, `docs/features/dashboard.md`,
  `docs/features/file-browser.md` (proxied preview/download),
  `docs/features/settings.md`, `docs/SECURITY.md` (no presigned URLs, prefix
  confinement, delete confirmation), `docs/RELIABILITY.md` (verify-before-park,
  manifest-last), `docs/verification.md` (e2e command), `docs/dev-workflows.md`.
- Delete: `docs/features/file-upload.md`, `docs/features/metadata-extraction.md`,
  `infra/vercel/README.md`, `infra/railway/README.md`.
- New stubs: `docs/features/tenants.md`, `tiering.md`, `restore.md`,
  `latency-report.md`, `library.md` from `docs/features/_template.md`.

### Declared identity (`docs/exec-plans/sample.json`)

| Field | Value |
|---|---|
| `schema_version` | `1` |
| `name` | `Qdrant Multitenant RAG Tiering` |
| `slug` | `qdrant-multitenant-rag-tiering` |
| `package_scope` | `@qdrant-multitenant-rag-tiering` |
| `purpose` | "A multi-tenant RAG service that serves hot tenants from Qdrant, parks idle tenants' collections as verified snapshots in Backblaze B2, restores them on the next query, and measures what that costs in latency and saves in memory." |
| `tagline` | "Keep vector memory for the tenants who query; park the rest in B2." |
| `primary_entity` | `{schema: "TenantDetail", singular: "tenant", plural: "tenants"}` |
| `features` | Tenants `/tenants`, Tiering `/tenants` (route of the sweep dialog), Restore on query `null`, Latency report `/reports`, Library `/library`, Bucket explorer `/files`, Dashboard `/`, Settings `/settings`, each with its doc path above |
| `b2_surface` | the operations table in section 3 |
| `b2_key_prefix` | `rag/` |
| `stack` | web: Next.js 16, React 19, Tailwind v4, shadcn/ui, TanStack Query, Recharts; api: FastAPI, Python 3.12, boto3, qdrant-client, fastembed, Pydantic v2; storage: Backblaze B2 (S3-compatible API) with Qdrant (pinned) as the hot tier; package_manager: pnpm workspaces |
| `deployment_targets` | `[]` (Docker Compose only; `scripts/gen-docs.mjs` generates infra runbooks only for declared targets) |
| `env_vars` | the four required `B2_*`, `B2_PUBLIC_URL_BASE` optional, `NEXT_PUBLIC_API_URL` optional, and the seven optional vars in the configuration table |
| `attribution_token` | `b2ai-qdrant-multitenant-rag-tiering` |
| `repo` | `{org: "backblaze-b2-samples", name: "qdrant-multitenant-rag-tiering"}` |
| `screenshots` | `[]` |

This file is written before `pnpm gen:docs` runs, because the generator reads it.

## 6. Rename table

| From | To |
|---|---|
| `vibe-coding-starter-kit` (package names, `app_slug`, comments, file-tree and query namespaces, `next.config.ts`, SECURITY and dev-workflows docs) | `qdrant-multitenant-rag-tiering` |
| `@vibe-coding-starter-kit/web`, `@vibe-coding-starter-kit/shared`, every `pnpm --filter` | `@qdrant-multitenant-rag-tiering/web`, `@qdrant-multitenant-rag-tiering/shared` |
| `Vibe Coding Starter Kit` (`APP_NAME`, `API_TITLE`, `API_DESCRIPTION`, branding check, openapi title) | `Qdrant Multitenant RAG Tiering` |
| `vibe_coding_starter_kit` (any snake case) | `qdrant_multitenant_rag_tiering` |
| `user_agent_extra="b2ai-oss-start"` | `user_agent_extra="b2ai-qdrant-multitenant-rag-tiering"` |
| `utm_content=b2ai-oss-start` (README, sidebar, doctor) | `utm_content=b2ai-qdrant-multitenant-rag-tiering` |
| Compose image tags / service names | `qdrant-multitenant-rag-tiering-api`, `qdrant-multitenant-rag-tiering-web` |
| CI workflow name | `qdrant-multitenant-rag-tiering CI` |
| `.env.example` | keeps the four required `B2_*` names, `B2_PUBLIC_URL_BASE` commented, adds the optional vars commented with their defaults |
