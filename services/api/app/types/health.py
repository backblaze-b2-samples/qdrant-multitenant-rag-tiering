from pydantic import Field

from app.types.base import ResponseModel


class QdrantHealth(ResponseModel):
    """Reachability of the hot tier."""

    ok: bool = Field(description="True when the Qdrant node answered.")
    version: str | None = Field(description="Server version reported by the node.")


class HealthStatus(ResponseModel):
    """Liveness plus B2 and Qdrant reachability.

    The route answers HTTP 200 even when a dependency is unreachable, so a
    caller must read `b2_connected` and `qdrant.ok` rather than the status code.
    """

    status: str = Field(description='"healthy" when B2 and Qdrant answered, else "degraded".')
    b2_connected: bool = Field(
        description="True when the bucket answered a cheap head request."
    )
    qdrant: QdrantHealth
