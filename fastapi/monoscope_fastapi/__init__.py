import uuid
from fastapi import Request, Response
from typing import Any
from common import (
    observe_request,
    report_error,
    set_attributes,
    set_user,
    set_tenant,
    set_session,
    apply_session_from_baggage,
    add_attributes_to_current_span,
    _current_span_var,
)
from starlette.types import Message
from starlette.concurrency import iterate_in_threadpool
from opentelemetry.trace import get_tracer, SpanKind

async def set_body(request: Request, body: bytes):
    async def receive() -> Message:
        return {"type": "http.request", "body": body}
    request._receive = receive


async def get_body(request: Request) -> bytes:
    body = await request.body()
    await set_body(request, body)
    return body

observe_request = observe_request
report_error = report_error
set_user = set_user
set_tenant = set_tenant
set_session = set_session
add_attributes_to_current_span = add_attributes_to_current_span

class Monoscope:
    def __init__(self, debug=False,
                 redact_headers=[],
                 redact_request_body=[],
                 redact_response_body=[],
                 capture_request_body=False,
                 service_name="",
                 capture_response_body=False,
                 service_version=None, tags=[]):
        self.redact_request_body = []
        self.redact_response_body = []
        self.service_version = service_version
        self.tags = tags
        self.service_name = service_name
        self.debug = False
        if debug:
            print("Monoscope initialize")
        self.debug = debug
        self.redact_headers = redact_headers
        self.redact_request_body = redact_request_body
        self.redact_response_body = redact_response_body
        self.config = {
            "redact_headers": self.redact_headers,
            "redact_request_body": self.redact_request_body,
            "redact_response_body": self.redact_response_body,
            "debug": self.debug,
            "service_version": self.service_version,
            "tags": self.tags,
            "capture_request_body": capture_request_body,
            "capture_response_body": capture_response_body,
            "service_name": service_name
        }

    async def middleware(self, request: Request, call_next):
        tracer = get_tracer(self.service_name or "monoscope-tracer")
        span = tracer.start_span("monoscope.http", kind=SpanKind.SERVER)
        ctx_token = _current_span_var.set(span)
        apply_session_from_baggage(span)
        if self.debug:
            print("Monoscope middleware")
        request.state.apitoolkit_message_id = str(uuid.uuid4())
        request.state.apitoolkit_errors = []
        request.state.apitoolkit_client = self
        request_body = b""
        err = None
        response = None
        try:
            if self.config["capture_request_body"]:
                request_body = await request.body()
            response = await call_next(request)
            return response
        except Exception as e:
            if self.debug:
                print(e)
            err = e
            raise
        finally:
            try:
                status_code, res_headers, response_body = 500, {}, []
                if err is not None:
                    report_error(request, err)
                    span.record_exception(err)
                # None also when cancelled, which is a BaseException and so leaves err unset.
                if response is not None:
                    status_code, res_headers = response.status_code, response.headers
                    if self.config["capture_response_body"]:
                        response_body = [chunk async for chunk in response.body_iterator]
                        response.body_iterator = iterate_in_threadpool(iter(response_body))
                path = request.url.path
                route_pattern = getattr(request.scope.get('route'), 'path', path)
                full_path = f"{path}?{request.url.query}" if request.url.query else path
                set_attributes(
                    span,
                    request.url.netloc,
                    status_code,
                    dict(request.query_params),
                    dict(request.path_params),
                    dict(request.headers),
                    dict(res_headers),
                    request.method,
                    full_path,
                    request.state.apitoolkit_message_id,
                    route_pattern,
                    request_body,
                    b''.join(response_body),
                    request.state.apitoolkit_errors,
                    self.config,
                    "PythonFastApi"
                )
            except Exception as e:
                # Only reachable before set_attributes, which always ends the span itself.
                span.record_exception(e)
                span.end()
                raise
            finally:
                _current_span_var.reset(ctx_token)
