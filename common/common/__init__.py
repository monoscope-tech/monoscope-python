from base64 import b64encode
import json
from contextvars import ContextVar
from datetime import datetime
from opentelemetry.trace import get_tracer, SpanKind
from opentelemetry.baggage import get_baggage
import traceback
from jsonpath_ng import parse
import pytz
import httpx

# Holds the active request span so set_user / set_tenant /
# add_attributes_to_current_span can attach attributes from anywhere inside
# a request handler. Mirrors AsyncLocalStorage in the JS SDK; works in both
# sync (Flask, Django, Pyramid) and async (FastAPI) handlers.
_current_span_var: ContextVar = ContextVar("monoscope_current_span", default=None)


def add_attributes_to_current_span(attributes: dict) -> None:
    span = _current_span_var.get()
    if span is None:
        return
    for key, value in attributes.items():
        if value is None:
            continue
        span.set_attribute(key, value)


def set_user(user: dict) -> None:
    """Attach the authenticated user to the current request span.

    Accepts a dict with optional `id`, `email`, and `name` keys; missing
    fields are skipped so partial info is fine.
    """
    add_attributes_to_current_span({
        "user.id": user.get("id"),
        "user.email": user.get("email"),
        "user.full_name": user.get("name"),
    })


def set_tenant(tenant: dict) -> None:
    """Attach the authenticated tenant/org to the current request span."""
    add_attributes_to_current_span({
        "tenant.id": tenant.get("id"),
        "tenant.name": tenant.get("name"),
    })


def set_session(session_id: str) -> None:
    """Attach a session id to the current request span as `session.id`."""
    add_attributes_to_current_span({"session.id": session_id})


def apply_session_from_baggage(span) -> None:
    """Tag the request span with `session.id` from W3C baggage if present.

    Called by each framework middleware after span creation. The browser SDK
    seeds `session.id` into baggage on outbound fetch/XHR; the OTel default
    propagator (tracecontext + baggage) extracts it on the incoming request.
    Safe no-op when baggage is absent.
    """
    try:
        session_id = get_baggage("session.id")
        if session_id:
            span.set_attribute("session.id", session_id)
    except Exception:
        pass


DEFAULT_REDACTED_HEADERS = ["authorization", "cookie", "set-cookie", "proxy-authorization"]


def set_attributes(
    span,
    host: str,
    status_code: int,
    query_params: dict,
    path_params: dict,
    req_headers: dict,
    resp_headers: dict,
    method: str,
    raw_url: str,
    msg_id: str,
    url_path: str,
    req_body: str,
    resp_body: str,
    errors: list,
    config: dict,
    sdk_type: str,
    parent_id: str = None,
):
    try:
        redacted = {h.strip().lower() for h in config.get("redact_headers", []) + DEFAULT_REDACTED_HEADERS}

        span.set_attributes({
            "net.host.name": host,
            "apitoolkit.msg_id": msg_id,
            "http.route": url_path,
            "http.target": raw_url,
            "http.request.method": method,
            "http.response.status_code": status_code,
            "http.request.query_params": json.dumps(query_params),
            "http.request.path_params": json.dumps(path_params),
            "apitoolkit.sdk_type": sdk_type,
            "apitoolkit.parent_id": parent_id or "",
            "http.request.body":  b64encode(redact_fields(req_body, config.get("redact_request_body", []))).decode(),
            "http.response.body": b64encode(redact_fields(resp_body, config.get("redact_response_body", []))).decode(),
            "apitoolkit.errors": json.dumps(errors),
            "apitoolkit.service_version": config.get("serviceVersion", ""),
            "apitoolkit.tags": json.dumps(config.get("tags", [])),
        })

        for kind, headers in (("request", req_headers), ("response", resp_headers)):
            for header, value in headers.items():
                span.set_attribute(f"http.{kind}.header.{header}",
                                   "[CLIENT_REDACTED]" if header.lower() in redacted else str(value))

    except Exception as error:
        span.record_exception(error)
    finally:
        span.end()


def observe_request(parent_request, url_wildcard=None,redact_headers=[], redact_request_body=[], redact_response_body=[]):
    def on_request(request):
        tracer = get_tracer("monoscope-tracer")
        # Kept on the request, not the closure, so concurrent calls on one client don't share a span.
        request.extensions["monoscope_span"] = tracer.start_span("monoscope.http", kind=SpanKind.CLIENT)

    def record(req, status_code, res_headers, res_body, errors):
        message_id = parent_request.apitoolkit_message_id if hasattr(
            parent_request, "apitoolkit_message_id") else parent_request.state.apitoolkit_message_id if hasattr(parent_request.state, "apitoolkit_message_id") else None
        if message_id is None:
            print(
                "No message_id found attached to request, make sure middleware is configured correctly")
        try:
            req_body = req.content.decode()
        except Exception:
            req_body = ""
        req_headers = dict((k, v if isinstance(v, list) else [v]) for k, v in req.headers.items())
        config = {"redact_headers": redact_headers, "redact_request_body": redact_request_body, "redact_response_body": redact_response_body}
        set_attributes(
            req.extensions["monoscope_span"], req.url.host, status_code,
            dict(req.url.params), {},
            req_headers, res_headers, req.method.upper(),
            req.url.path, message_id, url_wildcard or req.url.path, req_body, res_body, errors, config, sdk_type="PythonOutgoing")

    def on_response(response):
      try:
        response.read()
        res_headers = dict((k, v if isinstance(v, list) else [v]) for k, v in response.headers.items())
        record(response.request, response.status_code, res_headers, response.text, [])
      except Exception as e:
          pass

    client = httpx.Client(event_hooks={'request': [
        on_request], 'response': [on_response]})

    # httpx has no error hook, so a failed connection would otherwise leave the span open and unexported.
    send = client.send
    def send_and_record_failure(request, **kwargs):
        try:
            return send(request, **kwargs)
        except Exception as error:
            if "monoscope_span" in request.extensions:
                record(request, 0, {}, "", [ATError(error).to_dict()])
            raise
    client.send = send_and_record_failure

    return client

def redact_fields(body, paths):
    try:
        # A parsed body is deep-copied, since update() mutates in place and the caller may still use it.
        data = json.loads(body if isinstance(body, (str, bytes, bytearray)) else json.dumps(body))
    except Exception:
        return body.encode('utf-8') if isinstance(body, str) else body
    for path in paths:
        try:
            parse(path).update(data, "[CLIENT_REDACTED]")
        except Exception:
            pass
    return json.dumps(data).encode("utf-8")

class ATError:
    def __init__(self, error):
        timezone = pytz.timezone("UTC")
        self.error_info = {
            'when': datetime.now(timezone).isoformat(),
            'error_type': type(error).__name__,
            'message': str(error),
            'stack_trace': traceback.format_exc()
        }
        root_error = self.get_root_error(error)
        if root_error:
            self.error_info['root_error_type'] = type(root_error).__name__
            self.error_info['root_error_message'] = str(root_error)

    def to_dict(self):
        return self.error_info

    def get_root_error(self, error):
        while error.__cause__ is not None:
            error = error.__cause__
        return error


def report_error(request, error):
    # fast api throws error for trying to access request.apitoolkit_errors
    # so we use request.state.apitoolkit_errors instead
    try:
        errors = request.apitoolkit_errors or []
        at_error = ATError(error)
        errors.append(at_error.to_dict())
        request.apitoolkit_errors = errors
    except Exception as e:
        errors = request.state.apitoolkit_errors or []
        at_error = ATError(error)
        errors.append(at_error.to_dict())
        request.state.apitoolkit_errors = errors
