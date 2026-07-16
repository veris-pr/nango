from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import yaml  # type: ignore[import-untyped]

from nango_py.nango_yaml.errors import NangoYamlParseError
from nango_py.nango_yaml.models import (
    FieldValue,
    NangoEndpoint,
    NangoModel,
    NangoModelField,
    NangoYamlParseResult,
    ParsedNangoAction,
    ParsedNangoIntegration,
    ParsedNangoSync,
    ParsedNangoYaml,
    ParsedOnEventScripts,
    ParserIssue,
)

MODEL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")
ENDPOINT_MODEL_PATTERN = re.compile(r"{([^}]+)}")

TYPE_ALIASES = {
    "integer": "number",
    "int": "number",
    "char": "string",
    "varchar": "string",
    "float": "number",
    "bool": "boolean",
    "string": "string",
    "number": "number",
    "never": "never",
    "void": "void",
    "boolean": "boolean",
    "bigint": "bigint",
    "date": "Date",
    "object": "Record<string, any>",
    "any": "any",
    "array": "any[]",
    "undefined": "undefined",
}
DISALLOWED_GENERIC_PREFIXES = (
    "Object<",
    "Array<",
    "Function<",
    "Date<",
    "RegExp<",
    "Map<",
    "Set<",
    "WeakMap<",
    "WeakSet<",
    "Promise<",
    "Symbol<",
    "Error<",
    "Record<",
    "Partial<",
    "Readonly<",
    "Pick<",
    "Omit<",
    "Awaited<",
    "Required<",
    "Exclude<",
    "Extract<",
    "Uppercase<",
    "Lowercase<",
)

RawMap = Mapping[str, object]


def validate_nango_yaml_text(yaml_text: str) -> NangoYamlParseResult:
    try:
        raw = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        issue = ParserIssue(code="invalid_yaml", message=str(exc), path=())
        return NangoYamlParseResult(parsed=None, errors=(issue,))

    parser = NangoYamlV2Parser(raw)
    return parser.parse()


def parse_nango_yaml_text(yaml_text: str) -> ParsedNangoYaml:
    result = validate_nango_yaml_text(yaml_text)
    if not result.ok or result.parsed is None:
        raise NangoYamlParseError(result.errors)
    return result.parsed


def load_nango_yaml_file(path: str | Path) -> ParsedNangoYaml:
    return parse_nango_yaml_text(Path(path).read_text())


