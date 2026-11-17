<!-- last_verified: 2026-11-17 -->
# Architecture

## Components

<!-- gen:begin arch-components -->
A multi-tenant RAG service that serves hot tenants from Qdrant, parks idle tenants' collections as verified snapshots in Backblaze B2, restores them on the next query, and measures what that costs in latency and saves in memory.

- **apps/web/**: Next.js 16, React 19, Tailwind v4, shadcn/ui, TanStack Query, Recharts
  - Tenants (`/tenants`): create tenants from text or Markdown files (or seed demo tenants), one Qdrant collection each, corpus in B2
  - Tiering (`/tenants`): idle policy and manual park (snapshot, multipart upload to B2, manifest last, verify, then drop)
  - Latency report (`/reports`): benchmark warm, restore and post-restore latency plus memory freed, stored as report.json in B2
  - Library (`/library`): the app's own objects under rag/, grouped by tenant and kind
  - Bucket explorer (`/files`): full-bucket browse, preview, download and delete, streamed through the API
  - Dashboard (`/`): hot, parked and empty counts, vector memory in use and freed, bytes in B2, recent reports
  - Settings (`/settings`): read-only tiering policy and the browser theme
- **services/api/**: FastAPI, Python 3.12, boto3, qdrant-client, fastembed, Pydantic v2
  - REST API for every operation the frontend consumes, exported to `docs/api/openapi.json`
  - Backblaze B2 (S3-compatible API) with Qdrant v1.20.2 as the hot tier access isolated in the `repo/` layer
  - Restore on query: the first query to a parked tenant restores it from B2 into any Qdrant node and reports the cost
  - Structured JSON logging with request tracing, plus `/health` and Prometheus `/metrics`
- **packages/shared/**: TypeScript types generated from the API contract by `pnpm gen:api`, consumed by `apps/web/` as a workspace dependency (pnpm workspaces)
<!-- gen:end arch-components -->

## Runtime Topology

`docker compose up --build` starts three containers:

| Service | Image | Port | Role |
| --- | --- | --- | --- |
| `qdrant` | `qdrant/qdrant:v1.20.2` (pinned) | 6333 | Hot tier: one collection per hot tenant, named volume for storage |
| `api` | `qdrant-multitenant-rag-tiering-api` (Python 3.12) | 8000 | FastAPI; `QDRANT_URL=http://qdrant:6333`; fastembed model cache on a named volume; reads the repo-root env file |
| `web` | `qdrant-multitenant-rag-tiering-web` | 3000 | Next.js production build; `NEXT_PUBLIC_API_URL` set at build time |

Local development without Compose: `docker compose up qdrant` plus `pnpm dev`.

```
Browser ──> web (Next.js) ──> api (FastAPI) ──┬──> Qdrant node    hot tenants: tenant_<id> collections
                                              └──> Backblaze B2   corpus, snapshots, manifests, reports
                                                   (one boto3 client, user agent b2ai-qdrant-multitenant-rag-tiering)
```

The API is the only component that talks to B2. Snapshots move between Qdrant and
B2 through the API as byte streams; Qdrant never fetches from B2 itself.

## Backend Layering

The API follows a strict layered architecture:

```
types/     Pydantic models and the adapter ports (Protocols), no logic
  |
config/    Settings (pydantic-settings): depends only on types
  |
repo/      Adapters: boto3 (B2), qdrant-client + httpx (Qdrant), fastembed
  |
service/   Business logic: tenants, ingest, tiering, restore, reports, prune
  |
runtime/   FastAPI routes: call service, never repo directly
```

### Layering Rules

1. Dependencies flow downward only: `types` -> `config` -> `repo` -> `service` -> `runtime`
2. No backward imports (e.g., service must not import from runtime)
3. `boto3`, `qdrant_client`, `httpx`, `fastembed` and `onnxruntime` only in `repo/`
4. All boundary data uses Pydantic models or the frozen dataclasses in `app/types/ports.py`
5. Authored Python files under `services/api/app/` stay under 300 lines

Services reach the three adapters through `app/service/deps.py`, which builds them
lazily and is the single place B2 keys and collection names are formed. The
offline tests install in-memory fakes behind the same ports, so the park state
machine, manifest ordering and verification run unchanged against either.

### Directory Structure

<!-- gen:begin arch-directory -->
```
services/api/
  main.py                  App entrypoint, middleware, router registration
  app/
    types/                 Pydantic models, and the response-model base
    config/                Settings loaded from environment
    repo/                  B2 S3 client (data access layer)
    service/               Business logic
    runtime/               FastAPI route handlers
  scripts/                 Operational scripts (OpenAPI export, bucket CORS)
  tests/                   pytest tests (structural + integration)
```
<!-- gen:end arch-directory -->

## Tenant State

State is derived from what exists, never stored twice:

| State | Meaning |
| --- | --- |
| `hot` | collection `tenant_<id>` exists on the node |
| `parked` | no collection, and `rag/snapshots/<id>/latest.json` exists in B2 |
| `empty` | `_tenant.json` exists but nothing is indexed and no snapshot exists |
| `writing` / `embedding` / `upserting` | in memory only, while a create (or re-indexing edit) runs |
| `snapshotting` / `uploading` / `verifying` / `dropping` / `restoring` | in memory only, while a park (in that order) or restore runs |

A per-tenant `asyncio.Lock` (`app/service/state.py`) serialises park, restore,
edit, delete and query. Idle clocks are in memory; after a restart every clock
starts at process start, which can only delay parking, never park early.

## Data Flows

- **Create**: `POST /tenants` -> documents to `rag/corpus/<t>/`, `_tenant.json`, then chunk (120 words), embed (fastembed), upsert into `tenant_<t>`.
- **Query**: `POST /tenants/<t>/query` -> lock -> restore if parked -> embed query -> Qdrant search -> hits with `latency_ms` (and restore timing when it restored).
- **Park** (manual, sweep, or benchmark): Qdrant snapshot -> streamed `GET` into a B2 multipart upload hashed on the way (must equal Qdrant's checksum) -> `latest.json` written LAST -> `head_object` size + streamed re-read sha256 against the manifest -> only then delete the node snapshot and drop the collection. Any failure leaves the tenant hot and restores the previous manifest. See [docs/features/tiering.md](docs/features/tiering.md).
- **Restore**: `get_object` streamed into a spooled temp file (hashed against the manifest) -> `POST /collections/<c>/snapshots/upload?priority=snapshot&checksum=…` -> point count must equal the manifest. Works on a node with empty storage.
- **Benchmark**: warm probes -> park -> first query restores -> same probes -> compare -> `rag/reports/<run-id>/report.json`.
- **Bucket explorer**: list/head/delete through the shared listing cache; preview and download stream bytes through `GET /files-by-key/content`.

## Boundary Invariants

- **No external SDK leakage**: every third-party client lives in `app/repo/`, asserted by `tests/test_structure.py`.
- **No raw dicts at boundaries**: data crossing layers uses Pydantic models or the port dataclasses.
- **No cross-layer mutable state**: configuration is read-only after init. Intra-layer state (listing cache, B2 connectivity cache, download counter, rate-limit and metrics state, and the per-tenant locks and clocks in `service/state.py`) is module-local.
- **Background work**: the listing cache's refresh thread, the embedder warm-up thread, and the tiering sweep task started in `main.lifespan` (cancelled on shutdown; `TIERING_SWEEP_INTERVAL_SECONDS=0` disables it).
- **Validated inputs**: tenant ids, document names and run ids are validated before they become keys; file keys reject empty and path-traversal patterns; every app write stays under `RAG_PREFIX`.

## Deployment

- **Docker Compose**: the supported way to run the full stack (see Runtime Topology).
- **Local dev**: `docker compose up qdrant` and `pnpm dev` (web on `localhost:3000`, API on `localhost:8000`).
- No hosted delivery contract ships: the app needs a Qdrant node and a CPU
  embedding model, which serverless platforms do not host. External provisioning
  and deployment remain explicit user-approved actions.

## Data Stores

<!-- gen:begin arch-data-stores -->
- **Backblaze B2 (S3-compatible API) with Qdrant v1.20.2 as the hot tier**: the only data store; there is no application database
  - Every object this app writes lives under the `rag/` key prefix of one bucket
  - Listing, per-key metadata and presigned URLs all come from the S3 surface below
  - The primary entity is `TenantDetail`; one tenant is one object
<!-- gen:end arch-data-stores -->

## External Services

<!-- gen:begin arch-external-services -->
- **Backblaze B2 (S3-compatible API) with Qdrant v1.20.2 as the hot tier**: reached only through `services/api/app/repo/`, using:
  - `put_object`: tenant documents, _tenant.json, latest.json (written last) and report.json
  - `create_multipart_upload / upload_part / complete_multipart_upload / abort_multipart_upload`: stream a Qdrant snapshot to B2 without holding it in memory; abort on any failure so no partial object appears
  - `head_object`: verify snapshot size against the manifest, the /health probe (head_bucket) and file metadata
  - `get_object`: re-read a snapshot to verify its sha256, download it for restore, read corpus, manifests and reports, and proxy preview and download
  - `list_objects_v2`: bucket explorer, Library view, tenant discovery, snapshot history and report list
  - `delete_object / delete_objects`: bucket explorer delete, tenant delete scoped to its corpus and snapshot prefixes, opt-in snapshot prune, end-to-end test cleanup
<!-- gen:end arch-external-services -->

## Trust Boundaries

See [docs/SECURITY.md](docs/SECURITY.md) for full security documentation.

- **Frontend -> API**: CORS-restricted to configured origins (`GET/POST/PATCH/DELETE/OPTIONS`). `CORSMiddleware` is registered LAST in `main.py` (outermost) so it wraps **every** response, including uncaught-exception 500s. See [docs/RELIABILITY.md](docs/RELIABILITY.md#error-handling). A per-IP rate-limit middleware sits inner to CORS; see [docs/SECURITY.md](docs/SECURITY.md#rate-limiting).
- **API -> B2**: application key, signature v4, custom user agent on every request.
- **API -> Qdrant**: plain HTTP to `QDRANT_URL` on the Compose network; no API key is configured for the local node.
- **Browser -> B2**: none. No presigned URLs are issued; preview and download are proxied.

## Observability

- Structured JSON logging on all requests with `request_id`; park aborts log their reason at WARNING
- Request timing middleware (also the catch-all that converts uncaught exceptions to a typed JSON 500)
- `/metrics` (Prometheus format: request count, latency, `tenant_parks_total`, `tenant_restores_total`)
- `/health` (B2 connectivity and Qdrant reachability with its version)
- Latency reports in B2 (`rag/reports/<run-id>/report.json`)

## API Contract

<!-- gen:begin arch-api-contract -->
- Checked-in OpenAPI artifact: `docs/api/openapi.json`
- Export / check: `pnpm contract:export` / `pnpm contract:check`
- Generate the client seam from it: `pnpm gen:api` (drift gate: `pnpm gen:check`)
- FastAPI freshness test: `services/api/tests/test_openapi_contract.py`
- Frontend route drift test: `apps/web/src/lib/api-contract.test.ts`

The FastAPI routers and Pydantic models are the single source of truth. The
frontend's `API_CLIENT_ROUTES` registry, the `qk` query-key factory and the
shared TypeScript types are **generated** from the exported artifact by
`pnpm gen:api`, so the client cannot drift from the backend: there is no
hand-written copy left to disagree. The two contract tests are kept as a
belt-and-braces check that the generated files and the committed artifact are
still in step.

| Route | Returns | Generated client route |
| --- | --- | --- |
| `DELETE /files-by-key` | `DeleteFileResponse` | `fileByKeyDelete` |
| `DELETE /files/{key}` | `DeleteFileResponse` | `legacyFileDelete` |
| `DELETE /tenants/{tenant_id}` | `DeleteTenantResult` | `tenantDelete` |
| `GET /files` | `FileMetadata[]` | `files` |
| `GET /files-by-key/content` | n/a | `fileByKeyContent` |
| `GET /files-by-key/detail` | `FileMetadataDetail` | `fileByKeyDetail` |
| `GET /files-by-key/download` | `FileUrlResponse` | `fileByKeyDownload` |
| `GET /files-by-key/metadata` | `FileMetadata` | `fileByKeyMetadata` |
| `GET /files-by-key/preview` | `FileUrlResponse` | `fileByKeyPreview` |
| `GET /files/{key}` | `FileMetadata` | `legacyFileMetadata` |
| `GET /files/{key}/download` | `FileUrlResponse` | `legacyFileDownload` |
| `GET /files/{key}/preview` | `FileUrlResponse` | `legacyFilePreview` |
| `GET /files/stats` | `UploadStats` | `fileStats` |
| `GET /files/stats/activity` | `DailyUploadCount[]` | `uploadActivity` |
| `GET /health` | `HealthStatus` | `health` |
| `GET /library` | `LibraryEntry[]` | `library` |
| `GET /metrics` | n/a | _server-only_ |
| `GET /reports` | `ReportSummary[]` | `reports` |
| `GET /reports/{run_id}` | `LatencyReport` | `reportDetail` |
| `GET /reports/progress` | `BenchmarkProgress` | `reportProgress` |
| `GET /tenants` | `TenantSummary[]` | `tenants` |
| `GET /tenants/{tenant_id}` | `TenantDetail` | `tenantDetail` |
| `GET /tenants/{tenant_id}/progress` | `TenantProgress` | `tenantProgress` |
| `GET /tenants/{tenant_id}/snapshots` | `SnapshotEntry[]` | `tenantSnapshots` |
| `GET /tiering/policy` | `TieringPolicy` | `tieringPolicy` |
| `GET /tiering/stats` | `TieringStats` | `tieringStats` |
| `PATCH /tenants/{tenant_id}` | `TenantDetail` | `tenantUpdate` |
| `POST /reports` | `LatencyReport` | `reportRun` |
| `POST /snapshots/prune` | `PruneResult` | `snapshotsPrune` |
| `POST /tenants` | n/a | `tenantCreate` |
| `POST /tenants/{tenant_id}/park` | `ParkResult` | `tenantPark` |
| `POST /tenants/{tenant_id}/query` | `QueryResponse` | `tenantQuery` |
| `POST /tenants/{tenant_id}/restore` | `RestoreResult` | `tenantRestore` |
| `POST /tenants/seed` | `SeedResult` | `tenantSeed` |
| `POST /tiering/run` | `TieringRunResult` | `tieringRun` |
<!-- gen:end arch-api-contract -->

## Canonical Files

<!-- gen:begin arch-canonical-files -->
Hand-written: this is the file to edit:

- Layered API handler: `services/api/app/runtime/`
- Service orchestration: `services/api/app/service/`
- B2 data access (repo layer): `services/api/app/repo/b2_client.py`
- Pydantic models: `services/api/app/types/` (`base.py` carries the response-model config)
- Config (pydantic-settings): `services/api/app/config/settings.py`
- Structural tests: `services/api/tests/test_structure.py`
- OpenAPI exporter: `services/api/scripts/export_openapi.py`
- Frontend API client: error policy, transport, fallback: `apps/web/src/lib/api-client.ts`
- Frontend data layer: caching, invalidation, polling: `apps/web/src/lib/queries.ts`
- Shared type barrel: `packages/shared/src/types.ts`
- Generator policy: `scripts/gen/api-gen.config.json`
- Sample manifest behind the generated docs: `docs/exec-plans/sample.json`

Generated, **never hand-edit**; change the source and re-run the command:

- `docs/api/openapi.json`: `pnpm contract:export` (source: the routers and models)
- `packages/shared/src/generated/api-types.ts`: `pnpm gen:api`
- `apps/web/src/lib/generated/api-routes.ts`: `pnpm gen:api`
- `apps/web/src/lib/generated/query-keys.ts`: `pnpm gen:api`
- The marker-delimited regions of this file, `AGENTS.md`, `README.md` and the 0 `infra/` runbooks: `pnpm gen:docs`
<!-- gen:end arch-canonical-files -->

## Core Features

<!-- gen:begin arch-core-features -->
- [Tenants](docs/features/tenants.md): create tenants from text or Markdown files (or seed demo tenants), one Qdrant collection each, corpus in B2
- [Tiering](docs/features/tiering.md): idle policy and manual park (snapshot, multipart upload to B2, manifest last, verify, then drop)
- [Restore on query](docs/features/restore.md): the first query to a parked tenant restores it from B2 into any Qdrant node and reports the cost
- [Latency report](docs/features/latency-report.md): benchmark warm, restore and post-restore latency plus memory freed, stored as report.json in B2
- [Library](docs/features/library.md): the app's own objects under rag/, grouped by tenant and kind
- [Bucket explorer](docs/features/file-browser.md): full-bucket browse, preview, download and delete, streamed through the API
- [Dashboard](docs/features/dashboard.md): hot, parked and empty counts, vector memory in use and freed, bytes in B2, recent reports
- [Settings](docs/features/settings.md): read-only tiering policy and the browser theme
<!-- gen:end arch-core-features -->

## References

<!-- gen:begin arch-references -->
- [docs/SECURITY.md](docs/SECURITY.md): security principles and implementation
- [docs/RELIABILITY.md](docs/RELIABILITY.md): reliability expectations
- [AGENTS.md](AGENTS.md): architectural invariants and agent instructions
<!-- gen:end arch-references -->
