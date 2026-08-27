import base64
import json

import grpc
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from common.grpc import MonoscopeServerInterceptor

CAPTURE = {
    "service_name": "payment",
    "capture_request_body": True,
    "capture_response_body": True,
}
METHOD = "/oteldemo.PaymentService/Charge"


# The global tracer provider can only be set once per process, so it is installed at import
# and each test clears the exporter instead of installing a fresh one. Without this, only the
# first test's exporter is ever wired up and the rest silently see zero spans.
_EXPORTER = InMemorySpanExporter()
_PROVIDER = TracerProvider()
_PROVIDER.add_span_processor(SimpleSpanProcessor(_EXPORTER))
trace.set_tracer_provider(_PROVIDER)


@pytest.fixture
def exporter():
    _EXPORTER.clear()
    return _EXPORTER


class _Details:
    method = METHOD
    invocation_metadata = ()


class _Context:
    def code(self):
        return None


def _run(config, behavior, request, exporter):
    """Push one RPC through the interceptor and return (attributes, response, raised)."""
    handler = grpc.unary_unary_rpc_method_handler(behavior)
    wrapped = MonoscopeServerInterceptor(config).intercept_service(
        lambda _details: handler, _Details()
    )
    raised = None
    response = None
    try:
        response = wrapped.unary_unary(request, _Context())
    except Exception as exc:  # noqa: BLE001
        raised = exc

    spans = exporter.get_finished_spans()
    assert len(spans) == 1, f"expected one span, got {len(spans)}"
    assert spans[0].name == "monoscope.http", (
        "the span must be named monoscope.http or the server will not lift its bodies"
    )
    return dict(spans[0].attributes), response, raised


def _decode(attrs, key):
    raw = base64.b64decode(attrs[key])
    return json.loads(raw) if raw else {}


def test_captures_bodies_and_rpc_attributes(exporter):
    attrs, response, raised = _run(
        CAPTURE, lambda req, ctx: {"transactionId": "txn-1"}, {"amount": 42}, exporter
    )

    assert raised is None
    assert response == {"transactionId": "txn-1"}, "the response must reach the caller unchanged"
    assert _decode(attrs, "http.request.body") == {"amount": 42}
    assert _decode(attrs, "http.response.body") == {"transactionId": "txn-1"}
    assert attrs["rpc.system"] == "grpc"
    assert attrs["rpc.method"] == METHOD
    assert attrs["http.route"] == METHOD
    assert attrs["apitoolkit.sdk_type"] == "PythonGrpc"


def test_redacts_sensitive_fields(exporter):
    config = dict(CAPTURE, redact_request_body=["$.creditCard.creditCardNumber"])
    request = {
        "amount": 42,
        "creditCard": {"creditCardNumber": "4432-8015-6152-0454"},
    }
    attrs, _, _ = _run(config, lambda req, ctx: {}, request, exporter)

    body = _decode(attrs, "http.request.body")
    assert body["creditCard"]["creditCardNumber"] == "[CLIENT_REDACTED]"
    assert body["amount"] == 42, "redaction must not remove non-sensitive fields"


def test_error_propagates_untouched_and_is_recorded(exporter):
    failure = ValueError("card declined")

    def behavior(req, ctx):
        raise failure

    attrs, response, raised = _run(CAPTURE, behavior, {}, exporter)

    assert raised is failure, "the handler's own exception must reach the caller"
    assert response is None
    assert attrs["http.response.status_code"] == 500
    assert attrs["rpc.grpc.status_code"] == grpc.StatusCode.UNKNOWN.value[0]


def test_capture_off_records_metadata_but_no_bodies(exporter):
    attrs, _, _ = _run(
        {"service_name": "payment"},
        lambda req, ctx: {"secret": "s"},
        {"card": "4432-8015-6152-0454"},
        exporter,
    )

    assert base64.b64decode(attrs["http.request.body"]) == b""
    assert base64.b64decode(attrs["http.response.body"]) == b""
    assert attrs["rpc.system"] == "grpc", "the RPC is still traced, just without payloads"


def test_streaming_handlers_are_left_alone(exporter):
    """A stream has no single message to capture, so wrapping it would record nothing."""
    handler = grpc.unary_stream_rpc_method_handler(lambda req, ctx: iter([1, 2]))
    returned = MonoscopeServerInterceptor(CAPTURE).intercept_service(
        lambda _d: handler, _Details()
    )
    assert returned is handler, "streaming handlers must be returned untouched"
