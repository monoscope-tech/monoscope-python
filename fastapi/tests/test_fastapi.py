import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from monoscope_fastapi import Monoscope

EXPORTER = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(EXPORTER))
trace.set_tracer_provider(_provider)


def _call(**config):
    EXPORTER.clear()
    app = FastAPI()
    app.middleware("http")(Monoscope(**config).middleware)

    @app.post("/users/{name}")
    def user(name: str, body: dict):
        return {"secret": name, "echo": body}

    response = TestClient(app).post("/users/ada", json={"password": "p"})
    assert response.json() == {"secret": "ada", "echo": {"password": "p"}}, "the app must still see the body"
    [span] = [s for s in EXPORTER.get_finished_spans() if s.name == "monoscope.http"]
    return span.attributes


@pytest.mark.parametrize("flag,kind,value", [
    ("capture_request_body", "request", b"password"),
    ("capture_response_body", "response", b"ada"),
])
def test_bodies_are_captured_only_when_enabled(flag, kind, value):
    assert base64.b64decode(_call()[f"http.{kind}.body"]) == b""
    assert value in base64.b64decode(_call(**{flag: True})[f"http.{kind}.body"])
