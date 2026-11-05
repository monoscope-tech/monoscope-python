import base64

import pytest
from flask import Flask
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from monoscope_flask import Monoscope

EXPORTER = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(EXPORTER))
trace.set_tracer_provider(_provider)


def _call(**config):
    EXPORTER.clear()
    app, monoscope = Flask(__name__), Monoscope(**config)
    app.before_request(monoscope.beforeRequest)
    app.after_request(lambda response: (monoscope.afterRequest(response), response)[1])
    app.add_url_rule("/users/<name>", "u", lambda name: {"secret": name}, methods=["POST"])
    app.test_client().post("/users/ada?x=1", json={"password": "p"})
    [span] = [s for s in EXPORTER.get_finished_spans() if s.name == "monoscope.http"]
    return span.attributes


def _body(attrs, kind):
    return base64.b64decode(attrs[f"http.{kind}.body"])


@pytest.mark.parametrize("flag,kind,value", [("capture_request_body", "request", b"password"), ("capture_response_body", "response", b"ada")])
def test_bodies_are_captured_only_when_enabled(flag, kind, value):
    assert _body(_call(), kind) == b""
    assert value in _body(_call(**{flag: True}), kind)



def test_route_is_the_pattern_and_target_is_the_full_path():
    attrs = _call()
    assert attrs["http.route"] == "/users/<name>"
    assert attrs["http.target"] == "/users/ada?x=1"


def test_after_request_can_be_registered_directly():
    EXPORTER.clear()
    app, monoscope = Flask(__name__), Monoscope()
    app.before_request(monoscope.beforeRequest)
    app.after_request(monoscope.afterRequest)
    app.add_url_rule("/", "i", lambda: "ok")
    assert app.test_client().get("/").data == b"ok"
    assert len([s for s in EXPORTER.get_finished_spans() if s.name == "monoscope.http"]) == 1
