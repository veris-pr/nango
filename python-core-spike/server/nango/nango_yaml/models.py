from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class YamlModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class ParserIssue(YamlModel):
    code: str
    message: str
    path: tuple[str, ...] = ()


FieldValue = str | int | float | bool | None | list["NangoModelField"]


class NangoModelField(YamlModel):
    name: str
    value: FieldValue
    array: bool = False
    optional: bool = False
    ts_type: bool = Field(default=False, alias="tsType")
    model: bool = False
    union: bool = False
    dynamic: bool = False


class NangoModel(YamlModel):
    name: str
    fields: tuple[NangoModelField, ...]
    is_anon: bool = Field(default=False, alias="isAnon")


class NangoEndpoint(YamlModel):
    method: str
    path: str
    group: str | None = None


class ParsedNangoScript(YamlModel):
    name: str
    type: Literal["sync", "action"]
    description: str = ""
    version: str = ""
    scopes: tuple[str, ...] = ()
    input: str | None = None
    output: tuple[str, ...] | None = None
    used_models: tuple[str, ...] = Field(default=(), alias="usedModels")
    features: tuple[str, ...] = ()


class ParsedNangoSync(ParsedNangoScript):
    type: Literal["sync"] = "sync"
    output: tuple[str, ...]
    runs: str
    sync_type: Literal["full", "incremental"] = "full"
    track_deletes: bool = False
    auto_start: bool = True
    endpoints: tuple[NangoEndpoint, ...] = ()
    webhook_subscriptions: tuple[str, ...] = Field(default=(), alias="webhookSubscriptions")


class ParsedNangoAction(ParsedNangoScript):
    type: Literal["action"] = "action"
    endpoint: NangoEndpoint | None = None


class ParsedOnEventScripts(YamlModel):
    post_connection_creation: tuple[str, ...] = Field(default=(), alias="post-connection-creation")
    pre_connection_deletion: tuple[str, ...] = Field(default=(), alias="pre-connection-deletion")
    validate_connection: tuple[str, ...] = Field(default=(), alias="validate-connection")


class ParsedNangoIntegration(YamlModel):
    provider_config_key: str = Field(alias="providerConfigKey")
    syncs: tuple[ParsedNangoSync, ...] = ()
    actions: tuple[ParsedNangoAction, ...] = ()
    on_event_scripts: ParsedOnEventScripts = Field(
        default_factory=ParsedOnEventScripts, alias="onEventScripts"
    )
    post_connection_scripts: tuple[str, ...] = Field(default=(), alias="postConnectionScripts")


class ParsedNangoYaml(YamlModel):
    yaml_version: Literal["v2"] = Field(default="v2", alias="yamlVersion")
    integrations: tuple[ParsedNangoIntegration, ...]
    models: dict[str, NangoModel]


class NangoYamlParseResult(YamlModel):
    parsed: ParsedNangoYaml | None
    errors: tuple[ParserIssue, ...] = ()
    warnings: tuple[ParserIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors and self.parsed is not None
