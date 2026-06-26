"""Bearer token authentication for KUN runtime HTTP API.

Aligns with KUN server auth check.
"""

from __future__ import annotations

from typing import Any


class BearerTokenAuth:
    """Simple bearer token authenticator.

    When *insecure* is True, all requests are allowed.
    When *insecure* is False, requests must include
    ``Authorization: Bearer <token>``.
    """

    def __init__(self, token: str, insecure: bool = False):
        self._token = token
        self.insecure = insecure

    def verify(self, authorization: str | None) -> bool:
        """Return True if the authorization header is valid."""
        if self.insecure:
            return True
        if not authorization:
            return False
        return authorization == f"Bearer {self._token}"

    @staticmethod
    def extract_bearer(headers: dict[str, Any] | None) -> str | None:
        """Extract the Bearer token from headers dict."""
        if not headers:
            return None
        auth = headers.get("authorization") or headers.get("Authorization") or ""
        if auth.startswith("Bearer "):
            return auth[7:]
        return auth
