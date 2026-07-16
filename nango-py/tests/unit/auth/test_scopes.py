"""Scope wildcard semantics — mirrors ``packages/server/lib/middleware/scope.middleware.ts``."""

from __future__ import annotations

from nango_py.auth.domain.context import Scopes


def test_exact_scope_matches() -> None:
    scopes = Scopes(("environment:integrations:read",))
    assert scopes.has("environment:integrations:read")


def test_environment_wildcard_grants_all_environment_scopes() -> None:
    scopes = Scopes(("environment:*",))
    assert scopes.has("environment:integrations:read")
    assert scopes.has("environment:integrations:read_credentials")
    assert scopes.has("environment:connections:write")


def test_wildcard_does_not_cross_namespace() -> None:
    scopes = Scopes(("environment:*",))
    assert not scopes.has("account:environments:create")


def test_non_wildcard_prefix_does_not_match() -> None:
    scopes = Scopes(("environment:integrations",))
    assert not scopes.has("environment:integrations:read")


def test_empty_scopes_match_nothing() -> None:
    scopes = Scopes(())
    assert not scopes.has("environment:integrations:read")
    assert not scopes.has_any(("environment:integrations:read",))


def test_has_any_satisfied_by_one() -> None:
    scopes = Scopes(("environment:connections:read",))
    assert scopes.has_any(
        ("environment:integrations:read", "environment:connections:read")
    )


def test_has_any_unsatisfied() -> None:
    scopes = Scopes(("environment:connections:read",))
    assert not scopes.has_any(
        ("environment:integrations:read", "environment:integrations:read_credentials")
    )