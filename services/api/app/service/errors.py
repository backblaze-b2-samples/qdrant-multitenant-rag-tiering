"""Service errors that carry their HTTP meaning, so routers stay one-liners."""


class ServiceError(Exception):
    status_code = 500

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class InvalidInput(ServiceError):
    status_code = 400


class NotFound(ServiceError):
    status_code = 404


class Conflict(ServiceError):
    status_code = 409


class StorageFailure(ServiceError):
    """B2 or Qdrant failed, or returned data that does not match its manifest."""

    status_code = 502
