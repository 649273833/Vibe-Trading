"""Discovery and loading of user-owned, read-only connector plugins."""

from __future__ import annotations

import importlib.util
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from src.config.paths import get_runtime_root
from src.trading.types import READ_CAPABILITIES, TradingProfile

MANIFEST_FILENAME = "connector.json"
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_REQUIRED_CAPABILITIES = {"account.read", "positions.read"}
_ALLOWED_CAPABILITIES = frozenset(READ_CAPABILITIES)


@dataclass(frozen=True)
class CredentialField:
    name: str
    label: str
    secret: bool = True
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "secret": self.secret,
            "required": self.required,
        }


@dataclass(frozen=True)
class LocalConnectorPlugin:
    profile: TradingProfile
    directory: Path
    entrypoint: str
    auth_type: str
    credential_fields: tuple[CredentialField, ...]

    @property
    def module_path(self) -> Path:
        return self.directory / self.entrypoint

    def public_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile.id,
            "directory": str(self.directory),
            "auth_type": self.auth_type,
            "credential_fields": [field.to_dict() for field in self.credential_fields],
        }


def plugin_root() -> Path:
    return get_runtime_root() / "connectors"


def parse_manifest(path: Path) -> LocalConnectorPlugin:
    """Validate a local manifest as a strictly read-only connector contract."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid connector manifest at {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("connector manifest schema_version must be 1")
    profile_data = payload.get("profile")
    if not isinstance(profile_data, dict):
        raise ValueError("connector manifest profile must be an object")
    profile_id = str(profile_data.get("id") or "").strip().lower()
    connector = str(profile_data.get("connector") or "").strip().lower()
    if not _ID_RE.fullmatch(profile_id) or not _ID_RE.fullmatch(connector):
        raise ValueError(
            "connector and profile ids must use lowercase letters, numbers, dot, dash, or underscore"
        )
    capabilities = tuple(
        str(value).strip().lower() for value in profile_data.get("capabilities", [])
    )
    if not bool(profile_data.get("readonly")) or not _REQUIRED_CAPABILITIES.issubset(
        capabilities
    ):
        raise ValueError(
            "local connector plugins must be read-only and expose account.read + positions.read"
        )
    unsupported = sorted(set(capabilities) - _ALLOWED_CAPABILITIES)
    if unsupported:
        raise ValueError(
            "local connector plugins may declare read capabilities only: "
            + ", ".join(unsupported)
        )
    environment = str(profile_data.get("environment") or "live").strip().lower()
    if environment not in {"paper", "live"}:
        raise ValueError("connector environment must be paper or live")
    label = str(profile_data.get("label") or profile_id).strip()
    if not label or len(label) > 100:
        raise ValueError("connector label must contain 1 to 100 characters")
    entrypoint = str(payload.get("entrypoint") or "adapter.py").strip()
    if Path(entrypoint).name != entrypoint or not entrypoint.endswith(".py"):
        raise ValueError(
            "connector entrypoint must be a Python file in the manifest directory"
        )
    module_path = path.parent / entrypoint
    if not module_path.is_file():
        raise ValueError(f"connector entrypoint does not exist: {module_path}")
    auth = payload.get("auth") if isinstance(payload.get("auth"), dict) else {}
    fields: list[CredentialField] = []
    for raw in auth.get("fields", []):
        if not isinstance(raw, dict):
            raise ValueError("auth fields must be objects")
        name = str(raw.get("name") or "").strip().lower()
        if not _FIELD_RE.fullmatch(name):
            raise ValueError(f"invalid credential field: {name or '?'}")
        fields.append(
            CredentialField(
                name=name,
                label=str(raw.get("label") or name.replace("_", " ").title()).strip(),
                secret=bool(raw.get("secret", True)),
                required=bool(raw.get("required", True)),
            )
        )
    profile = TradingProfile(
        id=profile_id,
        connector=connector,
        label=label,
        environment=environment,  # type: ignore[arg-type]
        transport="local_plugin",
        capabilities=capabilities,
        readonly=True,
        config={"plugin_directory": str(path.parent)},
        notes=str(
            profile_data.get("notes") or "User-installed local read-only connector."
        ).strip(),
    )
    return LocalConnectorPlugin(
        profile=profile,
        directory=path.parent,
        entrypoint=entrypoint,
        auth_type=str(auth.get("type") or "none").strip().lower(),
        credential_fields=tuple(fields),
    )


def discover_plugins(
    root: Path | None = None,
) -> tuple[list[LocalConnectorPlugin], list[dict[str, str]]]:
    """Discover valid plugins and return field-safe diagnostics for invalid ones."""
    directory = root or plugin_root()
    if not directory.exists():
        return [], []
    plugins: list[LocalConnectorPlugin] = []
    errors: list[dict[str, str]] = []
    for manifest in sorted(directory.glob(f"*/{MANIFEST_FILENAME}")):
        try:
            plugins.append(parse_manifest(manifest))
        except ValueError as exc:
            errors.append({"directory": manifest.parent.name, "error": str(exc)[:300]})
    return plugins, errors


def plugin_by_profile_id(profile_id: str) -> LocalConnectorPlugin:
    plugins, _ = discover_plugins()
    for plugin in plugins:
        if plugin.profile.id == profile_id:
            return plugin
    raise ValueError(f"unknown local connector plugin profile: {profile_id}")


def load_adapter(plugin: LocalConnectorPlugin) -> ModuleType:
    """Load a plugin selected by the local operator from its private directory."""
    module_name = (
        f"vibe_local_connector_{plugin.profile.id.replace('-', '_').replace('.', '_')}"
    )
    spec = importlib.util.spec_from_file_location(module_name, plugin.module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load connector adapter: {plugin.profile.id}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for operation in ("check_status", "get_account_snapshot", "get_positions"):
        if not callable(getattr(module, operation, None)):
            raise RuntimeError(f"local connector adapter is missing {operation}()")
    return module
