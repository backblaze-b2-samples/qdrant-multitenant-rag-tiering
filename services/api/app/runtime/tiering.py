"""Tiering policy, sweep, stats and snapshot pruning routes."""

from fastapi import APIRouter

from app.runtime import metrics
from app.runtime.errors import http_errors
from app.service import prune, tiering
from app.types.tiering import (
    PruneRequest,
    PruneResult,
    TieringPolicy,
    TieringRunRequest,
    TieringRunResult,
    TieringStats,
)

router = APIRouter()


@router.get("/tiering/policy", response_model=TieringPolicy)
def policy_endpoint():
    return tiering.get_policy()


@router.post("/tiering/run", response_model=TieringRunResult)
async def run_endpoint(body: TieringRunRequest):
    """Find idle hot tenants; park them unless `dry_run` (the default)."""
    with http_errors():
        result = await tiering.run_policy(body)
    for _ in result.parked:
        metrics.record_park()
    return result


@router.get("/tiering/stats", response_model=TieringStats)
def stats_endpoint():
    with http_errors():
        return tiering.get_stats()


@router.post("/snapshots/prune", response_model=PruneResult)
def prune_endpoint(body: PruneRequest):
    """409 unless SNAPSHOT_PRUNE_ENABLED; deletes only with `apply`."""
    with http_errors():
        return prune.prune_snapshots(body)
