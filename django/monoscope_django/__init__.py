import uuid
import json
from opentelemetry.trace import get_tracer, SpanKind
from django.conf import settings
from common import observe_request, report_error, set_attributes

observe_request = observe_request
report_error = report_error
class MonoscopeMiddleware:
    def __init__(self, get_response):
        redact_headers = getattr(
            settings, 'MONOSCOPE_REDACT_HEADERS', [])
        debug = getattr(settings, 'MONOSCOPE_DEBUG', False)
        self.debug = debug
        redact_request_body = getattr(
            settings, 'MONOSCOPE_REDACT_REQUEST_BODY', [])
        redact_response_body = getattr(
            settings, 'MONOSCOPE_REDACT_RESPONSE_BODY', [])
        self.get_response = get_response
        service_version = getattr(
            settings, "MONOSCOPE_SERVICE_VERSION", None)
        tags = getattr(settings, "MONOSCOPE_TAGS", [])
        service_name = getattr(
            settings, "MONOSCOPE_SERVICE_NAME", "")
        capture_request_body = getattr(
            settings, "MONOSCOPE_CAPTURE_REQUEST_BODY", False)
        capture_response_body = getattr(
            settings, "MONOSCOPE_CAPTURE_RESPONSE_BODY", False)
        self.config = {"redact_headers": redact_headers,
                       "debug": debug,
                       "redact_request_body": redact_request_body,
                       "redact_response_body": redact_response_body,
                       "tags": tags,
                       "service_version": service_version,
                       "service_name": service_name,
                       "capture_request_body": capture_request_body,
                       "capture_response_body": capture_response_body
                       }
    def process_exception(self, request, exception):
        report_error(request,exception)
        pass

    def __call__(self, request):
        tracer = get_tracer(self.config['service_name'] or "monoscope-tracer")
        span = tracer.start_span("monoscope.http", kind=SpanKind.SERVER)
        if self.debug:
            print("Monoscope: making request")
        request_method = request.method
        raw_url = request.get_full_path()
        request_body = None
        query_params = dict(request.GET.copy())
        request_headers = request.headers
        content_type = request.headers.get('Content-Type', '')
        if content_type == 'application/json':
            request_body = json.loads(request.body.decode('utf-8'))
        if content_type == 'text/plain':
            request_body = request.body.decode('utf-8')
        if content_type == 'application/x-www-form-urlencoded' or 'multipart/form-data' in content_type:
            request_body = dict(request.POST.copy())
        request.apitoolkit_message_id = str(uuid.uuid4())
        request.apitoolkit_errors = []
        request.apitoolkit_client = self
        response = self.get_response(request)

        if self.debug:
            print("Monoscope: after request")
        try:
            url_path = request.resolver_match.route if request.resolver_match is not None else None
            path_params = request.resolver_match.kwargs if request.resolver_match is not None else {}
            status_code = response.status_code
            request_body = json.dumps(request_body)
            response_headers = response.headers
            request_body = request_body
            response_body = response.content.decode('utf-8')
            message_id = request.apitoolkit_message_id
            errors = request.apitoolkit_errors
            host = request.headers.get('HOST') or ""

            set_attributes(
                span,
                host,
                status_code,
                query_params,
                path_params,
                request_headers,
                response_headers,
                request_method,
                raw_url,
                message_id,
                url_path,
                request_body,
                response_body,
                errors,
                self.config,
                "PythonDjango"
            )
        except Exception as e:
            span.record_exception(e)
            span.end()
            return response
        return response

