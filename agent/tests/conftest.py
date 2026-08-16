"""Shared fixtures and sys.path setup for all tests."""

from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure agent/ is on sys.path so imports like `backtest.*` and `src.*` work.
AGENT_DIR = Path(__file__).resolve().parent.parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

# --------------------------------------------------------------------------- #
# Sandbox the config runtime root BEFORE any test module is imported (#1116).
# --------------------------------------------------------------------------- #
# The suite must never resolve its config root against the real ~/.vibe-trading
# (live mandate + audit-ledger state). Modules in BOTH categories must resolve
# to a temp sandbox:
#
#   * Import-time-baked constants (bound when the module is first imported,
#     i.e. during collection): loop.RUNS_DIR/SESSIONS_DIR, goal/session
#     _DB_PATH, helpers.ENV_PATH, memory MEMORY_BASE, skills USER_SKILLS_DIR,
#     strategy_store _DEFAULT_DB_PATH, swarm presets USER_PRESETS_DIR,
#     qveris QVERIS_CONFIG_PATH.
#   * Runtime Path.home() call sites: redaction's internal-root anchors
#     (_internal_roots_for_cwd), alpha_bench report output (_default_output_dir),
#     autopilot run dirs, uploads shadow_reports.
#
# Because the import-time constants are baked during test-module collection, the
# sandbox cannot be a pytest fixture (fixtures run AFTER collection); it has to
# be installed at conftest import time, before pytest imports any test module.
#
# TEST DISCIPLINE: a test that asserts the DEFAULT config-root fallback (e.g.
# ``get_runtime_root() == Path.home()/".vibe-trading"``) MUST call
# ``monkeypatch.delenv("VIBE_TRADING_HOME", raising=False)`` first, so it
# exercises the real fallback instead of silently passing green against this
# sandbox.
#
# On Windows Path.home() ignores $HOME and reads %USERPROFILE%, so we set all
# three knobs: VIBE_TRADING_HOME (the project's documented Windows-safe
# override, src/config/paths.py:27-33), HOME (POSIX) and USERPROFILE (Windows).
_PRIOR_SANDBOX_ENV = {
    key: os.environ.get(key) for key in ("VIBE_TRADING_HOME", "HOME", "USERPROFILE")
}
_SANDBOX_HOME = Path(tempfile.mkdtemp(prefix="vibe-trading-test-home-"))
os.environ["VIBE_TRADING_HOME"] = str(_SANDBOX_HOME / ".vibe-trading")
os.environ["HOME"] = str(_SANDBOX_HOME)
os.environ["USERPROFILE"] = str(_SANDBOX_HOME)
(_SANDBOX_HOME / ".vibe-trading").mkdir(parents=True, exist_ok=True)


def _teardown_sandbox() -> None:
    shutil.rmtree(_SANDBOX_HOME, ignore_errors=True)
    for key, prior in _PRIOR_SANDBOX_ENV.items():
        if prior is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = prior


# Safety net for e.g. `--collect-only` (no fixtures run) and abnormal exits.
atexit.register(_teardown_sandbox)


@pytest.fixture(autouse=True, scope="session")
def _sandbox_runtime_root():
    """Guard the import-time sandbox and tear it down at session end.

    The environment (VIBE_TRADING_HOME/HOME/USERPROFILE) is installed at
    conftest import time above — before collection — so both import-time-baked
    constants and runtime ``Path.home()`` calls resolve to the temp sandbox,
    never the real ``~/.vibe-trading``. This fixture only asserts that the
    invariant is still active and removes the temp dir at session end. The
    function-scoped ``_reset_env_config`` fixture snapshots the environment each
    test, so the sandbox values survive every test while per-test monkeypatches
    still work.
    """
    assert os.environ["VIBE_TRADING_HOME"] == str(_SANDBOX_HOME / ".vibe-trading")
    assert os.environ["HOME"] == str(_SANDBOX_HOME)
    assert os.environ["USERPROFILE"] == str(_SANDBOX_HOME)
    yield _SANDBOX_HOME / ".vibe-trading"
    _teardown_sandbox()


@pytest.fixture(autouse=True)
def _reset_env_config():
    """Isolate each test from the process environment and the config cache.

    Two things leak between tests otherwise, and the second one bit us:

    1. The cached ``EnvConfig`` singleton, so ``monkeypatch.setenv`` would have
       no effect on anything already holding the cached instance.
    2. ``os.environ`` itself. The settings write path deliberately applies a
       written ``.env`` to the running process, which is correct in production
       (settings take effect without a restart) but means a settings TEST
       writing ``TUSHARE_TOKEN=ts-secret-token`` into a temp file leaks that
       value into the process for every test that follows. That is exactly how
       four live-data tests came to fail with "token is wrong" while passing in
       isolation -- and monkeypatch cannot undo it, because the test never went
       through monkeypatch to set it.

    Snapshotting and restoring the whole environment closes the class of bug
    rather than the one instance of it.
    """
    from src.config.accessor import reset_env_config

    saved_environ = dict(os.environ)
    reset_env_config()
    yield
    os.environ.clear()
    os.environ.update(saved_environ)
    reset_env_config()
