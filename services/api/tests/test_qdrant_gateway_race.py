"""A collection dropped between the existence check and the read is "absent".

The UI polls a tenant every second while it parks; a poll that lands in the
`dropping` step used to 500 (Qdrant 404 from get_collection) instead of
falling back to the manifest figures.
"""

import httpx
from qdrant_client.http.exceptions import UnexpectedResponse

from app.repo.qdrant_gateway import QdrantGateway


class _DroppedMidRead:
    def collection_exists(self, name):
        return True

    def get_collection(self, name):
        raise UnexpectedResponse(
            status_code=404,
            reason_phrase="Not Found",
            content=b'{"status":{"error":"Not found: Collection doesn\'t exist!"}}',
            headers=httpx.Headers(),
        )


def test_collection_stats_is_none_when_dropped_mid_read():
    gateway = QdrantGateway("http://localhost:6333")
    gateway.client = _DroppedMidRead()

    assert gateway.collection_stats("tenant_gone") is None