class ModelsParser:
    def __init__(self, raw_models: RawMap) -> None:
        self.raw_models = raw_models
        self.parsed: dict[str, NangoModel] = {}
        self.errors: list[ParserIssue] = []
        self.warnings: list[ParserIssue] = []

    def parse_all(self) -> None:
        for name, fields in self.raw_models.items():
            if not MODEL_NAME_PATTERN.match(name):
                self.errors.append(
                    ParserIssue(
                        code="invalid_model_name",
                        message=f'Model "{name}" contains invalid characters',
                        path=(name,),
                    )
                )
                continue
            if name not in self.parsed:
                self._parse_one(name, fields, (name,))

    def get(self, name: str) -> NangoModel | None:
        return self.parsed.get(name)

    def parse_anonymous_model(self, name: str, field_name: str, raw_type: object) -> NangoModel:
        fields = self.parse_fields({field_name: raw_type}, (name,))
        model = NangoModel(name=name, fields=tuple(fields), isAnon=True)
        self.parsed[name] = model
        return model

    def parse_fields(self, fields: object, stack: tuple[str, ...]) -> list[NangoModelField]:
        if isinstance(fields, Mapping):
            entries = [(str(key), value) for key, value in fields.items()]
        elif isinstance(fields, Sequence) and not isinstance(fields, str | bytes):
            entries = [(str(index), value) for index, value in enumerate(fields)]
        else:
            self.errors.append(
                ParserIssue(
                    code="invalid_model_shape",
                    message="Model fields must be a mapping or array",
                    path=stack,
                )
            )
            return []

        parsed: dict[str, NangoModelField] = {}
        dynamic_field: NangoModelField | None = None
        parent = stack[-1] if stack else "models"

        for raw_name, value in entries:
            optional = raw_name.endswith("?")
            name = raw_name[:-1] if optional else raw_name

            if name == "__extends":
                for inherited_name in str(value).split(","):
                    inherited_name = inherited_name.strip()
                    if not self._ensure_model_parsed(inherited_name, stack):
                        self.errors.append(
                            ParserIssue(
                                code="model_extends_not_found",
                                message=(
                                    f'Model "{parent}" is extending "{inherited_name}", '
                                    "but it does not exists"
                                ),
                                path=(*stack, "__extends"),
                            )
                        )
                        continue
                    inherited = self.parsed[inherited_name]
                    for field in inherited.fields:
                        if field.dynamic:
                            dynamic_field = field
                        else:
                            parsed.setdefault(field.name, field)
                continue

            if name == "__string":
                nested = self.parse_fields({"tmp": value}, stack)
                if nested:
                    dynamic_field = nested[0].model_copy(
                        update={"name": name, "dynamic": True, "optional": optional}
                    )
                continue

            parsed[name] = self._parse_field(name, value, optional, parent, stack)

        if dynamic_field is not None:
            parsed[dynamic_field.name] = dynamic_field
        return list(parsed.values())

    def _parse_one(self, name: str, fields: object, stack: tuple[str, ...]) -> None:
        self.parsed[name] = NangoModel(name=name, fields=tuple(self.parse_fields(fields, stack)))

    def _parse_field(
        self, name: str, value: object, optional: bool, parent: str, stack: tuple[str, ...]
    ) -> NangoModelField:
        if isinstance(value, Sequence) and not isinstance(value, str | bytes):
            nested = self.parse_fields(value, stack)
            return NangoModelField(name=name, value=nested, array=True, optional=optional)

        if isinstance(value, bool | int | float) or value is None:
            return NangoModelField(name=name, value=value, tsType=True, optional=optional)

        if isinstance(value, Mapping):
            nested = self.parse_fields(value, stack)
            return NangoModelField(name=name, value=nested, optional=optional)

        raw_value = str(value)
        if "|" in raw_value:
            union_fields = self.parse_fields([part.strip() for part in raw_value.split("|")], stack)
            return NangoModelField(name=name, value=union_fields, union=True, optional=optional)

        is_array = raw_value.endswith("[]")
        value_clean = raw_value[:-2] if is_array else raw_value
        if not value_clean:
            self.errors.append(
                ParserIssue(
                    code="type_syntax_error",
                    message='Type "" contains unsupported TypeScript syntax',
                    path=(parent, name),
                )
            )
            return NangoModelField(name=name, value=value_clean, array=is_array, optional=optional)

        native = _native_data_type(value_clean)
        if native is not _NO_NATIVE_VALUE:
            return NangoModelField(
                name=name,
                value=cast(FieldValue, native),
                tsType=True,
                array=is_array,
                optional=optional,
            )

        alias = TYPE_ALIASES.get(value_clean.lower())
        if alias is not None:
            return NangoModelField(
                name=name,
                value=alias,
                tsType=True,
                array=is_array,
                optional=optional,
            )

        if value_clean.startswith(DISALLOWED_GENERIC_PREFIXES):
            self.errors.append(
                ParserIssue(
                    code="type_syntax_error",
                    message=f'Type "{value_clean}" contains unsupported TypeScript syntax',
                    path=(parent, name),
                )
            )
            return NangoModelField(name=name, value=value_clean, array=is_array, optional=optional)

        if self._ensure_model_parsed(value_clean, stack):
            return NangoModelField(
                name=name,
                value=value_clean,
                model=True,
                array=is_array,
                optional=optional,
            )

        return NangoModelField(name=name, value=value_clean, array=is_array, optional=optional)

    def _ensure_model_parsed(self, name: str, stack: tuple[str, ...]) -> bool:
        if name in stack:
            self.warnings.append(
                ParserIssue(
                    code="cyclic_model",
                    message=f"Cyclic import {stack[0]}->{name}",
                    path=stack,
                )
            )
            return True
        if name in self.parsed:
            return True
        raw = self.raw_models.get(name)
        if raw is None:
            self.warnings.append(
                ParserIssue(
                    code="model_not_found_fallback",
                    message=f'Model "{name}" is not defined, using as string literal',
                    path=(*stack, name),
                )
            )
            return False
        self._parse_one(name, raw, (*stack, name))
        return True


