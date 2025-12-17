"""Testes unitários para o módulo config."""

import os
from unittest.mock import patch

import pytest

from otel_observability.config import TelemetryConfig


@pytest.mark.unit
class TestTelemetryConfig:
    """Testes para TelemetryConfig."""

    def test_from_env_with_all_vars(self, mock_env_vars: dict):
        """Testa criação de config com todas as variáveis de ambiente."""
        config = TelemetryConfig.from_env()

        assert config.service_name == "test-service"
        assert config.environment == "test"
        assert config.service_version == "1.0.0"
        assert config.otlp_endpoint == "http://localhost:4318"
        assert config.enable_console_export is False
        assert config.log_level == "INFO"
        assert config.sample_rate == 1.0

    def test_from_env_with_defaults(self):
        """Testa criação de config com valores padrão."""
        with patch.dict(os.environ, {}, clear=True):
            config = TelemetryConfig.from_env()

            assert config.service_name == "unknown-service"
            assert config.environment == "development"
            assert config.service_version == "0.0.0"
            assert config.otlp_endpoint == "http://localhost:4318"
            assert config.sample_rate == 1.0

    def test_from_env_custom_endpoint(self):
        """Testa configuração de endpoint customizado."""
        with patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://custom:4318"}):
            config = TelemetryConfig.from_env()
            assert config.otlp_endpoint == "http://custom:4318"

    def test_from_env_detect_lambda(self):
        """Testa detecção de ambiente Lambda."""
        with patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "test-function"}):
            config = TelemetryConfig.from_env()
            assert config.is_lambda is True

    def test_from_env_not_lambda(self, mock_env_vars: dict):
        """Testa que não é Lambda quando variável não está presente."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove AWS_LAMBDA_FUNCTION_NAME se existir
            os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
            config = TelemetryConfig.from_env()
            assert config.is_lambda is False

    def test_parse_headers_from_env(self):
        """Testa parsing de headers do ambiente."""
        with patch.dict(
            os.environ,
            {"OTEL_EXPORTER_OTLP_HEADERS": "key1=value1,key2=value2"},
        ):
            config = TelemetryConfig.from_env()
            assert config.otlp_headers == {"key1": "value1", "key2": "value2"}

    def test_parse_headers_datadog(self):
        """Testa parsing de headers do Datadog."""
        with patch.dict(
            os.environ,
            {
                "DD_API_KEY": "test-api-key",
                "DD_SITE": "datadoghq.com",
            },
        ):
            config = TelemetryConfig.from_env()
            assert config.otlp_headers["DD-API-KEY"] == "test-api-key"
            assert config.otlp_headers["DD-SITE"] == "datadoghq.com"

    def test_console_export_enabled(self):
        """Testa habilitação de console export."""
        with patch.dict(os.environ, {"OTEL_CONSOLE_EXPORT": "true"}):
            config = TelemetryConfig.from_env()
            assert config.enable_console_export is True

    def test_sample_rate_custom(self):
        """Testa configuração de sample rate customizado."""
        with patch.dict(os.environ, {"OTEL_TRACES_SAMPLER_ARG": "0.5"}):
            config = TelemetryConfig.from_env()
            assert config.sample_rate == 0.5

    def test_sample_rate_invalid_raises_error(self):
        """Testa que sample rate inválido levanta erro."""
        with (
            patch.dict(os.environ, {"OTEL_TRACES_SAMPLER_ARG": "2.0"}),
            pytest.raises(ValueError, match="sample_rate must be between"),
        ):
            TelemetryConfig.from_env()

    def test_sample_rate_negative_raises_error(self):
        """Testa que sample rate negativo levanta erro."""
        with (
            patch.dict(os.environ, {"OTEL_TRACES_SAMPLER_ARG": "-0.1"}),
            pytest.raises(ValueError, match="sample_rate must be between"),
        ):
            TelemetryConfig.from_env()

    def test_warning_on_unknown_service(self):
        """Testa que warning é emitido quando service_name não está definido."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.warns(UserWarning, match="OTEL_SERVICE_NAME not set"):
                config = TelemetryConfig.from_env()
            assert config.service_name == "unknown-service"
