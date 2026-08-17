from __future__ import annotations

import json
import logging

from src.agent.tools import ToolRegistry


def test_missing_tool_reports_matching_import_failure() -> None:
    registry = ToolRegistry()
    registry.record_import_failure(
        "options_pricing_tool",
        "ImportError: No module named 'scipy'",
    )

    payload = json.loads(registry.execute("options_pricing", {}))

    assert payload["status"] == "error"
    assert payload["registry_incomplete"] is True
    assert payload["failed_source"] == "options_pricing_tool"
    assert "No module named 'scipy'" in payload["error"]


def test_build_registry_surfaces_aggregate_failure_warning(monkeypatch, caplog) -> None:
    import src.tools as tools_module

    monkeypatch.setattr(tools_module, "_discover_subclasses", lambda: [])
    monkeypatch.setattr(
        tools_module,
        "_DISCOVERY_FAILURES",
        {"options_pricing_tool": "ImportError: missing optional dependency"},
    )
    with caplog.at_level(logging.WARNING, logger="src.tools"):
        registry = tools_module.build_registry()

    assert registry.import_failures == {
        "options_pricing_tool": "ImportError: missing optional dependency"
    }
    assert (
        "Registered 0 local tools; 1 tool source(s) failed during registry construction"
        in caplog.messages
    )
