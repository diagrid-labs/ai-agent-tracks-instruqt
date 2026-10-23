"""Check the HTTP contract and binding requests without a sidecar or database."""

import json
from unittest.mock import MagicMock, patch

import pytest
from dapr.clients.exceptions import DaprInternalError
from fastapi.testclient import TestClient
from grpc import RpcError

from app import app


@pytest.fixture
def client_and_binding():
    with patch("app.DaprClient") as factory:
        binding = factory.return_value.__enter__.return_value
        with TestClient(app) as client:
            yield client, binding, factory


def test_create_booking_uses_exec_operation(client_and_binding):
    client, binding, _ = client_and_binding
    binding.invoke_binding.return_value = MagicMock(binding_metadata={"rows-affected": "1"})
    response = client.post(
        "/bookings", json={"venue": "Grand Ballroom", "event_date": "2026-03-15"}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "saved", "rows_affected": "1"}
    kwargs = binding.invoke_binding.call_args.kwargs
    assert kwargs["binding_name"] == "postgres-binding"
    assert kwargs["operation"] == "exec"
    assert (
        kwargs["binding_metadata"]["sql"]
        == "INSERT INTO bookings (venue, event_date) VALUES ($1, $2)"
    )
    assert json.loads(kwargs["binding_metadata"]["params"]) == ["Grand Ballroom", "2026-03-15"]


def test_list_bookings_uses_query_operation(client_and_binding):
    client, binding, _ = client_and_binding
    binding.invoke_binding.return_value = MagicMock(data=b'[[1,"Grand Ballroom","2026-03-15"]]')
    response = client.get("/bookings")
    assert response.status_code == 200
    assert response.json() == {
        "bookings": [{"id": 1, "venue": "Grand Ballroom", "event_date": "2026-03-15"}]
    }
    kwargs = binding.invoke_binding.call_args.kwargs
    assert kwargs["binding_name"] == "postgres-binding"
    assert kwargs["operation"] == "query"
    assert (
        kwargs["binding_metadata"]["sql"]
        == "SELECT id, venue, event_date::text FROM bookings ORDER BY id"
    )


def test_list_bookings_handles_empty_array(client_and_binding):
    client, binding, _ = client_and_binding
    binding.invoke_binding.return_value = MagicMock(data=b"[]")
    response = client.get("/bookings")
    assert response.status_code == 200
    assert response.json() == {"bookings": []}


def test_requests_reuse_one_client(client_and_binding):
    client, binding, factory = client_and_binding
    binding.invoke_binding.return_value = MagicMock(data=b"[]")
    client.get("/bookings")
    client.get("/bookings")
    factory.assert_called_once_with()
    assert binding.invoke_binding.call_count == 2


def test_openapi_describes_responses(client_and_binding):
    client, _, _ = client_and_binding
    schema = client.get("/openapi.json").json()
    for method, name in (("post", "SaveBookingResponse"), ("get", "BookingsResponse")):
        response = schema["paths"]["/bookings"][method]["responses"]["200"]
        assert response["content"]["application/json"]["schema"]["$ref"].endswith(name)


@pytest.mark.parametrize("error", [DaprInternalError("binding failed"), RpcError("binding failed")])
def test_binding_failure_has_an_actionable_response(client_and_binding, error):
    client, binding, _ = client_and_binding
    binding.invoke_binding.side_effect = error
    response = client.post(
        "/bookings", json={"venue": "Grand Ballroom", "event_date": "2026-03-15"}
    )
    assert response.status_code == 503
    assert "Postgres binding request failed" in response.json()["detail"]
