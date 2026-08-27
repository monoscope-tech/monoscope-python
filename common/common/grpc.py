"""gRPC payload capture for Monoscope.

Every other integration in this SDK is an HTTP middleware, which leaves a gRPC service with no
request or response payloads at all. This closes that for unary RPCs.

`grpc` is an optional dependency: importing this module without it raises, but importing the
package as a whole does not, so an HTTP-only user is unaffected.
"""

import json
import uuid

import grpc
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from . import set_attributes

# Only unary-unary is covered. A streaming RPC has no single request or response message, so a
# wrapper would record nothing while appearing to work — better to leave those handlers
# untouched and say so than to ship a silent no-op.
_SDK_TYPE = "PythonGrpc"


def _to_json_string(message) -> str:
    """Render a gRPC message as a JSON *string*.

    A string, not a dict, on purpose: ``redact_fields`` does ``json.loads(body)``, so handing it
    an already-decoded object makes it throw and return the value **unredacted**. A gRPC message
    arrives decoded in every language, which is exactly the path that bug lives on.

    ``MessageToJson`` rather than a hand-rolled walk: it applies the field names declared in the
    ``.proto`` and renders 64-bit fields as strings, so a redaction path written against the
    schema matches. Best-effort — capture must never be the reason an RPC fails.
    """
    try:
        from google.protobuf.json_format import MessageToJson

        return MessageToJson(message, indent=None)
    except Exception:
        pass
    try:
        return json.dumps(message, default=str)
    except Exception:
        return ""


def _grpc_code(context, error) -> int:
    """The gRPC status the call actually ended with.

    Kept because the HTTP shape cannot express it: NOT_FOUND and PERMISSION_DENIED both flatten
    to 500, and that distinction is usually the whole question during an incident.
    """
    if error is not None:
        return grpc.StatusCode.UNKNOWN.value[0]
    try:
        code = context.code()
        return code.value[0] if code is not None else grpc.StatusCode.OK.value[0]
    except Exception:
        return grpc.StatusCode.OK.value[0]


class MonoscopeServerInterceptor(grpc.ServerInterceptor):
    """Capture request and response payloads for unary gRPC methods.

    ::

        server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=10),
            interceptors=[MonoscopeServerInterceptor({
                "service_name": "payment",
                "capture_request_body": True,
                "redact_request_body": ["$.creditCard.creditCardNumber"],
            })],
        )

    Body capture is opt-in, matching every other integration in this SDK and the Go and JS
    ones: bodies are the expensive part of a span and the part most likely to hold something
    the operator did not intend to store, so switching them on should be a decision. With
    capture off the RPC is still traced — route, rpc status, timing — just without payloads.
    """

    def __init__(self, config: dict):
        self.config = config or {}

    def intercept_service(self, continuation, handler_call_details):
        handler = continuation(handler_call_details)
        if handler is None or not handler.unary_unary or handler.request_streaming or handler.response_streaming:
            return handler

        method = handler_call_details.method
        config = self.config
        behavior = handler.unary_unary

        def wrapper(request, context):
            tracer = trace.get_tracer(config.get("service_name", "monoscope"))
            span = tracer.start_span("monoscope.http", kind=SpanKind.SERVER)
            error = None
            response = None
            try:
                with trace.use_span(span, end_on_exit=False):
                    response = behavior(request, context)
            except Exception as exc:  # noqa: BLE001 - re-raised below, untouched
                error = exc
            finally:
                req_body = (
                    _to_json_string(request) if config.get("capture_request_body") else ""
                )
                resp_body = ""
                if config.get("capture_response_body") and error is None:
                    resp_body = _to_json_string(response)

                # Recorded BEFORE set_attributes, because set_attributes ends the span in its
                # own `finally` — anything set after that is silently dropped onto a finished
                # span. These sit alongside the HTTP-shaped attributes rather than instead of
                # them: the server lifts bodies based on the HTTP shape, but the gRPC status
                # carries more than ok-or-not, so the real code is kept for the UI to use.
                try:
                    span.set_attributes({
                        "rpc.system": "grpc",
                        "rpc.method": method,
                        "rpc.grpc.status_code": _grpc_code(context, error),
                    })
                    if error is not None:
                        span.set_status(Status(StatusCode.ERROR, str(error)))
                except Exception:
                    pass

                # This ends the span.
                set_attributes(
                    span,
                    config.get("service_name", ""),
                    500 if error is not None else 200,
                    {},
                    {},
                    {},
                    {},
                    "POST",  # gRPC rides on HTTP/2 POST
                    method,
                    str(uuid.uuid4()),
                    method,
                    req_body,
                    resp_body,
                    [],
                    config,
                    _SDK_TYPE,
                )

            if error is not None:
                # The handler's own exception, propagated untouched — capture is never the
                # reason an RPC fails or succeeds differently.
                raise error
            return response

        return grpc.unary_unary_rpc_method_handler(
            wrapper,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )
