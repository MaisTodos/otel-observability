"""Configuration for OpenTelemetry."""

from dataclasses import dataclass
import os


@dataclass
class TelemetryConfig:
    """Telemetry configuration from environment variables."""

    service_name: str
    environment: str
    service_version: str
    otlp_endpoint: str
    otlp_headers: dict | None
    is_lambda: bool
    enable_console_export: bool
    log_level: str
    sample_rate: float

    @classmethod
    def from_env(cls) -> "TelemetryConfig":
        """
        Create config from environment variables.

        Environment Variables:
            OTEL_SERVICE_NAME: Service name (required)
            OTEL_ENVIRONMENT: Environment (dev, staging, production)
            OTEL_SERVICE_VERSION: Service version
            OTEL_EXPORTER_OTLP_ENDPOINT: OTLP endpoint URL
            OTEL_EXPORTER_OTLP_HEADERS: OTLP headers (format: key1=value1,key2=value2)
            DD_API_KEY: Datadog API key (if sending directly)
            DD_SITE: Datadog site (datadoghq.com, datadoghq.eu, etc.)
            OTEL_CONSOLE_EXPORT: Enable console exporter for debugging
            OTEL_LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR)
            OTEL_TRACES_SAMPLER_ARG: Sample rate (0.0 to 1.0, default 1.0)
        """
        is_lambda = "AWS_LAMBDA_FUNCTION_NAME" in os.environ

        if otlp_endpoint := os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
            endpoint = otlp_endpoint
        else:
            endpoint = "http://localhost:4318"

        # Parse headers
        headers = cls._parse_headers()

        return cls(
            service_name=os.getenv("OTEL_SERVICE_NAME", "unknown-service"),
            environment=os.getenv("OTEL_ENVIRONMENT", "development"),
            service_version=os.getenv("OTEL_SERVICE_VERSION", "0.0.0"),
            otlp_endpoint=endpoint,
            otlp_headers=headers,
            is_lambda=is_lambda,
            enable_console_export=os.getenv("OTEL_CONSOLE_EXPORT", "false").lower() == "true",
            log_level=os.getenv("OTEL_LOG_LEVEL", "INFO").upper(),
            sample_rate=float(os.getenv("OTEL_TRACES_SAMPLER_ARG", "1.0")),
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
            import warnings

            warnings.warn(  # noqa: B028
                "OTEL_SERVICE_NAME not set. Using 'unknown-service'. "
                "Set OTEL_SERVICE_NAME environment variable.",
                UserWarning,
            )

        if not 0.0 <= self.sample_rate <= 1.0:
            raise ValueError(f"sample_rate must be between 0.0 and 1.0, got {self.sample_rate}")
