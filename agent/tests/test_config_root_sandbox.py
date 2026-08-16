"""Regression tests for the sandboxed runtime root (issue #1116).

The test suite must never resolve its config root against the real home
directory. On Windows, ``Path.home()`` ignores ``$HOME`` and reads
``%USERPROFILE%``, so the suite's historical ``HOME``-based isolation idiom is
inert there and tests leaked into the real ``~/.vibe-trading`` (including the
live audit ledger). ``conftest.py`` installs ``VIBE_TRADING_HOME``/``HOME``/
``USERPROFILE`` at import time (before collection, so import-time-baked
constants also resolve there) to a temp sandbox root — the project's documented
Windows-safe override — and these tests pin that contract.

NOTE: the base-failure signature of these tests depends on ``VIBE_TRADING_HOME``
being unset in the ambient environment. A CI runner that pre-sets it (rather
than letting ``conftest.py`` install the sandbox) would not see the red/green
regression signal this file is meant to produce.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from src.config.paths import get_runtime_root
from src.live.audit import audit_ledger_path
from src.live.paths import live_root


def test_sandbox_runtime_root_is_active() -> None:
    """The import-time sandbox must have pointed the runtime root at a sandbox."""
    sandbox_root = os.environ.get("VIBE_TRADING_HOME")
    assert sandbox_root, (
        "VIBE_TRADING_HOME is unset — the conftest sandbox is not active; "
        "without it tests resolve the real ~/.vibe-trading (issue #1116)"
    )
    sandbox_root = Path(sandbox_root)

    # The root must live under the system temp dir — a temp sandbox, not a
    # non-temp value a broken setup could otherwise point VIBE_TRADING_HOME at.
    assert sandbox_root.is_relative_to(Path(tempfile.gettempdir()))
    assert sandbox_root.is_absolute()
    assert get_runtime_root() == sandbox_root


def test_windows_home_semantics_still_resolve_under_sandbox_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Windows ``Path.home()`` ignores ``HOME``; it must not escape the sandbox.

    Simulates the Windows failure from issue #1116: a fake "real home" is
    installed into BOTH ``HOME`` and ``USERPROFILE`` (Windows ``Path.home()``
    reads the latter). The runtime root must still resolve under the sandbox
    ``VIBE_TRADING_HOME``, never under the fake real home.
    """
    fake_real_home = tmp_path / "real-home"
    monkeypatch.setenv("HOME", str(fake_real_home))
    monkeypatch.setenv("USERPROFILE", str(fake_real_home))

    sandbox_root = os.environ.get("VIBE_TRADING_HOME")
    assert sandbox_root, (
        "VIBE_TRADING_HOME is unset — the conftest sandbox is not active; "
        "without it get_runtime_root() falls back to Path.home()/.vibe-trading, "
        "which resolves to the fake real home under Windows HOME/USERPROFILE "
        "semantics (issue #1116)"
    )
    sandbox_root = Path(sandbox_root)

    # Temp sandbox, not the real home — same mutation-gap closure as Test 1.
    assert sandbox_root.is_relative_to(Path(tempfile.gettempdir()))
    assert get_runtime_root() == sandbox_root
    assert get_runtime_root() != fake_real_home / ".vibe-trading"
    assert live_root() == sandbox_root / "live"
    # The issue's headline harm: the live audit ledger must also resolve under the
    # sandbox, never the real ~/.vibe-trading.
    assert audit_ledger_path() == sandbox_root / "live" / "audit.jsonl"
