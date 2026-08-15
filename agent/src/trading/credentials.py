"""OS-backed secret storage for local trading connection instances."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Protocol

SERVICE_NAME = "Vibe-Trading"


class CredentialBackend(Protocol):
    def get_password(self, service_name: str, username: str) -> str | None: ...
    def set_password(self, service_name: str, username: str, password: str) -> None: ...
    def delete_password(self, service_name: str, username: str) -> None: ...


class CredentialStore:
    """Store secrets in Keychain/Credential Manager/Secret Service via keyring."""

    def __init__(self, backend: CredentialBackend | None = None) -> None:
        self._backend = backend

    @property
    def backend(self) -> CredentialBackend:
        if self._backend is None:
            import keyring

            self._backend = keyring
        return self._backend

    @staticmethod
    def reference(connection_id: str) -> str:
        return f"keyring://vibe-trading/{connection_id}"

    @staticmethod
    def _username(connection_id: str, field: str) -> str:
        return f"connection:{connection_id}:{field}"

    def save(self, connection_id: str, values: Mapping[str, str]) -> None:
        """Persist non-empty values; blank fields leave an existing secret unchanged."""
        for field, raw_value in values.items():
            value = str(raw_value or "").strip()
            if value:
                self.backend.set_password(
                    SERVICE_NAME,
                    self._username(connection_id, field),
                    value,
                )

    def load(self, connection_id: str, fields: Iterable[str]) -> dict[str, str]:
        values: dict[str, str] = {}
        for field in fields:
            value = self.backend.get_password(
                SERVICE_NAME,
                self._username(connection_id, field),
            )
            if value:
                values[field] = value
        return values

    def status(self, connection_id: str, fields: Iterable[str]) -> dict[str, bool]:
        result = {}
        for field in fields:
            try:
                result[field] = bool(
                    self.backend.get_password(
                        SERVICE_NAME,
                        self._username(connection_id, field),
                    )
                )
            except Exception:
                result[field] = False
        return result

    def delete(self, connection_id: str, fields: Iterable[str]) -> None:
        for field in fields:
            try:
                self.backend.delete_password(
                    SERVICE_NAME,
                    self._username(connection_id, field),
                )
            except Exception as exc:  # keyring backends differ on missing entries
                if "not found" not in str(exc).lower():
                    raise