_NO_NATIVE_VALUE = object()


def _native_data_type(value: str) -> object:
    try:
        return int(value)
    except ValueError:
        pass
    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower == "null":
        return None
    if lower == "undefined":
        return "undefined"
    return _NO_NATIVE_VALUE


class NangoYamlV2Parser:
    def __init__(self, raw: object) -> None:
        self.raw = raw
        self.errors: list[ParserIssue] = []
        self.warnings: list[ParserIssue] = []
        self.models_parser = ModelsParser({})

    def parse(self) -> NangoYamlParseResult:
        if not isinstance(self.raw, Mapping):
            return self._failed_top_level("nango.yaml must be a mapping")

        integrations = self.raw.get("integrations")
        if not isinstance(integrations, Mapping) or not integrations:
            return self._failed_top_level("v2 nango.yaml must define an integrations mapping")

        raw_models = self.raw.get("models", {})
        if raw_models is None:
            raw_models = {}
        if not isinstance(raw_models, Mapping):
            return self._failed_top_level("models must be a mapping when present")

        self.models_parser = ModelsParser(_string_key_mapping(raw_models))
        self.models_parser.parse_all()
        self.errors.extend(self.models_parser.errors)
        self.warnings.extend(self.models_parser.warnings)

        parsed_integrations = [
            self._parse_integration(str(name), value)
            for name, value in integrations.items()
            if self._valid_integration_name(str(name))
        ]

        parsed = ParsedNangoYaml(
            integrations=tuple(integration for integration in parsed_integrations if integration),
            models=self.models_parser.parsed,
        )
        self._post_parse_validate(parsed)
        return NangoYamlParseResult(
            parsed=parsed,
            errors=tuple(self.errors),
            warnings=tuple(self.warnings),
        )

    def _failed_top_level(self, message: str) -> NangoYamlParseResult:
        return NangoYamlParseResult(
            parsed=None,
            errors=(ParserIssue(code="invalid_top_level_shape", message=message, path=()),),
        )

    def _valid_integration_name(self, name: str) -> bool:
        if name.strip():
            return True
        self.errors.append(
            ParserIssue(
                code="missing_integration_name",
                message="Integration names must be non-empty strings",
                path=("integrations",),
            )
        )
        return False

    def _parse_integration(
        self, integration_name: str, raw_integration: object
    ) -> ParsedNangoIntegration | None:
        if not isinstance(raw_integration, Mapping):
            self.errors.append(
                ParserIssue(
                    code="invalid_integration_shape",
                    message="Integration configuration must be a mapping",
                    path=(integration_name,),
                )
            )
            return None

        raw_syncs = _optional_mapping(
            raw_integration.get("syncs"), integration_name, "syncs", self.errors
        )
        raw_actions = _optional_mapping(
            raw_integration.get("actions"), integration_name, "actions", self.errors
        )
        post_connection_scripts = _string_tuple(raw_integration.get("post-connection-scripts"))
        on_events = _optional_mapping(
            raw_integration.get("on-events"), integration_name, "on-events", self.errors
        )
        if post_connection_scripts and on_events:
            self.errors.append(
                ParserIssue(
                    code="both_post_connection_scripts_and_on_events_present",
                    message="Both post-connection-scripts and on-events are present",
                    path=(integration_name, "on-events"),
                )
            )

        return ParsedNangoIntegration(
            providerConfigKey=integration_name,
            syncs=tuple(
                parsed_sync
                for sync_name, raw_sync in raw_syncs.items()
                if (parsed_sync := self._parse_sync(integration_name, str(sync_name), raw_sync))
                is not None
            ),
            actions=tuple(
                parsed_action
                for action_name, raw_action in raw_actions.items()
                if (
                    parsed_action := self._parse_action(
                        integration_name, str(action_name), raw_action
                    )
                )
                is not None
            ),
            onEventScripts=ParsedOnEventScripts(
                **{
                    "post-connection-creation": _string_tuple(
                        on_events.get("post-connection-creation")
                    ),
                    "pre-connection-deletion": _string_tuple(
                        on_events.get("pre-connection-deletion")
                    ),
                    "validate-connection": _string_tuple(on_events.get("validate-connection")),
                }
            ),
            postConnectionScripts=post_connection_scripts,
        )

    def _parse_sync(
        self, integration_name: str, sync_name: str, raw_sync: object
    ) -> ParsedNangoSync | None:
        if not self._valid_script(integration_name, "syncs", sync_name, raw_sync):
            return None
        sync_mapping = cast(RawMap, raw_sync)

        raw_output = sync_mapping.get("output")
        if raw_output is None:
            self.errors.append(
                ParserIssue(
                    code="missing_output",
                    message=f'Sync "{sync_name}" must define output',
                    path=(integration_name, "syncs", sync_name, "output"),
                )
            )
            return None

        output_models = self._models_for_output(raw_output, sync_name, "sync", integration_name)
        input_model = self._model_for_input(
            sync_mapping.get("input"), sync_name, "sync", integration_name
        )
        endpoints = self._parse_sync_endpoints(
            sync_mapping.get("endpoint"), len(output_models), integration_name, sync_name
        )
        webhook_subscriptions = _string_tuple(sync_mapping.get("webhook-subscriptions"))
        used_models = self._used_model_names(
            (*output_models, *(tuple([input_model]) if input_model else ()))
        )

        return ParsedNangoSync(
            name=sync_name,
            description=str(sync_mapping.get("description") or "").strip(),
            runs=str(sync_mapping.get("runs") or ""),
            version=str(sync_mapping.get("version") or ""),
            sync_type="incremental"
            if str(sync_mapping.get("sync_type") or "").lower() == "incremental"
            else "full",
            track_deletes=bool(sync_mapping.get("track_deletes") or False),
            auto_start=sync_mapping.get("auto_start") is not False,
            input=input_model.name if input_model else None,
            output=tuple(model.name for model in output_models),
            scopes=_scopes(sync_mapping.get("scopes")),
            endpoints=endpoints,
            webhookSubscriptions=webhook_subscriptions,
            usedModels=used_models,
        )

    def _parse_action(
        self, integration_name: str, action_name: str, raw_action: object
    ) -> ParsedNangoAction | None:
        if not self._valid_script(integration_name, "actions", action_name, raw_action):
            return None
        action_mapping = cast(RawMap, raw_action)

        output_models = self._models_for_output(
            action_mapping.get("output"), action_name, "action", integration_name
        )
        input_model = self._model_for_input(
            action_mapping.get("input"), action_name, "action", integration_name
        )
        endpoint = self._parse_endpoint(
            action_mapping.get("endpoint"), "POST", integration_name, "actions", action_name
        )
        used_models = self._used_model_names(
            (*output_models, *(tuple([input_model]) if input_model else ()))
        )

        return ParsedNangoAction(
            name=action_name,
            description=str(action_mapping.get("description") or "").strip(),
            version=str(action_mapping.get("version") or ""),
            scopes=_scopes(action_mapping.get("scopes")),
            input=input_model.name if input_model else None,
            output=tuple(model.name for model in output_models) or None,
            endpoint=endpoint,
            usedModels=used_models,
        )

    def _valid_script(
        self, integration_name: str, script_type: str, script_name: str, raw_script: object
    ) -> bool:
        if not script_name.strip():
            self.errors.append(
                ParserIssue(
                    code="missing_script_name",
                    message="Script names must be non-empty strings",
                    path=(integration_name, script_type),
                )
            )
            return False
        if not isinstance(raw_script, Mapping):
            self.errors.append(
                ParserIssue(
                    code="invalid_script_shape",
                    message="Script configuration must be a mapping",
                    path=(integration_name, script_type, script_name),
                )
            )
            return False
        return True

    def _models_for_output(
        self, raw_output: object, script_name: str, script_type: str, integration_name: str
    ) -> tuple[NangoModel, ...]:
        if raw_output is None:
            return ()
        raw_outputs = raw_output if isinstance(raw_output, list) else [raw_output]
        return tuple(
            self._model_for_io(raw, script_name, script_type, integration_name, "output")
            for raw in raw_outputs
        )

    def _model_for_input(
        self, raw_input: object, script_name: str, script_type: str, integration_name: str
    ) -> NangoModel | None:
        if raw_input is None:
            return None
        return self._model_for_io(raw_input, script_name, script_type, integration_name, "input")

    def _model_for_io(
        self, raw_type: object, script_name: str, script_type: str, integration_name: str, io: str
    ) -> NangoModel:
        type_name = str(raw_type)
        existing = self.models_parser.get(type_name)
        if existing:
            return existing
        safe_integration_name = _safe_identifier(integration_name)
        safe_script_name = _safe_identifier(script_name)
        anon_name = f"Anonymous_{safe_integration_name}_{script_type}_{safe_script_name}_{io}"
        return self.models_parser.parse_anonymous_model(anon_name, io, raw_type)

    def _parse_sync_endpoints(
        self, raw_endpoint: object, outputs_count: int, integration_name: str, sync_name: str
    ) -> tuple[NangoEndpoint, ...]:
        if raw_endpoint is None:
            return ()
        raw_endpoints = raw_endpoint if isinstance(raw_endpoint, list) else [raw_endpoint]
        if len(raw_endpoints) != outputs_count:
            self.errors.append(
                ParserIssue(
                    code="endpoints_mismatch",
                    message="The number of endpoints does not match "
                    f'the number of models returned by "{sync_name}"',
                    path=(integration_name, "syncs", sync_name),
                )
            )
            return ()
        return tuple(
            endpoint
            for raw in raw_endpoints
            if (endpoint := self._parse_endpoint(raw, "GET", integration_name, "syncs", sync_name))
            is not None
        )

    def _parse_endpoint(
        self,
        raw_endpoint: object,
        default_method: str,
        integration_name: str,
        script_type: str,
        script_name: str,
    ) -> NangoEndpoint | None:
        if raw_endpoint is None:
            return None
        if isinstance(raw_endpoint, str):
            parts = raw_endpoint.split()
            if len(parts) > 1:
                return NangoEndpoint(method=parts[0], path=parts[1])
            return NangoEndpoint(method=default_method, path=parts[0])
        if isinstance(raw_endpoint, Mapping):
            path = raw_endpoint.get("path")
            if isinstance(path, str) and path:
                return NangoEndpoint(
                    method=str(raw_endpoint.get("method") or default_method),
                    path=path,
                    group=str(raw_endpoint["group"])
                    if raw_endpoint.get("group") is not None
                    else None,
                )
        self.errors.append(
            ParserIssue(
                code="invalid_endpoint",
                message="Endpoint must be a path string or mapping with a path",
                path=(integration_name, script_type, script_name, "endpoint"),
            )
        )
        return None

    def _post_parse_validate(self, parsed: ParsedNangoYaml) -> None:
        for integration in parsed.integrations:
            endpoints: set[str] = set()
            used_sync_outputs: set[str] = set()
            for sync in integration.syncs:
                for model_name in sync.output:
                    if model_name in used_sync_outputs:
                        self.errors.append(
                            ParserIssue(
                                code="duplicate_model",
                                message=f'Model "{model_name}" is used multiple times',
                                path=(
                                    integration.provider_config_key,
                                    "syncs",
                                    sync.name,
                                    "[output]",
                                ),
                            )
                        )
                    used_sync_outputs.add(model_name)
                    model = self.models_parser.get(model_name)
                    if model and not any(field.name == "id" for field in model.fields):
                        self.errors.append(
                            ParserIssue(
                                code="model_missing_id",
                                message=(
                                    f'Model "{model_name}" does not have an id field required '
                                    "to uniquely identify data records"
                                ),
                                path=(
                                    integration.provider_config_key,
                                    "syncs",
                                    sync.name,
                                    "[output]",
                                ),
                            )
                        )
                    self._warn_literal_io(model_name, "syncs", sync.name, "[output]", integration)
                if sync.input:
                    self._warn_literal_io(sync.input, "syncs", sync.name, "[input]", integration)
                for endpoint in sync.endpoints:
                    self._validate_endpoint(
                        endpoint, endpoints, integration.provider_config_key, "syncs", sync.name
                    )

            for action in integration.actions:
                action_outputs: set[str] = set()
                for model_name in action.output or ():
                    if model_name in action_outputs:
                        self.errors.append(
                            ParserIssue(
                                code="duplicate_model",
                                message=f'Model "{model_name}" is used multiple times',
                                path=(
                                    integration.provider_config_key,
                                    "actions",
                                    action.name,
                                    "[output]",
                                ),
                            )
                        )
                    action_outputs.add(model_name)
                    self._warn_literal_io(
                        model_name, "actions", action.name, "[output]", integration
                    )
                if action.input:
                    self._warn_literal_io(
                        action.input, "actions", action.name, "[input]", integration
                    )
                if action.endpoint:
                    self._validate_endpoint(
                        action.endpoint,
                        endpoints,
                        integration.provider_config_key,
                        "actions",
                        action.name,
                    )

    def _validate_endpoint(
        self,
        endpoint: NangoEndpoint,
        endpoints: set[str],
        integration_name: str,
        script_type: str,
        script_name: str,
    ) -> None:
        key = f"{endpoint.method} {endpoint.path}"
        if key in endpoints:
            self.errors.append(
                ParserIssue(
                    code="duplicate_endpoint",
                    message=f'Endpoint "{key}" is used multiple times',
                    path=(integration_name, script_type, script_name, "[endpoint]"),
                )
            )
        endpoints.add(key)
        match = ENDPOINT_MODEL_PATTERN.search(endpoint.path)
        if not match:
            return
        model_name = match.group(1).split(":", 1)[0]
        if not self.models_parser.get(model_name):
            self.errors.append(
                ParserIssue(
                    code="model_not_found",
                    message=f'Model "{model_name}" does not exists',
                    path=(integration_name, script_type, script_name, "[endpoint]"),
                )
            )

    def _warn_literal_io(
        self,
        model_name: str,
        script_type: str,
        script_name: str,
        io_path: str,
        integration: ParsedNangoIntegration,
    ) -> None:
        model = self.models_parser.get(model_name)
        if not model or not model.is_anon or not model.fields or model.fields[0].union:
            return
        self.warnings.append(
            ParserIssue(
                code="model_is_literal",
                message=f'A literal type "{model.fields[0].value}" was parsed',
                path=(integration.provider_config_key, script_type, script_name, io_path),
            )
        )

    def _used_model_names(self, models: tuple[NangoModel, ...]) -> tuple[str, ...]:
        names: list[str] = []
        seen: set[str] = set()
        for model in models:
            for name in (model.name, *tuple(self._recursive_model_names(model.name))):
                if name not in seen:
                    seen.add(name)
                    names.append(name)
        return tuple(names)

    def _recursive_model_names(self, model_name: str) -> tuple[str, ...]:
        model = self.models_parser.get(model_name)
        if not model:
            return ()
        names: list[str] = []
        self._collect_field_model_names(model.fields, names, {model_name})
        return tuple(names)

    def _collect_field_model_names(
        self, fields: tuple[NangoModelField, ...], names: list[str], seen: set[str]
    ) -> None:
        for field in fields:
            if field.model and isinstance(field.value, str) and field.value not in seen:
                seen.add(field.value)
                names.append(field.value)
                sub_model = self.models_parser.get(field.value)
                if sub_model:
                    self._collect_field_model_names(sub_model.fields, names, seen)
            if isinstance(field.value, list):
                self._collect_field_model_names(tuple(field.value), names, seen)


def _string_key_mapping(raw: Mapping[object, object]) -> dict[str, object]:
    return {str(key): value for key, value in raw.items()}


def _optional_mapping(
    value: object, integration_name: str, key: str, errors: list[ParserIssue]
) -> dict[str, object]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return _string_key_mapping(value)
    errors.append(
        ParserIssue(
            code="invalid_integration_shape",
            message=f"{key} must be a mapping when present",
            path=(integration_name, key),
        )
    )
    return {}


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, bytes):
        return tuple(str(item) for item in value)
    return (str(value),)


def _scopes(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(scope.strip() for scope in value.split(",") if scope.strip())
    if isinstance(value, Sequence) and not isinstance(value, bytes):
        return tuple(str(scope) for scope in value)
    return (str(value),)


def _safe_identifier(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "", value)
