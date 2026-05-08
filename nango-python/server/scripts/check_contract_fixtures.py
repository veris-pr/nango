from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nango.contracts import (
    ConnectSessionCreateRequest,
    ConnectSessionCreateResponse,
    HealthResponse,
    UserCreatedEvent,
    WebhookSignatureFixture,
)
from nango.contracts.base import ContractModel
from nango.metering import MeteringTeamUpdatedEvent, MeteringUsageEvent
from nango.utils.json import canonical_json

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "contract-fixtures"

FIXTURES: dict[str, type[ContractModel]] = {
    "health.response.json": HealthResponse,
    "connect.session.create.request.json": ConnectSessionCreateRequest,
    "connect.session.create.response.json": ConnectSessionCreateResponse,
    "pubsub.team.updated.event.json": MeteringTeamUpdatedEvent,
    "pubsub.user.created.event.json": UserCreatedEvent,
    "pubsub.usage.records.event.json": MeteringUsageEvent,
    "webhook.signature.fixture.json": WebhookSignatureFixture,
}

def fixture_payload(path: Path) -> Any:
    return json.loads(path.read_text())


def normalized_payload(model_type: type[ContractModel], payload: Any) -> Any:
    model = model_type.model_validate(payload)
    return json.loads(model.model_dump_json(by_alias=True, exclude_none=True))


def check_fixtures() -> list[str]:
    failures: list[str] = []

    for filename, model_type in FIXTURES.items():
        path = FIXTURE_DIR / filename
        payload = fixture_payload(path)
        normalized = normalized_payload(model_type, payload)
        if canonical_json(normalized) != canonical_json(payload):
            failures.append(filename)

    return failures


def main() -> int:
    failures = check_fixtures()
    if failures:
        print("Contract fixture drift detected:")
        for filename in failures:
            print(f"- {filename}")
        return 1

    print(f"Checked {len(FIXTURES)} contract fixtures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
