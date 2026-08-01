"""Tests for the webhook use cases.

These used to have nowhere to live: the router was the use case, so parsing
could only be exercised through an HTTP request with a valid HMAC signature.
"""

import json

import pytest

from helprs.core.exceptions import DomainValidationError
from helprs.modules.webhook.service import parse_delivery, record_delivery


def _body(payload: dict) -> bytes:
    return json.dumps(payload).encode()


class TestParseDelivery:
    def test_extracts_the_fields_the_dispatcher_needs(self):
        delivery = parse_delivery(
            delivery_id="  d-1  ",
            event_type="pull_request",
            body=_body({"action": "opened", "installation": {"id": 4242}}),
        )

        assert delivery.delivery_id == "d-1"
        assert delivery.event_type == "pull_request"
        assert delivery.action == "opened"
        assert delivery.github_installation_id == 4242
        assert delivery.payload["action"] == "opened"

    def test_a_payload_without_an_installation_is_still_valid(self):
        """Not every event carries one, and the dispatcher decides what to do."""
        delivery = parse_delivery(delivery_id="d-2", event_type="ping", body=_body({}))

        assert delivery.github_installation_id is None
        assert delivery.action is None

    @pytest.mark.parametrize(
        ("installation", "why"),
        [
            ("not-an-object", "GitHub sending a scalar must not become an int id"),
            ({"id": "4242"}, "a string id must not be passed off as an int"),
        ],
    )
    def test_a_malformed_installation_yields_no_id(self, installation, why):
        delivery = parse_delivery(
            delivery_id="d-3",
            event_type="pull_request",
            body=_body({"installation": installation}),
        )

        assert delivery.github_installation_id is None, why

    def test_a_missing_delivery_id_is_a_400(self):
        with pytest.raises(DomainValidationError, match="X-GitHub-Delivery"):
            parse_delivery(delivery_id="   ", event_type="ping", body=_body({}))

    def test_invalid_json_is_a_400(self):
        with pytest.raises(DomainValidationError, match="Invalid JSON"):
            parse_delivery(delivery_id="d-4", event_type="ping", body=b"{not json")

    def test_a_non_object_payload_is_a_400(self):
        with pytest.raises(DomainValidationError, match="must be an object"):
            parse_delivery(delivery_id="d-5", event_type="ping", body=b"[1, 2, 3]")


class TestRecordDelivery:
    async def test_persists_the_event(self, db_session):
        delivery = parse_delivery(
            delivery_id="d-record",
            event_type="pull_request",
            body=_body({"action": "opened", "installation": {"id": 1}}),
        )

        event = await record_delivery(db_session, delivery)

        assert event is not None
        assert event.delivery_id == "d-record"
        assert event.status == "pending"

    async def test_a_redelivery_returns_none_rather_than_raising(self, db_session):
        """GitHub retries deliveries, so a duplicate is an expected outcome —
        the unique index on delivery_id is what makes the receiver idempotent."""
        delivery = parse_delivery(
            delivery_id="d-dup",
            event_type="pull_request",
            body=_body({"action": "opened", "installation": {"id": 1}}),
        )

        assert await record_delivery(db_session, delivery) is not None
        assert await record_delivery(db_session, delivery) is None
