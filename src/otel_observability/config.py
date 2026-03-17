"""Configuration for OpenTelemetry."""

from dataclasses import dataclass
import os
import warnings


@dataclass
class TelemetryConfig:
    """Telemetry configuration from environment variables."""

    service_name: str
    environment: str
    service_version: str
    otlp_endpoint: str
    otlp_traces_endpoint: str | None
    otlp_metrics_endpoint: str | None
    otlp_logs_endpoint: str | None
    traces_enabled: bool
    otlp_headers: dict | None
    is_lambda: bool
    enable_console_export: bool
    log_level: str
    sample_rate: float
    dogstatsd_enabled: bool
    dogstatsd_host: str
    dogstatsd_port: int

    @classmethod
    def from_env(cls) -> "TelemetryConfig":
        """
        Create config from environment variables.

        Environment Variables:
            OTEL_SERVICE_NAME: Service name (required)
            OTEL_ENVIRONMENT: Environment (dev, staging, production)
            OTEL_SERVICE_VERSION: Service version
            OTEL_EXPORTER_OTLP_ENDPOINT: OTLP base endpoint (fallback for all signals)
            OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: Traces-specific endpoint (overrides base)
            OTEL_EXPORTER_OTLP_METRICS_ENDPOINT: Metrics-specific endpoint (overrides base)
            OTEL_EXPORTER_OTLP_LOGS_ENDPOINT: Logs-specific endpoint (enables OTLP log export)
            OTEL_TRACES_ENABLED: Explicitly enable/disable traces exporter (default: true if endpoint available)
            OTEL_EXPORTER_OTLP_HEADERS: OTLP headers (format: key1=value1,key2=value2)
            DD_API_KEY: Datadog API key (if sending directly)
            DD_SITE: Datadog site (datadoghq.com, datadoghq.eu, etc.)
            OTEL_CONSOLE_EXPORT: Enable console exporter for debugging
            OTEL_LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR)
            OTEL_TRACES_SAMPLER_ARG: Sample rate (0.0 to 1.0, default 1.0)
            DD_DOGSTATSD_ENABLED: Enable DogStatsD metrics (default: true)
            DD_DOGSTATSD_HOST: DogStatsD host (default: localhost)
            DD_DOGSTATSD_PORT: DogStatsD port (default: 8125)
        """
        is_lambda = "AWS_LAMBDA_FUNCTION_NAME" in os.environ

        if otlp_endpoint := os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
            endpoint = otlp_endpoint
        else:
            endpoint = "http://localhost:4318"

        # Signal-specific endpoint resolution: signal-specific > generic > None
        generic_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

        otlp_traces_endpoint = (
            os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or generic_endpoint or None
        )
        otlp_metrics_endpoint = (
            os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT") or generic_endpoint or None
        )
        otlp_logs_endpoint = (
            os.getenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT") or generic_endpoint or None
        )

        traces_enabled = (
            os.getenv("OTEL_TRACES_ENABLED", "true").lower() == "true"
            and otlp_traces_endpoint is not None
        )

        if not otlp_traces_endpoint:
            warnings.warn(  # noqa: B028
                "No OTLP traces endpoint configured. Traces will not be exported. "
                "Set OTEL_EXPORTER_OTLP_TRACES_ENDPOINT or OTEL_EXPORTER_OTLP_ENDPOINT.",
                UserWarning,
            )

        # Parse headers
        headers = cls._parse_headers()

        # DogStatsD configuration
        dogstatsd_enabled = os.getenv("DD_DOGSTATSD_ENABLED", "true").lower() == "true"
        dogstatsd_host = os.getenv("DD_DOGSTATSD_HOST", "localhost")
        dogstatsd_port = int(os.getenv("DD_DOGSTATSD_PORT", "8125"))

        return cls(
            service_name=os.getenv("OTEL_SERVICE_NAME", "unknown-service"),
            environment=os.getenv("OTEL_ENVIRONMENT", "development"),
            service_version=os.getenv("OTEL_SERVICE_VERSION", "0.0.0"),
            otlp_endpoint=endpoint,
            otlp_traces_endpoint=otlp_traces_endpoint,
            otlp_metrics_endpoint=otlp_metrics_endpoint,
            otlp_logs_endpoint=otlp_logs_endpoint,
            traces_enabled=traces_enabled,
            otlp_headers=headers,
            is_lambda=is_lambda,
            enable_console_export=os.getenv("OTEL_CONSOLE_EXPORT", "false").lower() == "true",
            log_level=os.getenv("OTEL_LOG_LEVEL", "INFO").upper(),
            sample_rate=float(os.getenv("OTEL_TRACES_SAMPLER_ARG", "1.0")),
            dogstatsd_enabled=dogstatsd_enabled,
            dogstatsd_host=dogstatsd_host,
            dogstatsd_port=dogstatsd_port,
        )

    @staticmethod
    def _parse_headers() -> dict | None:
        """Parse OTLP headers from environment."""
        headers = {}

        # From OTEL_EXPORTER_OTLP_HEADERS
        if headers_str := os.getenv("OTEL_EXPORTER_OTLP_HEADERS"):
            for pair in headers_str.split(","):
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    headers[key.strip()] = value.strip()

        # Datadog API Key
        if dd_api_key := os.getenv("DD_API_KEY"):
            headers["DD-API-KEY"] = dd_api_key

        # Datadog Site
        if dd_site := os.getenv("DD_SITE"):
            headers["DD-SITE"] = dd_site

        return headers if headers else None

    def __post_init__(self):
        """Validate configuration."""
        if self.service_name == "unknown-service":
            warnings.warn(  # noqa: B028
                "OTEL_SERVICE_NAME not set. Using 'unknown-service'. "
                "Set OTEL_SERVICE_NAME environment variable.",
                UserWarning,
            )

        if not 0.0 <= self.sample_rate <= 1.0:
            raise ValueError(f"sample_rate must be between 0.0 and 1.0, got {self.sample_rate}")
