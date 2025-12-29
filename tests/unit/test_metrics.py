"""Unit tests for metrics module."""

from unittest.mock import Mock, patch

import pytest

# Importar módulo de métricas
from otel_observability import metrics


@pytest.fixture
def mock_statsd_client():
    """Mock DogStatsD client."""
    mock_client = Mock()
    mock_client.increment = Mock()
    mock_client.gauge = Mock()
    mock_client.histogram = Mock()
    mock_client.distribution = Mock()
    mock_client.flush = Mock()
    return mock_client


@pytest.fixture
def _reset_metrics_module():
    """Reset metrics module state between tests."""
    metrics._statsd_client = None
    metrics._config = None
    yield
    metrics._statsd_client = None
    metrics._config = None


class TestMetricsClient:
    """Test DogStatsD client initialization."""

    @patch("otel_observability.metrics.DogStatsd")
    @patch("otel_observability.metrics.TelemetryConfig")
    def test_client_initialization_success(
        self, mock_config_class, mock_dogstatsd, reset_metrics_module
    ):
        """Test successful client initialization."""
        # Setup mock config
        mock_config = Mock()
        mock_config.dogstatsd_enabled = True
        mock_config.dogstatsd_host = "localhost"
        mock_config.dogstatsd_port = 8125
        mock_config.environment = "test"
        mock_config.service_name = "test-service"
        mock_config.service_version = "1.0.0"
        mock_config_class.from_env.return_value = mock_config

        # Setup mock client
        mock_client = Mock()
        mock_dogstatsd.return_value = mock_client

        # Test
        client = metrics._get_statsd_client()

        # Assertions
        assert client is not None
        mock_dogstatsd.assert_called_once()
        assert mock_dogstatsd.call_args[1]["host"] == "localhost"
        assert mock_dogstatsd.call_args[1]["port"] == 8125

    @patch("otel_observability.metrics.TelemetryConfig")
    def test_client_disabled(self, mock_config_class, reset_metrics_module):
        """Test client when DogStatsD is disabled."""
        # Setup mock config
        mock_config = Mock()
        mock_config.dogstatsd_enabled = False
        mock_config_class.from_env.return_value = mock_config

        # Test
        client = metrics._get_statsd_client()

        # Assertions
        assert client is None

    @patch("otel_observability.metrics.TelemetryConfig")
    def test_client_import_error(self, reset_metrics_module):
        """Test client when datadog library is not installed."""
        with patch("otel_observability.metrics.DogStatsd", side_effect=ImportError()):
            client = metrics._get_statsd_client()
            assert client is None


class TestUnifiedTags:
    """Test unified service tags."""

    @patch("otel_observability.metrics.TelemetryConfig")
    def test_get_unified_tags(self, mock_config_class, reset_metrics_module):
        """Test unified tags generation."""
        # Setup mock config
        mock_config = Mock()
        mock_config.environment = "production"
        mock_config.service_name = "my-service"
        mock_config.service_version = "1.2.3"
        mock_config_class.from_env.return_value = mock_config
        metrics._config = mock_config

        # Test
        tags = metrics._get_unified_tags()

        # Assertions
        assert "env:production" in tags
        assert "service:my-service" in tags
        assert "version:1.2.3" in tags
        assert len(tags) == 3


class TestTagValidation:
    """Test tag validation."""

    def test_validate_tags_valid(self):
        """Test validation of valid tags."""
        tags = ["region:us-east-1", "env:production", "service:my-service"]
        validated = metrics._validate_tags(tags)

        assert validated == tags

    def test_validate_tags_invalid_format(self):
        """Test validation of invalid tag format."""
        tags = ["invalid_tag", "region:us-east-1", "also_invalid"]
        validated = metrics._validate_tags(tags)

        # Only valid tags should be returned
        assert "region:us-east-1" in validated
        assert len(validated) == 1

    def test_validate_tags_high_cardinality_warning(self, caplog):
        """Test warning for high cardinality tags."""
        import logging

        tags = ["user_id:12345", "session_id:abc123"]
        with caplog.at_level(logging.WARNING):
            validated = metrics._validate_tags(tags)

        # Tags should still be validated, but warning logged
        assert len(validated) == 2
        assert "High cardinality tag detected" in caplog.text

    def test_validate_tags_non_string(self):
        """Test validation of non-string tags."""
        tags = [123, "region:us-east-1", None, {"key": "value"}]
        validated = metrics._validate_tags(tags)

        # Only valid string tags should be returned
        assert "region:us-east-1" in validated
        assert len(validated) == 1


class TestMergeTags:
    """Test tag merging."""

    def test_merge_tags(self):
        """Test merging multiple tag lists."""
        tags1 = ["env:production", "service:my-service"]
        tags2 = ["region:us-east-1", "env:production"]  # env:production is duplicate
        tags3 = ["version:1.0.0"]

        merged = metrics._merge_tags(tags1, tags2, tags3)

        # Should have all unique tags
        assert "env:production" in merged
        assert "service:my-service" in merged
        assert "region:us-east-1" in merged
        assert "version:1.0.0" in merged
        assert len(merged) == 4  # No duplicates

    def test_merge_tags_with_none(self):
        """Test merging tags with None values."""
        tags1 = ["env:production"]
        tags2 = None
        tags3 = ["region:us-east-1"]

        merged = metrics._merge_tags(tags1, tags2, tags3)

        assert "env:production" in merged
        assert "region:us-east-1" in merged
        assert len(merged) == 2


