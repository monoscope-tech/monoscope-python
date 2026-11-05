import base64

import django
import pytest
from django.conf import settings
from django.http import JsonResponse
from django.urls import path
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

EXPORTER = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(EXPORTER))
trace.set_tracer_provider(_provider)

urlpatterns = [path("users/<name>", lambda request, name: JsonResponse({"secret": name}))]
settings.configure(ROOT_URLCONF=__name__, ALLOWED_HOSTS=["*"], MIDDLEWARE=["monoscope_django.MonoscopeMiddleware"])
django.setup()

from django.test import Client, override_settings  # noqa: E402


def _call(**flags):
    EXPORTER.clear()
    with override_settings(**flags):
        Client().post("/users/ada", {"password": "p"}, content_type="application/json")
    [span] = [s for s in EXPORTER.get_finished_spans() if s.name == "monoscope.http"]
    return span.attributes


@pytest.mark.parametrize("flag,kind,value", [
    ("MONOSCOPE_CAPTURE_REQUEST_BODY", "request", b"password"),
    ("MONOSCOPE_CAPTURE_RESPONSE_BODY", "response", b"ada"),
])
def test_bodies_are_captured_only_when_enabled(flag, kind, value):
    assert base64.b64decode(_call()[f"http.{kind}.body"]) == b""
    assert value in base64.b64decode(_call(**{flag: True})[f"http.{kind}.body"])
