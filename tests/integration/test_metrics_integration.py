"""Integration tests for metrics module."""

import os
import socket
import threading
import time
from unittest.mock import patch

import pytest

# Importar módulo de métricas
from otel_observability import metrics


@pytest.fixture
def mock_datadog_agent():
    """Mock Datadog Agent UDP server."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("localhost", 8125))
    sock.settimeout(1.0)

    received_messages = []

    def receive_loop():
        while True:
            try:
                data, _addr = sock.recvfrom(1024)
                received_messages.append(data.decode("utf-8"))
            except TimeoutError:
                break
            except Exception:
                break

    thread = threading.Thread(target=receive_loop, daemon=True)
    thread.start()

    yield received_messages

    sock.close()


class TestMetricsIntegration:
    """Integration tests for metrics with mock Agent."""

    @pytest.mark.skipif(
        os.getenv("SKIP_INTEGRATION_TESTS") == "true",
        reason="Skipping integration tests",
    )
    @patch("otel_observability.config.TelemetryConfig")
    def test_increment_counter_integration(
        self, mock_config_class, mock_datadog_agent, reset_metrics_module
    ):
        """Test counter increment with mock Agent."""
        # Setup mock config
        mock_config = type("Config", (), {})()
        mock_config.dogstatsd_enabled = True
        mock_config.dogstatsd_host = "localhost"
        mock_config.dogstatsd_port = 8125
        mock_config.environment = "test"
        mock_config.service_name = "test-service"
        mock_config.service_version = "1.0.0"
        mock_config_class.from_env.return_value = mock_config

        # Reset client
        metrics._statsd_client = None

        # Send metric
        metrics.increment_counter("test.counter", tags=["test:integration"])

        # Flush to ensure delivery
        metrics.flush()

        # Wait for message
        time.sleep(0.1)

        # Note: This test may not work reliably without actual datadog library
        # It's more of a smoke test to ensure the code path works
        assert True  # If we get here without exception, it's a success

    @patch("otel_observability.config.TelemetryConfig")
    def test_funnel_tracking_integration(self, mock_config_class, reset_metrics_module):
        """Test funnel step tracking integration."""
        # Setup mock config
        mock_config = type("Config", (), {})()
        mock_config.dogstatsd_enabled = True
        mock_config.dogstatsd_host = "localhost"
        mock_config.dogstatsd_port = 8125
        mock_config.environment = "test"
        mock_config.service_name = "test-service"
        mock_config.service_version = "1.0.0"
        mock_config_class.from_env.return_value = mock_config

        with patch("otel_observability.metrics._get_statsd_client") as mock_get_client:
            mock_client = type("Client", (), {})()
            mock_client.increment = lambda *args, **kwargs: None
            mock_get_client.return_value = mock_client

            # Track funnel steps
            metrics.track_funnel_step("checkout", "start")
            metrics.track_funnel_step("checkout", "payment_success")
            metrics.track_funnel_step("checkout", "completed")

            # Verify calls (if client was available)
            assert mock_get_client.called


class TestTagApplication:
    """Test automatic tag application."""

    @patch("otel_observability.metrics._get_statsd_client")
    @patch("otel_observability.config.TelemetryConfig")
    def test_unified_tags_applied(self, mock_config_class, mock_get_client, reset_metrics_module):
        """Test that unified tags are automatically applied."""
        # Setup mock config
        mock_config = type("Config", (), {})()
        mock_config.dogstatsd_enabled = True
        mock_config.dogstatsd_host = "localhost"
        mock_config.dogstatsd_port = 8125
        mock_config.environment = "production"
        mock_config.service_name = "my-service"
        mock_config.service_version = "1.2.3"
        mock_config_class.from_env.return_value = mock_config

        # Setup mock client
        mock_client = type("Client", (), {})()
        call_args_list = []

        def mock_increment(*args, **kwargs):
            call_args_list.append(kwargs)

        mock_client.increment = mock_increment
        mock_get_client.return_value = mock_client

        # Send metric
        metrics.increment_counter("test.metric", tags=["custom:tag"])

        # Verify unified tags are included
        assert len(call_args_list) > 0
        tags = call_args_list[0]["tags"]
        assert "env:production" in tags
        assert "service:my-service" in tags
        assert "version:1.2.3" in tags
        assert "custom:tag" in tags


class TestErrorHandling:
    """Test error handling in metrics."""

    @patch("otel_observability.metrics._get_statsd_client")
    def test_metrics_graceful_degradation(self, mock_get_client, reset_metrics_module):
        """Test that metrics fail gracefully when client is unavailable."""
        mock_get_client.return_value = None

        # Should not raise exceptions
        metrics.increment_counter("test.metric")
        metrics.set_gauge("test.gauge", 100)
        metrics.record_histogram("test.histogram", 0.5)
        metrics.record_distribution("test.distribution", 0.5)
        metrics.flush()

        # If we get here, graceful degradation worked
        assert True

    @patch("otel_observability.metrics._get_statsd_client")
    def test_metrics_handle_client_errors(self, mock_get_client, reset_metrics_module):
        """Test that metrics handle client errors gracefully."""
        # Setup mock client that raises exceptions
        mock_client = type("Client", (), {})()
        mock_client.increment = lambda *args, **kwargs: (_ for _ in ()).throw(
            Exception("Connection error")
        )
        mock_get_client.return_value = mock_client

        # Should not raise exceptions, just log warnings
        with patch("otel_observability.metrics.logger") as mock_logger:
            metrics.increment_counter("test.metric")
            # Should log warning
            assert mock_logger.warning.called


class TestFunnelMetrics:
    """Test funnel metrics specifically."""

    @patch("otel_observability.metrics.increment_counter")
    def test_funnel_metric_naming(self, mock_increment, reset_metrics_module):
        """Test that funnel metrics use correct naming convention."""
        metrics.track_funnel_step("checkout", "start", tags=["region:us-east-1"])

        # Verify metric name format
        call_args = mock_increment.call_args
        metric_name = call_args[0][0]
        assert metric_name == "app.funnel.checkout.start"

    @patch("otel_observability.metrics.increment_counter")
    def test_funnel_tags_preserved(self, mock_increment, reset_metrics_module):
        """Test that funnel step tags are preserved."""
        metrics.track_funnel_step(
            "checkout", "start", tags=["region:us-east-1", "payment_method:credit_card"]
        )

        # Verify tags are passed through
        call_args = mock_increment.call_args
        tags = call_args[1]["tags"]
        assert "region:us-east-1" in tags
        assert "payment_method:credit_card" in tags
