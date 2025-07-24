from base64 import b64encode
import json
from datetime import datetime
from opentelemetry.trace import get_tracer, SpanKind
import traceback
import requests
from jsonpath_ng import parse
import json
import pytz
import httpx


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
        def redact_header(header: str) -> str:
            if header.lower() in (config.get("redact_headers", []) + ["cookies", "authorization"]):
                return "[CLIENT_REDACTED]"
            return header

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

        for header, value in req_headers.items():
            span.set_attribute(f"http.request.header.{header}", redact_header(str(value)))

        for header, value in resp_headers.items():
            span.set_attribute(f"http.response.header.{header}", redact_header(str(value)))

    except Exception as error:
        span.record_exception(error)
    finally:
        span.end()


def observe_request(parent_request, url_wildcard=None,redact_headers=[], redact_request_body=[], redact_response_body=[]):
    start_time = 0
    span = None
    req = None

    def on_request(request):
        nonlocal start_time, req, span
        # create an open telemetry span
        tracer = get_tracer("monoscope-tracer")
        span = tracer.start_span("monoscope.http", kind=SpanKind.CLIENT)
        req = request
        return request

    def on_response(response):
      try:
        response.read()
        message_id = parent_request.apitoolkit_message_id if hasattr(
            parent_request, "apitoolkit_message_id") else parent_request.state.apitoolkit_message_id if hasattr(parent_request.state, "apitoolkit_message_id") else None
        if message_id is None:
            print(
                "No message_id found attached to request, make sure middleware is configured correctly")

        host = req.url.host if req.url else ""
        url_path = url_wildcard or req.url.path
        path_and_query = get_path_and_query_params_from_url(req.url) if req.url else {
        "path": "", "queryParams": {}, "rawUrl": ""}
        req_body = req.content.decode()
        res_body = response.text
        req_headers = dict((k, v if isinstance(v, list) else [v]) for k, v in req.headers.items())
        res_headers = dict((k, v if isinstance(v, list) else [v]) for k, v in (response.headers if response else {}).items())
        config = {"redact_headers": redact_headers, "redact_request_body": redact_request_body, "redact_response_body": redact_response_body}
        set_attributes(
            span, host, response.status_code,
            path_and_query["queryParams"], {},
            req_headers, res_headers, req.method.upper() if req.method else "",
            req.url.path, message_id, url_path, req_body, res_body, [], config, sdk_type="PythonOutgoing")
      except Exception as e:
          pass

    client = httpx.Client(event_hooks={'request': [
        on_request], 'response': [on_response]})

    return client

def redact_fields(body, paths):
    try:
        data = json.loads(body)
        for path in paths:
            expr = parse(path)
            expr.update(data, "[CLIENT_REDACTED]")
        return json.dumps(data).encode("utf-8")
    except Exception as e:
        if isinstance(body, str):
            return body.encode('utf-8')
        return body

def get_path_and_query_params_from_url(url):
    try:
        parsed_url = requests.utils.urlparse(url)
        path = parsed_url.path
        query_params = dict(requests.utils.parse_qsl(parsed_url.query))
        raw_url = url
        return {"path": path, "queryParams": query_params, "rawUrl": raw_url}
    except Exception as e:
        return {"path": "", "queryParams": {}, "rawUrl": ""}

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
