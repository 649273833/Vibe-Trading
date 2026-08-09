"""Unit tests for run-level provider/model metadata on SwarmRun.

The fields capture which LLM provider/model the swarm was launched against
so ``.swarm/runs/<id>/run.json`` carries enough context for cost audits
and post-hoc debugging. The tests assert the new fields are accepted,
default cleanly, and that legacy run.json files (which predate the
fields) still parse — important because existing on-disk runs will be
re-read by ``SwarmStore.list_runs`` after this change.
"""

from __future__ import annotations

import pytest

import src.providers.llm as llm_mod
from src.config.accessor import reset_env_config
from src.swarm.models import SwarmRun
from src.swarm.runtime import SwarmRuntime
from src.swarm.store import SwarmStore


def _base_kwargs() -> dict:
    """Required-only kwargs for a SwarmRun instance."""
    return {
        "id": "swarm-test",
        "preset_name": "dummy_preset",
        "created_at": "2026-05-09T00:00:00+00:00",
    }


def test_provider_and_model_persist_on_construction() -> None:
    """Explicitly-supplied provider/model should appear in serialization."""
    run = SwarmRun(
        **_base_kwargs(),
        provider="openai",
        model="gpt-4o",
        reasoning_effort="max",
        use_responses_api=True,
    )

    assert run.provider == "openai"
    assert run.model == "gpt-4o"
    assert run.reasoning_effort == "max"
    assert run.use_responses_api is True

    # Round-trip through JSON to mirror the .swarm/runs/<id>/run.json path.
    blob = run.model_dump_json()
    rehydrated = SwarmRun.model_validate_json(blob)
    assert rehydrated.provider == "openai"
    assert rehydrated.model == "gpt-4o"
    assert rehydrated.reasoning_effort == "max"
    assert rehydrated.use_responses_api is True


def test_provider_and_model_default_to_none() -> None:
    """Both fields are optional and default to None."""
    run = SwarmRun(**_base_kwargs())

    assert run.provider is None
    assert run.model is None
    assert run.reasoning_effort is None
    assert run.use_responses_api is None


def test_runtime_loads_dotenv_before_capturing_provider_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LANGCHAIN_MODEL_NAME=smoke-model-from-dotenv\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LANGCHAIN_PROVIDER", "openai")
    monkeypatch.setenv("LANGCHAIN_REASONING_EFFORT", "max")
    monkeypatch.setenv("LANGCHAIN_USE_RESPONSES_API", "true")
    monkeypatch.delenv("LANGCHAIN_MODEL_NAME", raising=False)
    monkeypatch.setattr(llm_mod, "_ENV_CANDIDATES", [env_file])
    monkeypatch.setattr(llm_mod, "_dotenv_loaded", False)
    reset_env_config()
    monkeypatch.setattr(SwarmRuntime, "_execute_run", lambda *_: None)
    runtime = SwarmRuntime(store=SwarmStore(tmp_path / "runs"))

    run = runtime.start_run("risk_committee", {"goal": "smoke test"})

    assert run.provider == "openai"
    assert run.model == "smoke-model-from-dotenv"
    assert run.reasoning_effort == "max"
    assert run.use_responses_api is True


def test_runtime_resolves_unset_responses_api_to_false(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("LANGCHAIN_MODEL_NAME=smoke-model\n", encoding="utf-8")
    monkeypatch.setenv("LANGCHAIN_PROVIDER", "openai")
    monkeypatch.delenv("LANGCHAIN_USE_RESPONSES_API", raising=False)
    monkeypatch.setattr(llm_mod, "_ENV_CANDIDATES", [env_file])
    monkeypatch.setattr(llm_mod, "_dotenv_loaded", False)
    reset_env_config()
    monkeypatch.setattr(SwarmRuntime, "_execute_run", lambda *_: None)
    runtime = SwarmRuntime(store=SwarmStore(tmp_path / "runs"))

    run = runtime.start_run("risk_committee", {"goal": "smoke test"})

    assert run.use_responses_api is False


def test_runtime_redacts_sensitive_llm_metadata_before_persistence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LANGCHAIN_MODEL_NAME=api_key=must-not-be-persisted\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LANGCHAIN_PROVIDER", "openai")
    monkeypatch.setattr(llm_mod, "_ENV_CANDIDATES", [env_file])
    monkeypatch.setattr(llm_mod, "_dotenv_loaded", False)
    reset_env_config()
    monkeypatch.setattr(SwarmRuntime, "_execute_run", lambda *_: None)
    store = SwarmStore(tmp_path / "runs")
    runtime = SwarmRuntime(store=store)

    run = runtime.start_run("risk_committee", {"goal": "smoke test"})

    assert run.model == "[redacted]"
    assert store.load_run(run.id).model == "[redacted]"


def test_runtime_bounds_llm_metadata_before_persistence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"LANGCHAIN_MODEL_NAME={'x' * 129}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LANGCHAIN_PROVIDER", "openai")
    monkeypatch.setattr(llm_mod, "_ENV_CANDIDATES", [env_file])
    monkeypatch.setattr(llm_mod, "_dotenv_loaded", False)
    reset_env_config()
    monkeypatch.setattr(SwarmRuntime, "_execute_run", lambda *_: None)
    store = SwarmStore(tmp_path / "runs")
    runtime = SwarmRuntime(store=store)

    run = runtime.start_run("risk_committee", {"goal": "smoke test"})

    assert run.model == "[redacted]"
    assert store.load_run(run.id).model == "[redacted]"


def test_runtime_redacts_unsupported_reasoning_effort_before_persistence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LANGCHAIN_REASONING_EFFORT=unsupported\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LANGCHAIN_PROVIDER", "openai")
    monkeypatch.setattr(llm_mod, "_ENV_CANDIDATES", [env_file])
    monkeypatch.setattr(llm_mod, "_dotenv_loaded", False)
    reset_env_config()
    monkeypatch.setattr(SwarmRuntime, "_execute_run", lambda *_: None)
    store = SwarmStore(tmp_path / "runs")
    runtime = SwarmRuntime(store=store)

    run = runtime.start_run("risk_committee", {"goal": "smoke test"})

    assert run.reasoning_effort == "[redacted]"
    assert store.load_run(run.id).reasoning_effort == "[redacted]"


def test_legacy_run_json_without_provider_model_still_parses() -> None:
    """Existing run.json files predate provider/model and must still load.

    SwarmStore.get_run / list_runs reads on-disk JSON via
    ``SwarmRun.model_validate_json``. Adding required fields would silently
    break those flows; we want absent keys to deserialize to the default.
    """
    legacy_blob = (
        '{"id":"legacy-run","preset_name":"old","status":"completed",'
        '"created_at":"2026-01-01T00:00:00+00:00",'
        '"total_input_tokens":12345,"total_output_tokens":678}'
    )
    run = SwarmRun.model_validate_json(legacy_blob)

    assert run.id == "legacy-run"
    assert run.provider is None
    assert run.model is None
    assert run.reasoning_effort is None
    assert run.use_responses_api is None
    # Untouched fields still come through.
    assert run.total_input_tokens == 12345
    assert run.total_output_tokens == 678


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("anthropic", "claude-sonnet-4-5"),
        ("deepseek", "deepseek-v3"),
        ("openrouter", "openai/gpt-5"),
    ],
)
def test_accepts_other_providers(provider: str, model: str) -> None:
    """Field accepts any string — provider list is not enumerated at runtime."""
    run = SwarmRun(**_base_kwargs(), provider=provider, model=model)
    assert run.provider == provider
    assert run.model == model
