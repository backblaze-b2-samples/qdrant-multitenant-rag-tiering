<!-- last_verified: 2026-11-17 -->
# Tech Debt Tracker

Known tech debt items. Agents update this when they discover or create tech debt.

## Open

| Description | Impact | Proposed Resolution | Priority |
|---|---|---|---|
| The benchmark runs inside one HTTP request | Six tenants with large corpora can take minutes; a dropped connection loses the result (the report is only written at the end) | Run benchmarks as background jobs with a status endpoint, writing `report.json` incrementally | Medium |
| Payload bytes in the memory estimate come from ingest-time metadata (`_tenant.json`), not from Qdrant | Qdrant's collection info reports no payload size, so the estimate trusts the app's own record; edits made outside the app are not reflected | Sum payload sizes with a scroll before parking, or read Qdrant telemetry when it exposes payload storage | Low |
| Per-tenant locks and idle clocks are per API process | Two API replicas against one node could park and query the same tenant concurrently | Single replica per node (documented), or a distributed lock (e.g. Redis) keyed by tenant | Medium |
| `/library` and tenant discovery list the whole `RAG_PREFIX` on each call | Thousands of tenants or snapshots make every page load a long listing | Paginate `/library`, cache tenant discovery like the bucket listing | Low |
| Download counter & `/metrics` not durable across restart/replicas | Counter resets on redeploy (ephemeral FS); both fragment across replicas | Back the counter with a shared store (Redis/DB); label/aggregate metrics per instance. Relocated to `repo/counter.py` and documented in RELIABILITY.md | Medium |
| `GET /files-by-key/detail` re-downloads the whole object to recompute checksums | A full download + in-memory hash per request; objects above `MAX_FILE_SIZE` are refused | Stream the hash, or read checksums from object metadata when present | Low |
| `get_upload_activity` re-materializes `FileMetadata` for every object just to bucket dates | Wasted O(n) CPU per `/files/stats/activity` (scan is cached; materialization is not) | Aggregate from raw listing dicts like `get_upload_stats` does | Low |
| `GET /files` has no pagination — `/files` shows only the newest 100 objects | An older object is unreachable from the UI. The browser now *states* the truncation (`lib/file-list-limit.ts`) instead of claiming "everything in your bucket", but there is still no way to page or search to an older key | Add cursor pagination to `GET /files` (pass through S3's `ContinuationToken` rather than slicing a full scan) plus "Load more"/search in `FileBrowser` | Medium |
| Frontend has no component/render tests | UI states (loading/error/empty) are verified only by the Playwright journey in `e2e/tenants.spec.ts`, which needs the live stack | Add jsdom + @testing-library/react render tests for the tenant, report and library screens | Medium |
| No auth layer or placeholder | Every consumer designs auth from scratch; unclear where it plugs in | Add example middleware (API-key or JWT) + docs for the seam | Low |
| `e2e/**` and `playwright.config.ts` are excluded from `apps/web/tsconfig.json` | Neither `pnpm typecheck` nor `next build` typechecks the E2E specs, and `pnpm test:e2e` is not in CI — type errors there can sit undetected indefinitely | Add a dedicated `tsconfig.e2e.json` and typecheck it in `pnpm verify:web`, or drop the exclude | Low |
| No tests for the ~545 lines of enforcement logic in `scripts/check-agent-docs.mjs` + `scripts/agent-docs/*.mjs`, against AGENTS.md §4 ("tests for every behavior change") | Seven AGENTS.md §5 rules now name this script as their enforcer, and its own comments record six fixed false-greens (`env-ignore.mjs:6`, `:11`, `check-agent-docs.mjs:63`, `:127`, `:213`, plus folded `run: >` scalars in `workflow.mjs:22`) — the next regression is silent again | Decide the harness: no precedent exists for testing `scripts/` (`doctor.mjs`, `pick-port.mjs` are untested), so this needs a small `node:test` runner over fixture repos, wired into `pnpm verify` as its own gate | Medium |
| `scripts/agent-docs/workflow.mjs:17,128` — `RUN_KEY` matches `run:` at any indentation (including under `with:`), and `readBlockScalar` does not advance the loop index, so block content is re-scanned as top-level lines | Non-executing text can satisfy "CI runs X". Verified with the real `run: pnpm verify:web` step deleted: both a heredoc containing `run: pnpm verify:web` and a `with:` input named `run` pass at exit 0 / 74 checks. Medium only because plain deletion of the job *is* caught | Anchor `run:` to step-level indentation (a `-` list item under `steps:`) and return the consumed line count from `readBlockScalar` so the loop skips past it | Medium |
| `scripts/agent-docs/env-ignore.mjs:36` — `isRepoIgnoreSource` validates the path *shape*, not that the `.gitignore` is tracked, while every message says "repo-tracked" | Verified both directions with an untracked `services/api/.gitignore` containing `.env.*`: false failure (`services/api/.env.example remains trackable — actual ignored`), and, with the root env section deleted, a false pass that is green locally and broken in a fresh clone | Confirm the matching source with `git ls-files --error-unmatch <source>`, or drop "repo-tracked" from the wording | Medium |
| `scripts/agent-docs/workflow.mjs:173` (`checkGateClaims`) — the package.json and CI-claims assertions are presence-only, so a neutered gate still satisfies them | A job disabled with `if: false` still satisfies "declares job X" / "runs X", and `"verify": "pnpm check:agent-docs && pnpm verify:api \|\| true && pnpm verify:web"` still satisfies every composition assertion — both verified at exit 0 / 74 checks. Needs deliberate neutering rather than deletion | Reject `if: false` (and equivalent always-false conditions) on the asserted jobs, and reject short-circuit operators (`\|\|`, `;`, `& `) inside the verify chains | Medium |
| `.github/workflows/ci.yml:4-5` — the header comment holds the only verbatim copy of the verify chain, and `scripts/agent-docs/workflow.mjs` strips comments before parsing by design | `docs/verification.md` makes `package.json` the single source of truth for the literal chain, so this last hand-maintained copy is permanently invisible to the guard and has already needed a hand edit once | Drop the `=` expansion from the comment and point at `package.json` instead | Low |
| The API contract check covers routes only; request/response *shapes* and the hand-written mirrors of the Pydantic models in `packages/shared/src/types.ts` are still hand-synced | Renaming or retyping a response field passes every gate — `docs/api/openapi.json` updates, the route set is unchanged, and the frontend keeps reading the old field as `undefined`. This is the half of "`api-client.ts` hand-synced to FastAPI" that the contract workflow did not close | Generate the shared TS types from `docs/api/openapi.json` (`openapi-typescript` emits types only, no client), or assert the schema of each client-consumed operation against `packages/shared` | Medium |

## Resolved

| Description | Resolution |
|---|---|
| `api-client.ts` hand-synced to FastAPI (route drift only) | Added deterministic OpenAPI workflow: `docs/api/openapi.json`, `pnpm contract:export`, `pnpm contract:check`, backend freshness coverage in `test_openapi_contract.py`, and frontend route drift coverage in `api-contract.test.ts`. Full codegen remains a future option only if this lightweight check proves insufficient. **Payload/type drift is not covered** — see the open row on `packages/shared/src/types.ts` |
| Byte-exact OpenAPI comparison against floating Python dependencies | Added `services/api/requirements.lock`, a complete Python 3.12 resolution installed by setup and CI. Intentional dependency refreshes now update the lock and `docs/api/openapi.json` together, so routine verification does not absorb upstream schema churn. |
| Rich metadata (checksums/EXIF/PDF) unavailable for already-stored files | `GET /files-by-key/detail` recomputes `FileMetadataDetail` on demand from the object bytes; `FileMetadataPanel` mounted in the Files preview dialog behind a lazy "Detailed metadata" disclosure |
| Blocking boto3 in `async def` handlers froze the single event loop | B2 handlers are sync `def` (Starlette threadpool); upload offloads via `run_in_threadpool` |
| Full-bucket scan on every list/stats/activity request, uncached | Short-TTL cache in `repo/b2_client._list_all_objects`, invalidated on upload/delete |
| No CI — quality gates ran only when a human remembered | `.github/workflows/ci.yml` runs all three `pnpm verify` gates — `check:agent-docs`, `verify:api`, `verify:web` — as parallel jobs on PR and push to `main` |
| README called AGENTS.md a "~100 line" entry point and concurrent `pnpm verify` shared Next.js's build lock | Replaced the stale size claims with bounded wording; the workflow supports one verification per worktree, documents the narrow `.next/lock` recovery, pre-commit use, timing, and separate E2E prerequisites |
| SVG stored-XSS; declared MIME trusted; unused `python-magic` dep | Dropped SVG from allow-list; added magic-byte signature check; removed dead `python-magic` |
| No rate limiting → DoS + B2 cost amplification | Per-IP fixed-window limiter (`runtime/ratelimit.py`), read/write budgets |
| Counter persistence lived in the service layer (layering violation) | Moved file I/O to `repo/counter.py` behind `get/increment_download_count` |
| CORS `allow_credentials=True` with no auth + regex escape hatch | Default `allow_credentials=False`; empty origins filtered |
| No security headers on API responses | `X-Content-Type-Options: nosniff` + `Referrer-Policy: no-referrer` on every response |
| Key-addressed ops could target any bucket object | Opt-in `ALLOWED_KEY_PREFIX` confinement (off by default, preserves arbitrary-key routes) |
| Redundant triple-scan + double sort per dashboard mount | TTL cache + single-flight collapse the concurrent empty-prefix scans; dropped the repo-layer sort so `get_files` owns newest-first ordering once |
| Unguarded `int(content-length)`; public `/docs`; uncached `/health` B2 call | Content-Length parse guarded; `ENABLE_DOCS` toggle; connectivity cached ~5s |
| Upload validation sad-paths (413/415) + sanitizer untested | `tests/test_upload_validation.py` covers the rejection matrix, signature, `uploads_total` |
| FastAPI `/docs` & `/redoc` undocumented | Documented in README; `ENABLE_DOCS` toggle added |
| `NEXT_PUBLIC_API_URL` missing from `.env.example` | Added with guidance |
| `get_upload_stats()` / `list_files()` object listing capped at 1000 | Shared `_list_all_objects()` paginator follows `ContinuationToken` |
| `datetime.utcnow()` deprecated in Python 3.12+ | Replaced with `datetime.now(UTC)` |
| S3 client recreated on every API call | Cached module-level singleton via `lru_cache` |
| `record_upload()` never called | Called from `runtime/upload.py` after upload |
| Metrics counters not thread-safe | Guarded by `threading.Lock` |
| `_humanize_bytes` duplicated in Python | Extracted to `app/types/formatting.py` |
| `humanizeBytes` / `formatDate` duplicated in TypeScript | Extracted to `lib/utils.ts` (tested) |
| Custom `FileNotFoundError` shadowed the built-in | Renamed to `FileNotFoundServiceError` |
| Dropzone accepted any file type client-side | `accept` allow-list mirroring backend `ALLOWED_TYPES` (tested for drift) |
| No test harness for feature specs | pytest suite across upload, files, activity, errors, validation, rate limit, pagination |

## 2026-11-17 — verify
- friction (unresolved after 3 rounds): Reports, benchmark form — only the hot tenant is pre-checked and "Tenants measured 1" results, with no text saying which tenants run → first-time user expects every listed tenant to be benchmarked (.local/verify/A-r3/r3-19-reports.png)
- friction (unresolved after 3 rounds): Tiering sweep dialog — 15 s park shows "Parked n of N so far" plus per-tenant step text but no determinate progress bar → long wait without a bar (.local/verify/B-r3/r3-15-sweep-progress-later.png)
- friction (unresolved after 3 rounds): Reports, Run benchmark — 37 s run shows "Tenant n of N (id): phase" plus spinner but no determinate progress bar → long wait without a bar (.local/verify/B-r3/r3-22-benchmark-progress-later.png)
- friction (unresolved after 3 rounds): /files bucket explorer — lists "the 100 most recent of 1,314 objects" with other apps' folders first; this app's rag/ objects sit below the fold unless "App objects only" is used → B2 evidence hard to find on a shared bucket (.local/verify/C-r3/r3-09-files-snapshot-tree.png)
- Report detail — every "RSS drop (obs.)" cell is 0 B and the observed series paints no bars → measured memory freed reads as nothing; only the estimate carries signal (.local/verify/C-r3/r3-20-bench-multi-figures.png)
- Dashboard footprint chart — parked tenant tooltip reads "Vector memory (KiB, est.) 5.2" while the Tenants table reads "0 B (5.2 KB freed)" → same number labelled in-use vs freed (.local/verify/C-r3/r3-22-dashboard-after-benchmark.png)
- Dashboard footprint chart — x-axis shows truncated tenant ids ("zoxide-docs-r33…") while the table uses display names → names disagree across surfaces (.local/verify/C-r3/r3-22-dashboard-after-benchmark.png)
- Tenant detail — breadcrumb shows the title-cased id ("Bat Docs R8634") instead of the display name ("bat documentation") (.local/verify/C-r2/r2-04-created-tenant-hot.png)
- Tenant detail during restore — header badge stays "Parked in B2" with no step text during a ~6 s restore; only the button reads "Restoring from B2…" (.local/verify/B-r3/r3-10-restoring.png)
- Tenants page — the unlabeled "4 tenants" seed-count picker reads like a tenant count; the header and the empty state carry duplicate Seed controls (.local/verify/A-r3/r3-02-tenants-empty.png)
- Toasts — "Parked 2 tenant(s)" / "Seeded 0 tenant(s)" use "(s)" plurals (.local/verify/B-r3/r3-17-table-after-sweep.png)
- Tiering sweep dialog — default 7-day threshold with Dry run on returns "Candidates: none" with no hint that the 30 s option demos parking; the dialog has no "done" state after parking (.local/verify/A-r2/r2-09-sweep-default-result.png)
- Dashboard empty state — the Seed action is one page deeper than the dashboard CTA ("Manage tenants") (.local/verify/A-r2/r2-01-dashboard-empty.png)
- Report latency chart — linear scale makes warm/post-restore bars (~5 ms) flat next to restore bars (~0.5–2 s); the numbers are only readable in the Figures table (.local/verify/C-r2/r2-20-bench-multi-figures.png)
- Memory units — MiB on the report chart, KB/MB in the tables and cards, and no unit on the dashboard footprint y-axis (.local/verify/C-r2/r2-17-dashboard-after-sweep.png)
