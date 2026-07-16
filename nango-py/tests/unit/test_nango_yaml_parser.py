from __future__ import annotations

from pathlib import Path

import pytest

from nango_py.nango_yaml import NangoYamlParseError, parse_nango_yaml_text, validate_nango_yaml_text

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "nango_yaml"


def fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text()


def issue_codes(yaml_name: str) -> set[str]:
    result = validate_nango_yaml_text(fixture(yaml_name))
    return {issue.code for issue in result.errors}


def test_parse_representative_v2_config() -> None:
    parsed = parse_nango_yaml_text(fixture("valid.v2.yaml"))

    integration = parsed.integrations[0]
    assert parsed.yaml_version == "v2"
    assert integration.provider_config_key == "github-demo"
    assert integration.on_event_scripts.post_connection_creation == ("seedGithub",)

    sync = integration.syncs[0]
    assert sync.name == "issues"
    assert sync.output == ("GithubIssue",)
    assert sync.input == "CreateIssueInput"
    assert sync.endpoints[0].method == "GET"
    assert sync.endpoints[0].path == "/repos/{GithubUser:id}/issues"
    assert sync.scopes == ("repo", "read:user")
    assert set(sync.used_models) == {"GithubIssue", "GithubUser", "CreateIssueInput"}

    action = integration.actions[0]
    assert action.name == "createIssue"
    assert action.endpoint is not None
    assert action.endpoint.method == "POST"
    assert action.scopes == ("repo",)

    issue = parsed.models["GithubIssue"]
    assert [field.name for field in issue.fields] == ["id", "title", "user"]
    assert issue.fields[2].optional is True
    assert issue.fields[2].model is True


def test_validate_duplicate_endpoint_within_integration() -> None:
    assert "duplicate_endpoint" in issue_codes("invalid.duplicate-endpoint.yaml")


def test_validate_sync_output_model_has_id() -> None:
    assert "model_missing_id" in issue_codes("invalid.missing-output-id.yaml")


def test_validate_invalid_top_level_shape() -> None:
    result = validate_nango_yaml_text(fixture("invalid.top-level.yaml"))

    assert result.parsed is None
    assert [issue.code for issue in result.errors] == ["invalid_top_level_shape"]


def test_validate_missing_integration_and_script_names() -> None:
    assert issue_codes("invalid.missing-names.yaml") == {
        "missing_integration_name",
        "missing_script_name",
    }


def test_parse_raises_for_invalid_config() -> None:
    with pytest.raises(NangoYamlParseError) as raised:
        parse_nango_yaml_text(fixture("invalid.duplicate-endpoint.yaml"))

    assert [issue.code for issue in raised.value.issues] == ["duplicate_endpoint"]
