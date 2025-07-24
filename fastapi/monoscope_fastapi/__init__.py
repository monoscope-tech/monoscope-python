import uuid
from fastapi import Request, Response
from typing import Any
from common import observe_request, report_error, set_attributes
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

class Monoscope:
    def __init__(self, debug=False,
                 redact_headers=['authorization', 'cookie'],
                 redact_request_body=[],
                 redact_response_body=[],
                 capture_request_body=False,
                 service_name="",
                 capture_response_body=False,
                 service_version=None, tags=[]):
        self.redact_headers = ['authorization', 'cookie']
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
        if self.debug:
            print("Monoscope middleware")
        request.state.apitoolkit_message_id = str(uuid.uuid4())
        request.state.apitoolkit_errors = []
        request.state.apitoolkit_client = self
        request_body = await request.body()
        request._body = request_body
        err = None
        response = None
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            if self.debug:
                print(e)
            err = e
            raise
        finally:
            if err is not None:
              report_error(request, err)
            response_body = ''
            res_headers = {}
            status_code = 200
            if response is not None:
              netloc = request.url.netloc
              host = netloc
              status_code = response.status_code
              res_headers = response.headers
              response_body = [chunk async for chunk in response.body_iterator]
              response.body_iterator = iterate_in_threadpool(iter(response_body))
              path = request.url.path
              route_pattern = getattr(request.scope.get('route'), 'path', path)
              query = request.url.query
              full_path = f"{path}"
              if query:
                  full_path += f"?{query}"
              message_id = request.state.apitoolkit_message_id
              errors = request.state.apitoolkit_errors
              set_attributes(
                  span,
                  host,
                  status_code,
                  dict(request.query_params),
                  dict(request.path_params),
                  dict(request.headers),
                  dict(res_headers),
                  request.method,
                  full_path,
                  message_id,
                  route_pattern,
                  request_body,
                  b''.join(response_body),
                  errors,
                  self.config,
                  "PythonFastApi"
              )
            else:
                if self.debug:
                    print("Monoscope metadata is not set restart server to fix")
