"""End-to-end tiering against real Docker Qdrant nodes and a real B2 bucket.

Run with `pnpm test:e2e:tiering` (sets RUN_E2E_TIERING=1). Needs Docker and the
four required B2_* variables in the repo-root .env. Everything is written under
a throwaway prefix `e2e/<uuid>/rag/`, and the test deletes exactly the keys it
recorded writing, then asserts that prefix is empty.

Flow: node A (empty storage) -> ingest two tenants -> record query results ->
park one through the policy with a seconds-level idle threshold -> start a
fresh node B -> the first query restores the tenant from B2 into B -> same hit
ids and scores -> run a benchmark and check report.json -> clean up.
"""

import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
# Settings() reads the environment at import, so load the repo-root env file
# before importing anything from app/ (main.py does the same for the server).
load_dotenv(REPO_ROOT / ".env")

from app.config import settings  # noqa: E402
from app.repo.b2_object import B2ObjectStore  # noqa: E402
from app.repo.embedder import get_embedder  # noqa: E402
from app.repo.qdrant_gateway import QdrantGateway  # noqa: E402
from app.service import deps, state  # noqa: E402
from app.service.seed_corpus import SEED_TENANTS  # noqa: E402

TOLERANCE = 1e-4
QUERIES = {
    "acme-legal": ["How much notice is needed to terminate a supplier contract?"],
    "greenleaf-garden": ["How often should I water tomato plants?"],
}


def _qdrant_image() -> str:
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    match = re.search(r"image:\s*(qdrant/qdrant:v[0-9.]+)", compose)
    assert match, "docker-compose.yml must pin qdrant/qdrant:vX.Y.Z"
    return match.group(1)


def _start_node(image: str) -> tuple[str, str]:
    cid = subprocess.check_output(
        ["docker", "run", "-d", "--rm", "-p", "127.0.0.1::6333", image], text=True
    ).strip()
    port = subprocess.check_output(["docker", "port", cid, "6333/tcp"], text=True)
    url = "http://" + port.strip().splitlines()[0]
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            if httpx.get(url + "/readyz", timeout=2).status_code == 200:
                return cid, url
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise AssertionError(f"Qdrant container {cid} never became ready")


class RecordingStore(B2ObjectStore):
    """The real B2 store, remembering every key this run wrote."""

    def __init__(self) -> None:
        self.written: set[str] = set()

    def put_bytes(self, key, data, content_type):
        self.written.add(key)
        super().put_bytes(key, data, content_type)

    def create_multipart(self, key, content_type):
        self.written.add(key)
        return super().create_multipart(key, content_type)


def _spec(tenant_id: str) -> dict:
    spec = next(s for s in SEED_TENANTS if s["tenant_id"] == tenant_id)
    return {
        "tenant_id": tenant_id,
        "display_name": spec["display_name"],
        "documents": [{"filename": n, "text": t} for n, t in spec["documents"].items()],
    }


def _hits(body: dict) -> list[tuple[str, int, float]]:
    return [(h["doc"], h["chunk"], h["score"]) for h in body["hits"]]


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_park_on_one_node_restore_on_a_fresh_node(monkeypatch):
    if os.environ.get("RUN_E2E_TIERING") != "1":
        pytest.skip("set RUN_E2E_TIERING=1 (pnpm test:e2e:tiering) to run against Docker and B2")
    if shutil.which("docker") is None:
        pytest.fail("Docker is required for the tiering end-to-end test")
    missing = [n for n in ("b2_application_key_id", "b2_application_key", "b2_bucket_name", "b2_region") if not getattr(settings, n)]
    if missing:
        pytest.fail(f"B2 credentials missing from .env: {missing}")

    from main import app

    run_prefix = f"e2e/{uuid.uuid4()}/"
    monkeypatch.setattr(settings, "rag_prefix", run_prefix + "rag/")
    image = _qdrant_image()
    store = RecordingStore()
    containers: list[str] = []
    try:
        cid_a, url_a = _start_node(image)
        containers.append(cid_a)
        deps.reset_backends()
        deps.set_backends(
            store=store,
            gateway=QdrantGateway(url_a),
            embedder=get_embedder(settings.embedding_model),
        )
        state.reset()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://e2e", timeout=600) as client:
            for tenant_id in QUERIES:
                r = await client.post("/tenants", json=_spec(tenant_id))
                assert r.status_code == 201, r.text
                assert r.json()["state"] == "hot"

            warm = {}
            for tenant_id, queries in QUERIES.items():
                r = await client.post(f"/tenants/{tenant_id}/query", json={"query": queries[0], "top_k": 3})
                assert r.status_code == 200, r.text
                warm[tenant_id] = _hits(r.json())
            assert warm["acme-legal"][0][0] == "supplier-contracts.md"

            # Policy park with a seconds-level threshold: only acme-legal is idle.
            state.touch("acme-legal", when=time.time() - 120)
            r = await client.post("/tiering/run", json={"idle_seconds": 60, "dry_run": False})
            assert r.status_code == 200, r.text
            assert r.json()["parked"] == ["acme-legal"], r.json()
            manifest = store.get_bytes(deps.manifest_key("acme-legal"))
            assert manifest is not None

            # A node that has never seen the tenant.
            cid_b, url_b = _start_node(image)
            containers.append(cid_b)
            deps.set_backends(gateway=QdrantGateway(url_b))

            r = await client.post(
                "/tenants/acme-legal/query",
                json={"query": QUERIES["acme-legal"][0], "top_k": 3},
            )
            body = r.json()
            assert r.status_code == 200, r.text
            assert body["restored"] is True
            after = _hits(body)
            assert [h[:2] for h in after] == [h[:2] for h in warm["acme-legal"]]
            for (_, _, s1), (_, _, s2) in zip(warm["acme-legal"], after, strict=True):
                assert abs(s1 - s2) <= TOLERANCE

            r = await client.post("/reports", json={"tenant_ids": ["acme-legal"], "queries_per_phase": 5})
            assert r.status_code == 200, r.text
            report = r.json()
            stored = store.get_bytes(deps.report_key(report["run_id"]))
            assert stored is not None
            entry = report["tenants"][0]
            assert entry["warm"]["n"] == 5 and entry["post_restore"]["n"] == 5
            assert entry["results_match"] is True
            assert entry["restore"]["total_ms"] > 0
    finally:
        try:
            if store.written:
                store.delete_keys(sorted(store.written))
            leftover = [e.key for e in store.list_objects(run_prefix)]
        finally:
            for cid in containers:
                subprocess.run(["docker", "rm", "-f", cid], capture_output=True, check=False)
            deps.reset_backends()
            state.reset()
    assert leftover == [], f"run prefix not empty after cleanup: {leftover}"
