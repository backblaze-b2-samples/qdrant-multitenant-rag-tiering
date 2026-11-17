"""Latency benchmark routes."""

from fastapi import APIRouter

from app.runtime.errors import http_errors
from app.service import reports
from app.types.reports import BenchmarkRequest, LatencyReport, ReportSummary

router = APIRouter()


@router.post("/reports", response_model=LatencyReport)
async def run_benchmark_endpoint(body: BenchmarkRequest):
    """Warm, park, restore-on-query and post-restore timings; writes report.json."""
    with http_errors():
        return await reports.run_benchmark(body)


@router.get("/reports", response_model=list[ReportSummary])
def list_reports_endpoint():
    with http_errors():
        return reports.list_reports()


@router.get("/reports/{run_id}", response_model=LatencyReport)
def get_report_endpoint(run_id: str):
    with http_errors():
        return reports.get_report(run_id)
