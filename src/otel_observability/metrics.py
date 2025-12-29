"""Custom metrics via DogStatsD for business metrics and conversion funnels."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Cliente DogStatsD global (singleton)
_statsd_client: Any = None
_config: Any = None


def _get_statsd_client():
    """Get or create DogStatsD client (singleton)."""
    global _statsd_client, _config

    if _statsd_client is not None:
        return _statsd_client

    try:
        from datadog import DogStatsd

        # Obter configuração
        from .config import TelemetryConfig

        _config = TelemetryConfig.from_env()

        if not _config.dogstatsd_enabled:
            logger.debug("DogStatsD is disabled in configuration")
            return None

        # Criar cliente
        _statsd_client = DogStatsd(
            host=_config.dogstatsd_host,
            port=_config.dogstatsd_port,
            constant_tags=_get_unified_tags(),
        )

        logger.info(
            f"DogStatsD client initialized: host={_config.dogstatsd_host}, "
            f"port={_config.dogstatsd_port}"
        )

        return _statsd_client

    except ImportError:
        logger.warning(
            "datadog library not installed. Install with: pip install otel-observability[metrics]"
        )
        return None
    except Exception as e:
        logger.warning(f"Failed to initialize DogStatsD client: {e}")
        return None


def _get_unified_tags() -> list[str]:
    """Get unified service tags (env, service, version)."""
    from .config import TelemetryConfig

    config = _config or TelemetryConfig.from_env()

    return [
        f"env:{config.environment}",
        f"service:{config.service_name}",
        f"version:{config.service_version}",
    ]


def _validate_tags(tags: list[str] | None) -> list[str]:
    """
    Validate tags and warn about high cardinality.

    Args:
        tags: List of tags to validate.

    Returns:
        Validated tags list.
    """
    if not tags:
        return []

    validated = []
    high_cardinality_patterns = ["user_id", "session_id", "request_id", "trace_id"]

    for tag in tags:
        if not isinstance(tag, str):
            logger.warning(f"Invalid tag type: {type(tag)}, skipping")
            continue

        if ":" not in tag:
            logger.warning(f"Invalid tag format (missing ':'): {tag}, skipping")
            continue

        # Verificar alta cardinalidade
        tag_key = tag.split(":")[0].lower()
        if any(pattern in tag_key for pattern in high_cardinality_patterns):
            logger.warning(
                f"High cardinality tag detected: {tag}. "
                "Consider using logs instead of metrics for high cardinality data."
            )

        validated.append(tag)

    return validated


def _merge_tags(*tag_lists: list[str] | None) -> list[str]:
    """Merge multiple tag lists, removing duplicates."""
    merged = []
    seen = set()

    for tag_list in tag_lists:
        if tag_list:
            for tag in tag_list:
                if tag not in seen:
                    merged.append(tag)
                    seen.add(tag)

    return merged


def increment_counter(
    metric_name: str,
    value: float = 1.0,
    tags: list[str] | None = None,
    sample_rate: float = 1.0,
) -> None:
    """
    Increment a counter metric.

    Counters are cumulative metrics that track the total number of events.
    Use counters for metrics like request counts, error counts, etc.

    Args:
        metric_name: Name of the metric (e.g., "app.checkout.start").
        value: Value to increment by (default: 1.0).
        tags: Optional list of tags (e.g., ["region:us-east-1", "env:production"]).
        sample_rate: Sample rate (0.0 to 1.0, default: 1.0).

    Example:
        >>> from otel_observability.metrics import increment_counter
        >>>
        >>> increment_counter("app.checkout.start", tags=["region:us-east-1"])
        >>> increment_counter("app.errors", value=1.0, tags=["error_type:validation"])
    """
    client = _get_statsd_client()
    if client is None:
        return

    try:
        validated_tags = _validate_tags(tags)
        all_tags = _merge_tags(_get_unified_tags(), validated_tags)

        client.increment(metric_name, value=value, tags=all_tags, sample_rate=sample_rate)
    except Exception as e:
        logger.warning(f"Failed to send counter metric {metric_name}: {e}")


def set_gauge(
    metric_name: str,
    value: float,
    tags: list[str] | None = None,
) -> None:
    """
    Set a gauge metric.

    Gauges represent a value at a specific point in time.
    Use gauges for metrics like active users, queue size, etc.

    Args:
        metric_name: Name of the metric (e.g., "app.active_users").
        value: Current value of the gauge.
        tags: Optional list of tags.

    Example:
        >>> from otel_observability.metrics import set_gauge
        >>>
        >>> set_gauge("app.active_users", 150, tags=["region:us-east-1"])
        >>> set_gauge("app.queue.size", queue_length, tags=["queue:orders"])
    """
    client = _get_statsd_client()
    if client is None:
        return

    try:
        validated_tags = _validate_tags(tags)
        all_tags = _merge_tags(_get_unified_tags(), validated_tags)

        client.gauge(metric_name, value=value, tags=all_tags)
    except Exception as e:
        logger.warning(f"Failed to send gauge metric {metric_name}: {e}")


def record_histogram(
    metric_name: str,
    value: float,
    tags: list[str] | None = None,
    sample_rate: float = 1.0,
) -> None:
    """
    Record a histogram metric.

    Histograms track the statistical distribution of values.
    Use histograms for metrics like request latency, response sizes, etc.

    Args:
        metric_name: Name of the metric (e.g., "app.request.latency").
        value: Value to record.
        tags: Optional list of tags.
        sample_rate: Sample rate (0.0 to 1.0, default: 1.0).

    Example:
        >>> from otel_observability.metrics import record_histogram
        >>>
        >>> record_histogram("app.request.latency", 0.125, tags=["endpoint:/api/users"])
    """
    client = _get_statsd_client()
    if client is None:
        return

    try:
        validated_tags = _validate_tags(tags)
        all_tags = _merge_tags(_get_unified_tags(), validated_tags)

        client.histogram(metric_name, value=value, tags=all_tags, sample_rate=sample_rate)
    except Exception as e:
        logger.warning(f"Failed to send histogram metric {metric_name}: {e}")


def record_distribution(
    metric_name: str,
    value: float,
    tags: list[str] | None = None,
) -> None:
    """
    Record a distribution metric.

    Distributions are global histograms that aggregate across all hosts.
    Use distributions for metrics like latency across datacenters.

    Args:
        metric_name: Name of the metric (e.g., "app.request.latency").
        value: Value to record.
        tags: Optional list of tags.

    Example:
        >>> from otel_observability.metrics import record_distribution
        >>>
        >>> record_distribution("app.request.latency", 0.125, tags=["region:us-east-1"])
    """
    client = _get_statsd_client()
    if client is None:
        return

    try:
        validated_tags = _validate_tags(tags)
        all_tags = _merge_tags(_get_unified_tags(), validated_tags)

        client.distribution(metric_name, value=value, tags=all_tags)
    except Exception as e:
        logger.warning(f"Failed to send distribution metric {metric_name}: {e}")


def track_funnel_step(
    funnel_name: str,
    step_name: str,
    tags: list[str] | None = None,
) -> None:
    """
    Track a step in a conversion funnel.

    This is a helper function that increments a counter metric with a standardized
    naming convention for funnel analysis.

    Metric name format: `app.funnel.{funnel_name}.{step_name}`

    Args:
        funnel_name: Name of the funnel (e.g., "checkout", "signup").
        step_name: Name of the step (e.g., "start", "payment_success", "completed").
        tags: Optional list of tags for segmentation.

    Example:
        >>> from otel_observability.metrics import track_funnel_step
        >>>
        >>> # Track checkout funnel steps
        >>> track_funnel_step("checkout", "start", tags=["region:us-east-1"])
        >>> track_funnel_step("checkout", "payment_success", tags=["region:us-east-1"])
        >>> track_funnel_step("checkout", "completed", tags=["region:us-east-1"])
    """
    metric_name = f"app.funnel.{funnel_name}.{step_name}"
    increment_counter(metric_name, tags=tags)


def flush() -> None:
    """
    Flush pending metrics to Datadog.

    This is useful when you want to ensure all metrics are sent before
    the application exits (e.g., in Lambda handlers).
    """
    client = _get_statsd_client()
    if client is None:
        return

    try:
        client.flush()
    except Exception as e:
        logger.warning(f"Failed to flush metrics: {e}")
