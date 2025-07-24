import uuid
from flask import request, g
import json
from common import observe_request, report_error, set_attributes
from werkzeug.exceptions import HTTPException
from opentelemetry.trace import get_tracer, SpanKind


observe_request = observe_request
report_error = report_error
class Monoscope:
    def __init__(self, redact_headers=["Authorization", "Cookie"], service_name="", redact_request_body=[], redact_response_body=[], capture_request_body=False, capture_response_body=False, debug=False, service_version=None, tags=[]):
        self.debug = debug
        self.redact_headers = redact_headers
        self.redact_request_body = redact_request_body
        self.redact_response_body = redact_response_body
        self.service_version = service_version
        self.service_name = service_name
        self.tags = tags
        self.config = {
            'redact_headers': redact_headers,
            'redact_request_body': redact_request_body,
            'redact_response_body': redact_response_body,
            'debug': debug,
            'capture_request_body': capture_request_body,
            'capture_response_body': capture_response_body,
            'service_version': service_version,
            'tags': tags,
            'service_name': service_name
        }

    def beforeRequest(self):
        tracer = get_tracer(self.service_name or "monoscope-tracer")
        span = tracer.start_span("monoscope.http", kind=SpanKind.SERVER)
        if self.debug:
            print("Monoscope: beforeRequest")
        request_method = request.method
        raw_url = request.full_path
        url_path = request.url_rule.rule if request.url_rule is not None else request.full_path
        request_body = None
        query_params = request.args.copy().to_dict()
        path_params = request.view_args.copy() if request.view_args is not None else {}
        request_headers = dict(request.headers)
        content_type = request.headers.get('Content-Type', '')

        if content_type == 'application/json':
            request_body = request.get_json()
        if content_type == 'text/plain':
            request_body = request.get_data().decode('utf-8')
        if content_type == 'application/x-www-form-urlencoded' or 'multipart/form-data' in content_type:
            request_body = request.form.copy().to_dict()

        g.apitoolkit_request_data = {
            "span": span,
            "query_params": query_params,
            "path_params": path_params,
            "request_headers": request_headers,
            "method": request_method,
            "url_path": url_path,
            "raw_url": raw_url,
            "request_body": request_body,
            "host": request.host,
            "referer": request.headers.get('Referer', "")
        }
        request.apitoolkit_message_id = str(uuid.uuid4())
        request.apitoolkit_errors = []
        request.apitoolkit_client = self

    def afterRequest(self, response):
        if self.debug:
            print("Monoscope: afterRequest")

        apitoolkit_request_data = g.get("apitoolkit_request_data", {})
        status_code = response.status_code
        request_body = json.dumps(
            apitoolkit_request_data.get("request_body", {}))
        response_headers = dict(response.headers)
        response_body = ""
        if not response.direct_passthrough:
          response_body = response.data
        message_id = request.apitoolkit_message_id
        span = apitoolkit_request_data.get("span", None)
        host = apitoolkit_request_data.get("host", "")
        query_params = apitoolkit_request_data.get("query_params", {})
        path_params = apitoolkit_request_data.get("path_params", {})
        request_headers = apitoolkit_request_data.get("request_headers", {})
        try:
            set_attributes(
               span,
               host,
               status_code,
               query_params,
               path_params,
               request_headers,
               response_headers,
               apitoolkit_request_data.get("method", ""),
               apitoolkit_request_data.get("url_path", ""),
               message_id,
               apitoolkit_request_data.get("raw_url", ""),
               request_body,
               response_body,
               request.apitoolkit_errors,
               self.config,
               "PythonFlask"
               )
        except Exception as e:
            return None
    def handle_error(self, e):
     if not isinstance(e, HTTPException):
        report_error(request, e)
