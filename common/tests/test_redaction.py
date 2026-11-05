import base64
import json

import httpx
import pytest
from opentelemetry import trace

from common import observe_request, redact_fields, set_attributes
# The global tracer provider can only be installed once per process; reuse the one test_grpc sets up.
from test_grpc import exporter  # noqa: F401

R = "[CLIENT_REDACTED]"


def _attrs(exporter):
    spans = exporter.get_finished_spans()
    assert len(spans) == 1, f"expected one span, got {len(spans)}"
    return dict(spans[0].attributes)


def test_headers_are_redacted_by_name_case_insensitively(exporter):
    set_attributes(
        trace.get_tracer("t").start_span("s"), "h", 200, {}, {},
        {"Authorization": "Bearer abc", "Cookie": "sid=1", "Proxy-Authorization": "Basic x",
         "X-Api-Key": "k", "Accept": "*/*"},
        {"Set-Cookie": "sid=2", "Content-Type": "application/json"},
        "GET", "/", "m", "/", "", "", [],
        {"redact_headers": ["x-API-key"]}, "t",
    )
    attrs = _attrs(exporter)
    for name in ("Authorization", "Cookie", "Proxy-Authorization", "X-Api-Key"):
        assert attrs[f"http.request.header.{name}"] == R, name
    assert attrs["http.response.header.Set-Cookie"] == R
    assert attrs["http.request.header.Accept"] == "*/*"
    assert attrs["http.response.header.Content-Type"] == "application/json"


@pytest.mark.parametrize("body", ['{"password": "p", "a": 1}', b'{"password": "p", "a": 1}', {"password": "p", "a": 1}])
def test_redact_fields_handles_every_body_shape(body):
    assert json.loads(redact_fields(body, ["$.password"])) == {"password": R, "a": 1}


def test_redact_fields_does_not_mutate_a_parsed_body():
    body = {"password": "p"}
    redact_fields(body, ["$.password"])
    assert body == {"password": "p"}


def test_one_invalid_path_does_not_disable_the_others():
    assert json.loads(redact_fields('{"password": "p"}', ["$[bad", "$.password"])) == {"password": R}


class _Parent:
    apitoolkit_message_id = "m"


def _client(handler):
    client = observe_request(_Parent())
    client._transport = httpx.MockTransport(handler)
    return client


def test_outgoing_error_response_keeps_request_details_and_redacts(exporter):
    _client(lambda req: httpx.Response(500, json={"e": 1})).post(
        "http://api.example.com/v1/pay?x=1", json={"card": "4111"}, headers={"Authorization": "Bearer out"}
    )
    attrs = _attrs(exporter)
    assert attrs["http.request.header.authorization"] == R
    assert attrs["http.response.status_code"] == 500
    assert attrs["http.request.method"] == "POST"
    assert attrs["net.host.name"] == "api.example.com"
    assert attrs["http.route"] == "/v1/pay"
    assert json.loads(attrs["http.request.query_params"]) == {"x": "1"}
    assert json.loads(base64.b64decode(attrs["http.request.body"])) == {"card": "4111"}


def test_outgoing_network_error_is_recorded_and_reraised(exporter):
    def refuse(req):
        raise httpx.ConnectError("refused", request=req)

    with pytest.raises(httpx.ConnectError):
        _client(refuse).get("http://down.example.com/x", headers={"Authorization": "Bearer out"})
    attrs = _attrs(exporter)
    assert attrs["http.request.header.authorization"] == R
    assert attrs["http.request.method"] == "GET"
    assert attrs["net.host.name"] == "down.example.com"
    assert attrs["http.route"] == "/x"
    assert json.loads(attrs["apitoolkit.errors"])[0]["error_type"] == "ConnectError"


def test_outgoing_capture_failure_never_replaces_the_callers_error(exporter):
    def refuse(req):
        raise httpx.ConnectError("refused", request=req)

    client = observe_request(object())
    client._transport = httpx.MockTransport(refuse)
    with pytest.raises(httpx.ConnectError):
        client.get("http://down.example.com/x")
