"""Unit tests for the venue-bookings app, with DaprClient mocked out.

These don't need a running Dapr sidecar or Postgres: they only assert that each
endpoint calls the binding with the right operation and SQL, and parses the
response the way the binding actually shapes it.
"""

import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


@patch("app.DaprClient")
def test_create_booking_uses_exec_operation(mock_dapr_client):
    mock_instance = mock_dapr_client.return_value.__enter__.return_value
    mock_response = MagicMock()
    mock_response.binding_metadata = {"rows-affected": "1"}
    mock_instance.invoke_binding.return_value = mock_response

    response = client.post("/bookings", json={"venue": "Grand Ballroom", "event_date": "2026-03-15"})

    assert response.status_code == 200
    assert response.json() == {"status": "saved", "rows_affected": "1"}

    _, kwargs = mock_instance.invoke_binding.call_args
    assert kwargs["binding_name"] == "postgres-binding"
    assert kwargs["operation"] == "exec"
    assert "INSERT INTO bookings" in kwargs["binding_metadata"]["sql"]
    assert json.loads(kwargs["binding_metadata"]["params"]) == ["Grand Ballroom", "2026-03-15"]


@patch("app.DaprClient")
def test_list_bookings_uses_query_operation(mock_dapr_client):
    mock_instance = mock_dapr_client.return_value.__enter__.return_value
    mock_response = MagicMock()
    mock_response.data = json.dumps([[1, "Grand Ballroom", "2026-03-15"]]).encode()
    mock_instance.invoke_binding.return_value = mock_response

    response = client.get("/bookings")

    assert response.status_code == 200
    assert response.json() == {
        "bookings": [{"id": 1, "venue": "Grand Ballroom", "event_date": "2026-03-15"}]
    }

    _, kwargs = mock_instance.invoke_binding.call_args
    assert kwargs["binding_name"] == "postgres-binding"
    assert kwargs["operation"] == "query"
    assert "SELECT" in kwargs["binding_metadata"]["sql"]


@patch("app.DaprClient")
def test_list_bookings_handles_empty_result(mock_dapr_client):
    mock_instance = mock_dapr_client.return_value.__enter__.return_value
    mock_response = MagicMock()
    mock_response.data = b""
    mock_instance.invoke_binding.return_value = mock_response

    response = client.get("/bookings")

    assert response.status_code == 200
    assert response.json() == {"bookings": []}
