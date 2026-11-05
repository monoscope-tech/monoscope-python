import base64

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pyramid.config import Configurator
from pyramid.request import Request

EXPORTER = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(EXPORTER))
trace.set_tracer_provider(_provider)


def _call(**settings):
    EXPORTER.clear()
    with Configurator(settings=settings) as config:
        config.add_tween("monoscope_pyramid.Monoscope")
        config.add_route("u", "/users/{name}")
        config.add_view(lambda request: {"secret": request.matchdict["name"]}, route_name="u", renderer="json")
        app = config.make_wsgi_app()
    request = Request.blank("/users/ada", method="POST", body=b'{"password": "p"}', content_type="application/json")
    request.get_response(app)
    [span] = [s for s in EXPORTER.get_finished_spans() if s.name == "monoscope.http"]
    return span.attributes


@pytest.mark.parametrize("flag,kind,value", [
    ("MONOSCOPE_CAPTURE_REQUEST_BODY", "request", b"password"),
    ("MONOSCOPE_CAPTURE_RESPONSE_BODY", "response", b"ada"),
])
def test_bodies_are_captured_only_when_enabled(flag, kind, value):
    assert base64.b64decode(_call()[f"http.{kind}.body"]) == b""
    assert value in base64.b64decode(_call(**{flag: True})[f"http.{kind}.body"])


def test_ini_string_flags_are_parsed_as_booleans():
    assert base64.b64decode(_call(MONOSCOPE_CAPTURE_REQUEST_BODY="false")["http.request.body"]) == b""
    assert b"password" in base64.b64decode(_call(MONOSCOPE_CAPTURE_REQUEST_BODY="true")["http.request.body"])


def test_ini_comma_lists_are_trimmed():
    attrs = _call(MONOSCOPE_REDACT_REQUEST_BODY="$.other, $.password", MONOSCOPE_CAPTURE_REQUEST_BODY="true")
    assert b"[CLIENT_REDACTED]" in base64.b64decode(attrs["http.request.body"])
