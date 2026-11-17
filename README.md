<!-- last_verified: 2026-11-17 -->
<!-- gen:begin readme-header -->
# Qdrant Multitenant RAG Tiering

Keep vector memory for the tenants who query; park the rest in B2. A multi-tenant RAG service that serves hot tenants from Qdrant, parks idle tenants' collections as verified snapshots in Backblaze B2, restores them on the next query, and measures what that costs in latency and saves in memory.

Built for developers and AI coding agents: the scaffolding, the storage
wiring and the agent-facing docs are already done, so you start on your
app's own features instead of rebuilding the same shell. Storage is
**[Backblaze B2](https://www.backblaze.com/sign-up/ai-cloud-storage?utm_source=github&utm_medium=referral&utm_campaign=ai_artifacts&utm_content=b2ai-qdrant-multitenant-rag-tiering)**, integrated through the S3-compatible API.

**What you get out of the box:**
- Full-stack dashboard UI (Next.js 16, React 19, Tailwind v4, shadcn/ui, TanStack Query, Recharts)
- Tenants — create tenants from text or Markdown files (or seed demo tenants), one Qdrant collection each, corpus in B2
- Tiering — idle policy and manual park: snapshot, multipart upload to B2, manifest last, verify, then drop
- Restore on query — the first query to a parked tenant restores it from B2 into any Qdrant node and reports the cost
- Latency report — benchmark warm, restore and post-restore latency plus memory freed, stored as report.json in B2
- Library — the app's own objects under rag/, grouped by tenant and kind
- Bucket explorer — full-bucket browse, preview, download and delete, streamed through the API
- Dashboard — hot, parked and empty counts, vector memory in use and freed, bytes in B2, recent reports
- Settings — read-only tiering policy and the browser theme
- Backend with a strict layered architecture and structural tests (FastAPI, Python 3.12, boto3, qdrant-client, fastembed, Pydantic v2)
- Agent-optimized docs — your AI coding agent can read the repo and start contributing immediately
<!-- gen:end readme-header -->

<!-- gen:begin readme-screenshots -->

<!-- gen:end readme-screenshots -->

## What it shows

A vector database bill grows with every tenant you index, including the ones
who query once a month. This sample keeps each tenant in its own Qdrant
collection while it is **hot**, and when a tenant has been idle longer than a
threshold it **parks** it: the collection is snapshotted through Qdrant's
snapshot API, streamed into Backblaze B2 with a multipart upload, checked
against a manifest, and only then dropped from the node. The first query to a
parked tenant **restores** it from B2 into whatever Qdrant node is running
(including a brand-new one) and answers. A benchmark measures warm latency,
restore time, the first query after a restore and the memory freed, so you can
choose a parking threshold on numbers rather than guesses.

B2 is the durable tier: every tenant's source documents and snapshots
accumulate there, while vector memory is spent only on tenants that query.

## Quick Start (Docker Compose)

You need Docker, and a free **[Backblaze B2 account](https://www.backblaze.com/sign-up/ai-cloud-storage?utm_source=github&utm_medium=referral&utm_campaign=ai_artifacts&utm_content=b2ai-qdrant-multitenant-rag-tiering)** with a bucket and an application key.

```bash
git clone https://github.com/backblaze-b2-samples/qdrant-multitenant-rag-tiering.git
cd qdrant-multitenant-rag-tiering
cp .env.example .env        # then fill in the four B2_* values (below)
docker compose up --build
```

Open `localhost:3000`, go to **Tenants**, click **Seed demo tenants**, open a
tenant, ask a question, click **Park now**, and ask again: the answer comes back
after a restore from B2, with the restore time shown. Then run a benchmark on
**Reports**.

To fill in `.env`, open the [Backblaze B2 dashboard](https://secure.backblaze.com/b2_buckets.htm?utm_source=github&utm_medium=referral&utm_campaign=ai_artifacts&utm_content=b2ai-qdrant-multitenant-rag-tiering) and:

<!-- gen:begin readme-credentials -->
1. **Create a bucket** and an **application key** with `Read and Write`
   permission, then paste each value into `.env`:
   - `B2_APPLICATION_KEY_ID` — B2 application key ID (**keyID** in the B2 console)
   - `B2_APPLICATION_KEY` — B2 application key (**applicationKey**) — shown once at creation
   - `B2_BUCKET_NAME` — bucket unique name (**Bucket Unique Name** in the B2 console)
   - `B2_REGION` — the region inside the bucket's **Endpoint** (`s3.<region>.backblazeb2.com`); the S3 endpoint is derived from it

   B2 shows an application key once, at creation. The optional variables are
   documented in `.env.example` and in the delivery runbooks.
<!-- gen:end readme-credentials -->

> Want a walkthrough? See the docs for [creating a bucket](https://www.backblaze.com/docs/cloud-storage-create-and-manage-buckets) and [creating app keys](https://www.backblaze.com/docs/cloud-storage-create-and-manage-app-keys).

Compose starts three containers: `qdrant` (pinned `qdrant/qdrant:v1.20.2`, port
6333, named volume), `api` (FastAPI on port 8000, reading `.env`) and `web`
(Next.js on port 3000). Everything the app writes lands under `rag/` in your
bucket.

### The embedding model

Embeddings run locally with [fastembed](https://github.com/qdrant/fastembed):
**`BAAI/bge-small-en-v1.5`**, 384 dimensions, about **67 MB**, downloaded once
from the Hugging Face Hub (no account or key) on first start. Under Compose it
is cached in the `model-cache` volume (`FASTEMBED_CACHE_PATH=/models`); in local
dev it goes to fastembed's default cache directory. It runs on CPU, which is the
intended path for a model this small. If onnxruntime reports a CUDA provider
(install `fastembed-gpu`), it uses the GPU; there is no Apple MPS provider for
onnxruntime, so Apple silicon runs on CPU. Set `EMBEDDING_MODEL` to use another
fastembed model: each snapshot manifest records the model and vector size, so a
restore under a different model fails clearly instead of returning wrong results.

### Local development without Compose

You need Node.js >= 20, pnpm >= 10, Python >= 3.12 and Docker (for Qdrant only).

```bash
pnpm run setup              # .env from .env.example, pnpm deps, services/api/.venv from requirements.lock
docker compose up qdrant    # the hot tier on localhost:6333
pnpm dev                    # web on localhost:3000, API on localhost:8000
```

> Use the `pnpm run` form: `setup` (like `doctor`) is a built-in pnpm command
> before pnpm 11, so bare `pnpm setup` would run pnpm's own command instead.

`pnpm dev` runs `pnpm run doctor` first, which catches wrong Node/Python
versions, a missing venv, a missing or placeholder `.env` and busy ports.
Interactive API docs are at `localhost:8000/docs`. Local scripts run on macOS,
Linux and WSL2; see [docs/verification.md](docs/verification.md#local-environments)
for sandbox and port-fallback behaviour.

## How tiering works

| State | Where the tenant lives |
| --- | --- |
| **Hot** | collection `tenant_<id>` on the Qdrant node; queries answer immediately |
| **Parked** | no collection; `rag/snapshots/<id>/latest.json` and the snapshot it names are in B2 |
| **Empty** | metadata only; adding documents makes it hot |

A tenant is a parking candidate when it has had no query or write for
`TIERING_IDLE_SECONDS` (7 days by default). A background sweep checks every
`TIERING_SWEEP_INTERVAL_SECONDS` (300 by default, `0` disables it); you can also
run the sweep from **Tenants** (dry run by default) or click **Park now** on a
tenant. Idle clocks live in memory, so after an API restart they start from
startup: that can only delay parking, never park early.

### The safety rule: verify before drop

1. Qdrant creates a snapshot of the collection and reports its sha256.
2. The API streams it into a B2 multipart upload (`SNAPSHOT_PART_SIZE_BYTES`,
   8 MiB parts), hashing as it goes; the hash must equal Qdrant's. Any failure
   aborts the upload, so no partial object appears.
3. `latest.json` is written **last**, so a previously good manifest is never
   replaced before the new snapshot is fully in B2.
4. The API reads B2 back: `head_object` size, then a streamed sha256, both
   against the manifest.
5. Only then does it delete the node's snapshot file and drop the collection.

If anything in steps 1 to 4 fails, the tenant stays hot, the previous manifest
is put back, and the reason is shown. Restore is just as strict: the snapshot is
hashed while it downloads, Qdrant is given the checksum, and the restored point
count must equal the manifest's.

### Reading the latency report

**Reports → Run benchmark** takes each selected tenant through warm queries,
a real park, a query that restores it, and the same queries again, then writes
`rag/reports/<run-id>/report.json`. On the report page:

- **Warm p50 / p95**: what a hot tenant costs per query.
- **Restore (download + load)**: time to pull the snapshot from B2 and load it.
- **First query**: what a user of a parked tenant actually waits, end to end.
  The headline card divides it by the warm p50.
- **Post-restore p50 / p95**: should be back at warm levels.
- **Memory freed**: the estimate (`points × dimensions × 4` plus payload bytes)
  is deterministic; the observed figure is the drop in Qdrant's
  `memory_resident_bytes` and can lag, because allocators do not always return
  memory at once.
- **Match**: hit ids and scores identical (within 1e-4) before and after.

If a parked tenant's first query is acceptable for how rarely that tenant
queries, you can park sooner.

## Alternative: Qdrant's built-in S3 snapshot storage

Qdrant can write snapshots straight to S3-compatible storage itself. Pointed at
B2, the node's config looks like this:

```yaml
storage:
  snapshots_config:
    snapshots_storage: s3
    s3_config:
      bucket: your-bucket-name
      region: <your-b2-region>
      access_key: <B2_APPLICATION_KEY_ID>
      secret_key: <B2_APPLICATION_KEY>
      endpoint_url: https://s3.<your-b2-region>.backblazeb2.com
```

That is a reasonable choice when you want Qdrant to own the transfer. This
sample does not use it, and its tests do not cover it: those requests carry
Qdrant's own user agent rather than this app's, the node needs the B2 key, and
the app could no longer hash the bytes on the way in and verify them before
dropping a collection, which is the point of the safety rule above.

## When to use

Use this sample when you run retrieval for many customers and most of them are
idle most of the time: a per-tenant collection model, a single Qdrant node or a
small cluster, and a need to justify a parking threshold with measured restore
cost. It is also a worked example of streaming large artifacts to B2 safely
(multipart, manifest-last, verify-before-delete).

## When not to use

It is a single-operator demo, not a hosted service: there is no
authentication, every route is open to whoever can reach the API, and the
per-tenant locks assume one API process per Qdrant node. It does not cover
Qdrant clusters with replicated shards, payload-based multitenancy inside one
collection, or tenants so large that a restore takes minutes. Before production
use you own auth, tenant-scoped access, capacity and operations.

## Why Backblaze B2?

[Backblaze B2](https://www.backblaze.com/cloud-storage?utm_source=github&utm_medium=referral&utm_campaign=ai_artifacts&utm_content=b2ai-qdrant-multitenant-rag-tiering) is the durable tier this design depends on:

- **Cheap enough to keep everything.** Snapshots and corpora for every tenant,
  plus older snapshots if you keep them, cost a fraction of the RAM and disk a
  vector node needs to hold the same tenants hot.
- **S3-compatible.** Plain `boto3` multipart uploads and streamed reads, isolated in
  `services/api/app/repo/`; nothing is locked to a proprietary client.
- **Fast enough to restore on demand.** The report measures exactly how fast, from
  your bucket's region to your node.
- **Free to start.** A [free B2 account](https://www.backblaze.com/sign-up/ai-cloud-storage?utm_source=github&utm_medium=referral&utm_campaign=ai_artifacts&utm_content=b2ai-qdrant-multitenant-rag-tiering) runs everything here.

## Core Features

<!-- gen:begin readme-core-features -->
- [Tenants](docs/features/tenants.md) — create tenants from text or Markdown files (or seed demo tenants), one Qdrant collection each, corpus in B2
- [Tiering](docs/features/tiering.md) — idle policy and manual park: snapshot, multipart upload to B2, manifest last, verify, then drop
- [Restore on query](docs/features/restore.md) — the first query to a parked tenant restores it from B2 into any Qdrant node and reports the cost
- [Latency report](docs/features/latency-report.md) — benchmark warm, restore and post-restore latency plus memory freed, stored as report.json in B2
- [Library](docs/features/library.md) — the app's own objects under rag/, grouped by tenant and kind
- [Bucket explorer](docs/features/file-browser.md) — full-bucket browse, preview, download and delete, streamed through the API
- [Dashboard](docs/features/dashboard.md) — hot, parked and empty counts, vector memory in use and freed, bytes in B2, recent reports
- [Settings](docs/features/settings.md) — read-only tiering policy and the browser theme
<!-- gen:end readme-core-features -->

## Tech Stack

- TypeScript, Next.js 16, React 19, Tailwind v4, shadcn/ui, TanStack Query, Recharts
- Python 3.12, FastAPI, boto3, qdrant-client 1.20, fastembed, Pydantic v2
- Qdrant v1.20.2 (Docker), Backblaze B2 (S3-compatible API)
- pnpm workspaces, Docker Compose

## Commands

<!-- gen:begin readme-commands -->
| Command | What it does |
| --- | --- |
| `pnpm run setup` | One-time cold start: copy `.env.example` → `.env` (only if missing), install workspace deps, create the backend venv, install locked API deps |
| `pnpm dev` | Start frontend + backend (runs the `pnpm run doctor` preflight first) |
| `pnpm wait-ready` | Block until the running web + API answer, print one line, exit 0/1 — use instead of sleeping before driving the app |
| `pnpm contract:export` | Export the FastAPI OpenAPI contract into `docs/api/openapi.json` |
| `pnpm contract:check` | Verify the exported contract and the generated client routes agree, both ways |
| `pnpm gen:api` | Regenerate the shared types, the client route registry and the query-key factory from the exported contract |
| `pnpm gen:docs` | Regenerate the marker-delimited doc regions from `docs/exec-plans/sample.json` |
| `pnpm gen:check` | Fail if any generated file or doc region is stale (first step of `pnpm verify:web`) |
| `pnpm verify` | Credential-free pre-PR suite — runs `check:agent-docs`, `verify:api`, then `verify:web` |
| `pnpm verify:full` | `pnpm verify` plus Playwright E2E; needs a live local stack, real `.env`, a free web port, and Chromium |
| `pnpm test:verify` | Run throwaway verification specs from `apps/web/e2e/verify/` against the app, with the shared browser fixtures |
<!-- gen:end readme-commands -->

`pnpm verify` is the gate to run before opening a PR. It needs
`services/api/.venv` from `pnpm run setup` but no B2 credentials, Docker or
browser: the backend tests run the park and restore state machine against
in-memory fakes behind the same interfaces as the real adapters. It breaks down
into `pnpm check:agent-docs`, `pnpm verify:api` and `pnpm verify:web`.

`pnpm test:e2e:tiering` is the end-to-end proof of the primary feature. It needs
Docker and the B2 values in `.env`: it starts a Qdrant container, ingests two
tenants, parks one through the policy, starts a second empty Qdrant container,
restores into it, checks the same hits come back, runs a benchmark, then deletes
only the keys it wrote under `e2e/<run-id>/` and removes both containers.

For the full command reference see [docs/dev-workflows.md](docs/dev-workflows.md#commands).

## Deployment

<!-- gen:begin readme-deploy-button -->
_This app does not ship a one-click deploy button._
<!-- gen:end readme-deploy-button -->

The app runs with Docker Compose. It needs a Qdrant node and a CPU embedding
model, which serverless platforms do not host, so no hosted delivery contract
ships with it.

## Documentation Map

<!-- gen:begin readme-doc-map -->
| Doc | Purpose |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Agent table of contents — start here |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System layout, layering, data flows |
| [docs/features/](docs/features/) | Feature docs (tenants, tiering, restore on query, latency report, library, bucket explorer, dashboard, settings) |
| [docs/design-system.md](docs/design-system.md) | Design tokens, primitives, loader, error/empty states |
| [docs/app-workflows.md](docs/app-workflows.md) | User journeys |
| [docs/dev-workflows.md](docs/dev-workflows.md) | Engineering workflows, command index, releases |
| [docs/verification.md](docs/verification.md) | What each gate checks, and failure recovery |
| [docs/frontend-conventions.md](docs/frontend-conventions.md) | Frontend conventions, screens, data fetching |
| [docs/SECURITY.md](docs/SECURITY.md) | Security principles |
| [docs/RELIABILITY.md](docs/RELIABILITY.md) | Reliability expectations |
| [docs/api/openapi.json](docs/api/openapi.json) | The checked-in API contract the client seam is generated from |
| [docs/exec-plans/](docs/exec-plans/) | Execution plans, tech debt, and the sample manifest |
<!-- gen:end readme-doc-map -->

## FAQ

**Why one collection per tenant instead of one collection with a tenant field?**
A whole collection can be snapshotted, moved and dropped as a unit, which is what
makes parking and restoring a single tenant cheap and safe.

**Does a parked tenant lose data?**
No. The collection is dropped only after its snapshot is verified in B2, and its
source documents stay in B2 regardless.

**Can I restore into a different Qdrant node?**
Yes. Restore uploads the snapshot through the API to whatever `QDRANT_URL` points
at, including a node with empty storage; the end-to-end test does exactly that.

**Do I need a GPU or an API key?**
No. Embeddings run on CPU with a 67 MB local model, and there are no external AI calls.

**Is it free?**
The code is MIT-licensed, and a free Backblaze B2 account is enough to run it.

**Where do I get help or report bugs?**
Repository issues: [GitHub Issues](https://github.com/backblaze-b2-samples/qdrant-multitenant-rag-tiering/issues).
B2 account, billing or API help: [Backblaze Support](https://www.backblaze.com/help).

## Maintenance and support

Backblaze maintains this open-source sample to help developers get started with
B2. Production use requires your own validation. Report repository defects and
feature requests through
[GitHub Issues](https://github.com/backblaze-b2-samples/qdrant-multitenant-rag-tiering/issues);
for B2 account, billing, service, or API help, use
[Backblaze Support](https://www.backblaze.com/help). This sample is not covered
by the Backblaze service level agreement, and no SLA is provided for the
repository software.

## Contributing

Start with [AGENTS.md](AGENTS.md). For local commit hooks, follow
[the pre-commit workflow](docs/verification.md#pre-commit).

## License

MIT License - see [LICENSE](LICENSE) for details.
