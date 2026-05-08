from nango.adapters.providers import (
    get_provider,
    load_provider_scopes_yaml,
    load_providers_yaml,
)


def test_provider_yaml_loader_reads_existing_catalog_shape() -> None:
    providers = load_providers_yaml()

    assert providers["1password-scim"]["auth_mode"] == "API_KEY"
    assert providers["1password-scim"]["connection_config"]["domain"]["prefix"] == "https://"


def test_provider_yaml_loader_preserves_alias_overrides() -> None:
    providers = load_providers_yaml()

    assert providers["adp-lyric"]["auth_mode"] == "OAUTH2_CC"
    assert providers["adp-lyric"]["display_name"] == "ADP Lyric"
    assert providers["adp-lyric"]["credentials"] == providers["adp"]["credentials"]
    assert "alias" not in providers["adp-lyric"]


def test_provider_scopes_loader_reads_existing_scopes_file() -> None:
    scopes = load_provider_scopes_yaml()

    assert scopes["acuity-scheduling"] == ["api-v1"]


def test_localized_provider_loader_deep_merges_language_overrides() -> None:
    provider = get_provider("workday", language="fr")

    assert provider is not None
    assert provider["connection_config"]["hostname"]["title"] == "Nom d'hôte"
    assert provider["credentials"]["username"]["description"] == (
        "Nom d'utilisateur de l'API Workday"
    )
