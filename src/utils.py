# src/utils.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from prometheus_client import Counter, Histogram, REGISTRY, Gauge
from prometheus_client.openmetrics.exposition import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match
import time
import logging

logger = logging.getLogger(__name__)

REQUESTS = Counter(
    "fastapi_requests_total",
    "Total request count",
    ["method", "path", "app_name"],
)
RESPONSES = Counter(
    "fastapi_responses_total",
    "Total response count",
    ["method", "path", "status_code", "app_name"],
)
REQUESTS_PROCESSING_TIME = Histogram(
    "fastapi_requests_duration_seconds",
    "Histogram of requests processing time by path (in seconds)",
    ["method", "path", "app_name"],
)
EXCEPTIONS = Counter(
    "fastapi_exceptions_total",
    "Total exception count",
    ["method", "path", "exception_type", "app_name"],
)
REQUESTS_IN_PROGRESS = Gauge(
    "fastapi_requests_in_progress",
    "Total requests currently being processed",
    ["method", "path", "app_name"],
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, app_name: str):
        super().__init__(app)
        self.app_name = app_name

    async def dispatch(self, request: Request, call_next):
        method = request.method
        path, is_handled = self.get_path(request)

        if not is_handled or path == "/metrics":
            return await call_next(request)

        REQUESTS_IN_PROGRESS.labels(method=method, path=path, app_name=self.app_name).inc()
        REQUESTS.labels(method=method, path=path, app_name=self.app_name).inc()
        before_time = time.perf_counter()

        try:
            logger.info(f"{method} {path}")
            response = await call_next(request)
            logger.info(f"{method} {path} {response.status_code}")
        except Exception as e:
            EXCEPTIONS.labels(method=method, path=path, exception_type=type(e).__name__, app_name=self.app_name).inc()
            raise e
        else:
            after_time = time.perf_counter()
            span = trace.get_current_span()
            trace_id = trace.format_trace_id(span.get_span_context().trace_id)
            REQUESTS_PROCESSING_TIME.labels(method=method, path=path, app_name=self.app_name).observe(
                after_time - before_time, exemplar={"TraceID": trace_id}
            )
            RESPONSES.labels(method=method, path=path, status_code=response.status_code, app_name=self.app_name).inc()
        finally:
            REQUESTS_IN_PROGRESS.labels(method=method, path=path, app_name=self.app_name).dec()

        return response

    @staticmethod
    def get_path(request: Request):
        for route in request.app.routes:
            match, _ = route.matches(request.scope)
            if match == Match.FULL:
                return route.path, True
        return request.url.path, False


def metrics(request: Request) -> Response:
    return Response(generate_latest(REGISTRY), headers={"Content-Type": CONTENT_TYPE_LATEST})


def setting_otlp(app, app_name: str, endpoint: str) -> None:
    resource = Resource.create(attributes={"service.name": app_name})
    tracer = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer)
    tracer.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer)
