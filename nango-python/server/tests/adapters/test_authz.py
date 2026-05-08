from nango.adapters.authz import Permission, permissions


def test_authz_catalog_matches_representative_ts_permissions() -> None:
    assert permissions["canManageTeam"] == Permission("update", "team", "global")
    assert permissions["canAccessProdEnvironment"] == Permission(
        "read", "environment", "production"
    )
    assert permissions["canUseProdPlayground"].as_string() == (
        "update:sync_command:production"
    )
    assert len(permissions) == 24
