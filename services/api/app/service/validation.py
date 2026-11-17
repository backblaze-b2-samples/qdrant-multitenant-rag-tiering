"""Identifiers that become B2 keys and Qdrant collection names."""

import re

from app.service.errors import InvalidInput
from app.types.tenants import TENANT_ID_PATTERN

_TENANT_ID = re.compile(TENANT_ID_PATTERN)
# Letters/digits first (so never "_tenant.json" or a dotfile), no separators,
# and only the text formats the embedder reads.
_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,95}\.(md|txt)$")
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,63}$")


def validate_tenant_id(tenant_id: str) -> None:
    if not _TENANT_ID.fullmatch(tenant_id or ""):
        raise InvalidInput(
            "Tenant id must be lowercase letters, digits and hyphens, 2 to 40 "
            "characters, starting and ending with a letter or digit."
        )


def validate_filename(filename: str) -> None:
    if not _FILENAME.fullmatch(filename or "") or ".." in filename:
        raise InvalidInput(
            f"Invalid document name {filename!r}: use a .txt or .md file name of "
            "letters, digits, spaces, dots, hyphens or underscores."
        )


def validate_run_id(run_id: str) -> None:
    if not _RUN_ID.fullmatch(run_id or ""):
        raise InvalidInput("Invalid report id.")
