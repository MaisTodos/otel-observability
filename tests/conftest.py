"""Pytest configuration and shared fixtures."""

from collections.abc import Generator
from contextlib import suppress
import os
from unittest.mock import MagicMock, patch

import pytest

from otel_observability.config import TelemetryConfig


@pytest.fixture
def mock_env_vars() -> Generator[dict, None, None]:
    """Fixture para mockar variáveis de ambiente."""
    env_vars = {
        "OTEL_SERVICE_NAME": "test-service",
        "OTEL_ENVIRONMENT": "test",
        "OTEL_SERVICE_VERSION": "1.0.0",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
        "OTEL_CONSOLE_EXPORT": "false",
        "OTEL_LOG_LEVEL": "INFO",
        "OTEL_TRACES_SAMPLER_ARG": "1.0",
    }

    with patch.dict(os.environ, env_vars, clear=False):
        yield env_vars


@pytest.fixture
def telemetry_config(mock_env_vars: dict) -> TelemetryConfig:
    """Fixture que retorna uma configuração de telemetria para testes."""
    return TelemetryConfig.from_env()


@pytest.fixture(name="reset_telemetry")
def _reset_telemetry() -> Generator[None, None, None]:
    """Fixture para resetar o estado global de telemetria entre testes."""
    from otel_observability.tracer import shutdown_telemetry

    yield

    # Limpar após o teste
    with suppress(Exception):
        shutdown_telemetry(timeout=1)

    # Resetar variáveis globais
    import otel_observability.tracer as tracer_module

    tracer_module._tracer_provider = None
    tracer_module._config = None


@pytest.fixture(name="reset_log_context")
def _reset_log_context() -> Generator[None, None, None]:
    """Fixture para limpar contexto de log entre testes."""
    from otel_observability.logging import clear_log_context

    yield

    # Limpar após o teste
    clear_log_context()


@pytest.fixture
def mock_otlp_exporter() -> Generator[MagicMock, None, None]:
    """Fixture para mockar o OTLP exporter."""
    with patch("otel_observability.tracer.OTLPSpanExporter") as mock:
        yield mock


@pytest.fixture
def mock_tracer_provider() -> Generator[MagicMock, None, None]:
    """Fixture para mockar o TracerProvider."""
    with patch("otel_observability.tracer.TracerProvider") as mock:
        provider = MagicMock()
        mock.return_value = provider
        yield provider
