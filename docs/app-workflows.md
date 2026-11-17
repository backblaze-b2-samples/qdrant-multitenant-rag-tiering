<!-- last_verified: 2026-11-17 -->
# App Workflows

User journeys inside the application.

## Manage Tenants

- User navigates to `/tenants`
- **Seed demo tenants**: pick 2, 4 (default) or 6 and click the button. Each synthetic tenant (legal, clinic, robotics, gardening, finance, astronomy: clearly distinct subjects) gets three short documents written to `rag/corpus/<tenant>/` and indexed into its own collection. Existing tenants are skipped, so seeding twice is safe
- **New tenant**: a dialog with tenant id (placeholder `acme-legal`, hint "lowercase letters, digits and hyphens, 2 to 40 characters"), display name (placeholder `Acme Legal`) and a `.txt` / `.md` file picker. Bad ids are rejected in the form; on success the user lands on the tenant's page
- The table shows each tenant's state badge (Hot, Parked in B2, Empty, or a spinning Snapshotting / Uploading / Verifying / Dropping / Restoring), points, documents, vector memory in Qdrant (a parked tenant shows `0 B (<estimate> freed)`, the same text as its detail page), last query and snapshot size. It polls every 15 s because the background sweep can park tenants without anyone clicking, and every second while any tenant is mid-park or mid-restore. Seeding, parking and sweeps only report success once the table has refetched
- On `/tenants/<id>`: facts (points, documents, vector memory in Qdrant, last query, latest snapshot); while "Park now" runs, a "Parking: Step n of 4" line follows the stage, and a query that restored the tenant flips the badge to Hot with the answer, the query box, the documents (each opens its preview in the bucket explorer), the snapshot history with the `latest.json` target marked, and the danger zone
- **Query**: type a question, choose 3 / 5 / 10 results, Search. Hits show document, chunk, score and text, plus the search time
- **Edit**: the Edit sheet changes the display name, removes documents (checkbox list) and adds documents. Editing a parked tenant restores it first; changed documents mark the B2 snapshot as stale until the next park
- **Delete**: the danger zone asks the user to type the tenant id. Only that tenant's collection, corpus and snapshots are deleted; reports stay
- See: [Tenants](features/tenants.md)

## Park Idle Tenants

- **Park now** on a hot tenant runs the full state machine: snapshot, stream to B2, write `latest.json` last, verify size and sha256, then drop the collection. The badge passes through Snapshotting and Verifying; a toast reports the snapshot size and the vector memory freed, or the reason the tenant stayed hot
- **Run tiering sweep** on `/tenants`: choose an idle threshold (30 s, 5 min, 1 h, 1 day, 7 days, defaulting to the server policy) and keep Dry run on to see the candidates. Turning Dry run off parks them and lists anything skipped with its reason
- **Prune snapshots**: keep 1, 2 or 3 per tenant; with "Delete for real" off it only lists candidates. The button is disabled, with an explanation, unless the server sets `SNAPSHOT_PRUNE_ENABLED=true`
- The background sweep does the same as a non-dry run every `TIERING_SWEEP_INTERVAL_SECONDS`
- See: [Tiering](features/tiering.md)

## Measure the Cost of Parking

- User navigates to `/reports`
- Picks tenants (checkbox list, the first hot tenant preselected, up to six) and 5 / 10 / 20 queries per phase, then **Run benchmark**
- The run takes a few seconds per tenant (it parks and restores each one for real); on success the user lands on `/reports/<run-id>`
- The report shows the restore penalty (first query after park vs warm p50), whether post-restore results matched warm results, a latency chart (warm p50, restore, post-restore p50 per tenant), a memory chart (estimated bytes freed vs observed Qdrant RSS drop) and a table with every figure
- This is the screen a person reviews to choose a parking threshold on measured numbers
- See: [Latency report](features/latency-report.md)

## Browse the App's Objects

- User navigates to `/library`
- Filters by tenant and by kind (corpus, snapshots, reports); `?kind=reports` preselects reports (the report page links here)
- Each card lists one tenant's objects of one kind; clicking an object opens its preview in the bucket explorer
- See: [Library](features/library.md)

## Browse the Whole Bucket

- User navigates to `/files`; the page lists the 100 most recent objects in the bucket, including objects this app did not write, and says so when more exist
- Clicking a file opens a preview dialog. Images, PDFs, text, Markdown and JSON (corpus documents, `latest.json`, `report.json`) render inline, streamed through the API: the browser never receives a presigned B2 URL
- Download shows a pending state, then starts an attachment download from the same content proxy; Delete asks for confirmation and removes the row when the request settles
- Arriving at `/files?preview=<key>` opens that object's preview directly; tenant pages, the Library and the ⌘K palette link here
- See: [Bucket explorer](features/file-browser.md)

## View Dashboard

- User navigates to `/` (home)
- Cards show hot, parked and empty tenant counts, estimated vector memory in use and freed by parking, and the bytes of snapshots and corpus held in B2
- A per-tenant chart shows each tenant's vector footprint, solid when hot and faded when parked
- The five latest latency reports link to their pages
- With no tenants, the empty states point to `/tenants`
- See: [Dashboard](features/dashboard.md)

## Check the Policy

- User navigates to `/settings`
- The Tiering policy card shows the idle threshold, the sweep cadence (or "disabled") and whether pruning is allowed, each with the environment variable that sets it. It is read-only: the policy is server configuration
- The theme radio group (light, dark, system) applies and persists the theme in this browser
- See: [Settings](features/settings.md)