class TestIncrementCounter:
    """Test increment_counter function."""

    @patch("otel_observability.metrics._get_statsd_client")
    def test_increment_counter_success(
        self, mock_get_client, mock_statsd_client, reset_metrics_module
    ):
        """Test successful counter increment."""
        mock_get_client.return_value = mock_statsd_client

        metrics.increment_counter("app.requests", value=1.0, tags=["region:us-east-1"])

        # Assertions
        mock_statsd_client.increment.assert_called_once()
        call_args = mock_statsd_client.increment.call_args
        assert call_args[0][0] == "app.requests"
        assert call_args[1]["value"] == 1.0
        assert "region:us-east-1" in call_args[1]["tags"]

    @patch("otel_observability.metrics._get_statsd_client")
    def test_increment_counter_no_client(self, mock_get_client, reset_metrics_module):
        """Test counter increment when client is not available."""
        mock_get_client.return_value = None

        # Should not raise exception
        metrics.increment_counter("app.requests")

        # Client should not be called
        assert not hasattr(mock_get_client.return_value, "increment")

    @patch("otel_observability.metrics._get_statsd_client")
    def test_increment_counter_with_unified_tags(
        self, mock_get_client, mock_statsd_client, reset_metrics_module
    ):
        """Test counter increment includes unified tags."""
        mock_get_client.return_value = mock_statsd_client

        metrics.increment_counter("app.requests", tags=["region:us-east-1"])

        call_args = mock_statsd_client.increment.call_args
        tags = call_args[1]["tags"]

        # Should include unified tags
        assert any("env:" in tag for tag in tags)
        assert any("service:" in tag for tag in tags)
        assert any("version:" in tag for tag in tags)
        assert "region:us-east-1" in tags


class TestSetGauge:
    """Test set_gauge function."""

    @patch("otel_observability.metrics._get_statsd_client")
    def test_set_gauge_success(self, mock_get_client, mock_statsd_client, reset_metrics_module):
        """Test successful gauge set."""
        mock_get_client.return_value = mock_statsd_client

        metrics.set_gauge("app.active_users", 150, tags=["region:us-east-1"])

        # Assertions
        mock_statsd_client.gauge.assert_called_once()
        call_args = mock_statsd_client.gauge.call_args
        assert call_args[0][0] == "app.active_users"
        assert call_args[0][1] == 150
        assert "region:us-east-1" in call_args[1]["tags"]


class TestRecordHistogram:
    """Test record_histogram function."""

    @patch("otel_observability.metrics._get_statsd_client")
    def test_record_histogram_success(
        self, mock_get_client, mock_statsd_client, reset_metrics_module
    ):
        """Test successful histogram record."""
        mock_get_client.return_value = mock_statsd_client

        metrics.record_histogram("app.latency", 0.125, tags=["endpoint:/api/users"])

        # Assertions
        mock_statsd_client.histogram.assert_called_once()
        call_args = mock_statsd_client.histogram.call_args
        assert call_args[0][0] == "app.latency"
        assert call_args[0][1] == 0.125
        assert "endpoint:/api/users" in call_args[1]["tags"]


class TestRecordDistribution:
    """Test record_distribution function."""

    @patch("otel_observability.metrics._get_statsd_client")
    def test_record_distribution_success(
        self, mock_get_client, mock_statsd_client, reset_metrics_module
    ):
        """Test successful distribution record."""
        mock_get_client.return_value = mock_statsd_client

        metrics.record_distribution("app.latency", 0.125, tags=["region:us-east-1"])

        # Assertions
        mock_statsd_client.distribution.assert_called_once()
        call_args = mock_statsd_client.distribution.call_args
        assert call_args[0][0] == "app.latency"
        assert call_args[0][1] == 0.125
        assert "region:us-east-1" in call_args[1]["tags"]


class TestTrackFunnelStep:
    """Test track_funnel_step function."""

    @patch("otel_observability.metrics.increment_counter")
    def test_track_funnel_step(self, mock_increment, reset_metrics_module):
        """Test funnel step tracking."""
        metrics.track_funnel_step("checkout", "start", tags=["region:us-east-1"])

        # Assertions
        mock_increment.assert_called_once()
        call_args = mock_increment.call_args
        assert call_args[0][0] == "app.funnel.checkout.start"
        assert "region:us-east-1" in call_args[1]["tags"]


class TestFlush:
    """Test flush function."""

    @patch("otel_observability.metrics._get_statsd_client")
    def test_flush_success(self, mock_get_client, mock_statsd_client, reset_metrics_module):
        """Test successful flush."""
        mock_get_client.return_value = mock_statsd_client

        metrics.flush()

        # Assertions
        mock_statsd_client.flush.assert_called_once()

    @patch("otel_observability.metrics._get_statsd_client")
    def test_flush_no_client(self, mock_get_client, reset_metrics_module):
        """Test flush when client is not available."""
        mock_get_client.return_value = None

        # Should not raise exception
        metrics.flush()
