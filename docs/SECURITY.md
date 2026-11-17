<!-- last_verified: 2026-11-17 -->
# Security

Security principles and implementation for qdrant-multitenant-rag-tiering.

## Trust Boundaries

- **Frontend -> API**: CORS-restricted to configured origins, scoped to `GET/POST/PATCH/DELETE/OPTIONS`. `allow_credentials` is `False` (no cookie/session auth); enable it only alongside real auth and a tightened origin allowlist.
- **API -> B2**: authenticated with `B2_APPLICATION_KEY_ID` + `B2_APPLICATION_KEY`, signature v4, through one boto3 client carrying the custom user agent.
- **API -> Qdrant**: plain HTTP to `QDRANT_URL`. Under Docker Compose the node is on the Compose network and its port is published to the host for local use only; do not expose port 6333 publicly without a Qdrant API key and TLS.
- **Browser -> B2**: none. The API issues **no presigned URLs**. Preview and download are proxied by `GET /files-by-key/content`, so B2 credentials, signed URLs and bucket hostnames never reach the browser, and every byte read is attributable to the app's user agent.
- **Qdrant -> B2**: none. Restore uploads the snapshot to Qdrant from the API; Qdrant's "recover from URL" (which would make the node fetch from B2 itself) is not used.

## Authentication & Multi-Tenancy

- **No auth by design.** This is a single-operator demo: every route is unauthenticated, and "tenant" means a data-isolation unit in the vector store, not a login. Any client that reaches the API can list, query, park, edit and delete tenants and browse the bucket. The rate limiter guards the open endpoints.
- **Before exposing it to tenants themselves**, add auth to every route AND scope every read to the caller's tenant: the tenant routes, the Library and the bucket explorer would otherwise let one tenant read another's corpus. See the notes in `runtime/tenants.py` and `runtime/files.py`.

## Prefix Confinement

- Everything the app writes lives under `RAG_PREFIX` (default `rag/`): `corpus/<tenant>/`, `snapshots/<tenant>/`, `reports/<run-id>/`. Keys are built in one place, `app/service/deps.py`.
- Tenant ids (`^[a-z0-9][a-z0-9-]{0,38}[a-z0-9]$`), document names (letters/digits first, `.txt` or `.md`, no separators or `..`) and report ids are validated before they become keys, so a tenant can never write outside its own prefixes, and `_tenant.json` cannot be overwritten through a document name.
- Tenant delete removes only `snapshots/<tenant>/` and `corpus/<tenant>/` (exact prefix listing, refusing an empty prefix). Reports are kept.
- The end-to-end test writes under `e2e/<uuid>/rag/` and deletes only the keys it recorded writing.
- Optional `ALLOWED_KEY_PREFIX` additionally confines the bucket explorer's key-addressed reads and deletes when the bucket is shared.

## Delete Confirmation

- `DELETE /tenants/{tenant_id}` requires `confirm=<tenant_id>`; the UI makes the user type it. A mismatch is a 400 with nothing deleted (tested).
- Snapshot pruning is opt-in twice: `SNAPSHOT_PRUNE_ENABLED=true` on the server and `apply=true` per call. The object a tenant's `latest.json` points at is never a prune candidate.
- The code applies no bucket configuration (no lifecycle, CORS or Object Lock changes).

## Rate Limiting

- Per-IP fixed-window limiter (`app/runtime/ratelimit.py`), configurable via `RATE_LIMIT_PER_MINUTE` (reads) and `RATE_LIMIT_WRITE_PER_MINUTE` (POST/PATCH/DELETE, downloads, previews, the content proxy and checksum recompute). Guards against DoS and B2 transaction/egress cost amplification on the unauthenticated endpoints.
- In-process, per replica. Horizontal scaling needs a shared store (e.g. Redis): see [RELIABILITY.md](RELIABILITY.md).

## File Key Validation

- Empty keys rejected
- Path traversal patterns rejected (`../`, `%2e%2e`, backslashes, null bytes)
- The content proxy accepts only `attachment` or `inline` dispositions and encodes the filename (RFC 5987) in `Content-Disposition`

## Response Hardening

- Baseline headers on every API response: `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`
- Interactive API docs (`/docs`, `/redoc`, `/openapi.json`) can be disabled with `ENABLE_DOCS=false`

## CI Permissions

- `.github/workflows/ci.yml` sets `permissions: contents: read` at the workflow level, so `GITHUB_TOKEN` is read-only in every job. Widen per job, never at the top level.

## Secrets Management

- All secrets loaded via environment variables (pydantic-settings); Compose reads the repo-root env file into the `api` container only
- Never committed to source control; the Docker build context excludes env files (`.dockerignore`)
- `.env.example` documents required variables without values
- The embedding model downloads from the public Hugging Face Hub without a token

## Dependency and Secret Detection

- [`.github/dependabot.yml`](../.github/dependabot.yml) opens weekly update
  PRs for the root pnpm workspace and `services/api` Python dependencies.
- [`.pre-commit-config.yaml`](../.pre-commit-config.yaml) runs a pinned
  `detect-secrets` hook against staged changes.
- The Qdrant image is pinned to an exact release tag and `qdrant-client` to the
  same minor; bump both together.

## Agent Security Rules

- Never commit `.env`, credentials, or API keys
- Never print them either: the canonical rule lives in
  [AGENTS.md §12: Secret Handling](../AGENTS.md#12-secret-handling) (agents
  read AGENTS.md first); don't restate it here. `pnpm check:agent-docs`
  verifies the anchor still resolves
- The user request and trusted repository instructions are authoritative; see
  [AGENTS.md: Instruction Authority](../AGENTS.md#instruction-authority).
- Never weaken validation or the tiering safety rule without explicit instruction
- Never bypass CORS, auth, or input sanitization
- Always validate at system boundaries
