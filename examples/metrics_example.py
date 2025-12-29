"""
Exemplo de uso de métricas customizadas com DogStatsD.

Este exemplo demonstra como usar diferentes tipos de métricas:
- COUNT: Contadores incrementais
- GAUGE: Valores instantâneos
- HISTOGRAM: Distribuições de valores
- DISTRIBUTION: Distribuições globais

Execute:
    export OTEL_SERVICE_NAME=metrics-example
    export OTEL_ENVIRONMENT=development
    export OTEL_SERVICE_VERSION=1.0.0
    export DD_DOGSTATSD_ENABLED=true
    python examples/metrics_example.py
"""

import time

from otel_observability.metrics import (
    flush,
    increment_counter,
    record_distribution,
    record_histogram,
    set_gauge,
)


def example_count_metrics():
    """Exemplo de métricas COUNT (contadores)."""
    print("=== Exemplo: COUNT Metrics ===")

    # Contar requisições
    increment_counter("app.requests.total")
    increment_counter("app.requests.total", tags=["method:GET", "endpoint:/api/users"])

    # Contar erros
    increment_counter("app.errors", tags=["error_type:validation"])
    increment_counter("app.errors", tags=["error_type:database"])

    # Contar com valor customizado
    increment_counter("app.items.processed", value=10, tags=["batch:orders"])

    print("✓ Métricas COUNT enviadas")


def example_gauge_metrics():
    """Exemplo de métricas GAUGE (valores instantâneos)."""
    print("\n=== Exemplo: GAUGE Metrics ===")

    # Usuários ativos
    set_gauge("app.active_users", 150, tags=["region:us-east-1"])

    # Tamanho de fila
    set_gauge("app.queue.size", 42, tags=["queue:orders"])

    # Uso de memória customizado
    set_gauge("app.memory.usage", 512, tags=["component:cache"])

    print("✓ Métricas GAUGE enviadas")


def example_histogram_metrics():
    """Exemplo de métricas HISTOGRAM (distribuições)."""
    print("\n=== Exemplo: HISTOGRAM Metrics ===")

    # Simular latência de requisições
    latencies = [0.05, 0.12, 0.08, 0.15, 0.10, 0.20, 0.09, 0.11]

    for latency in latencies:
        record_histogram(
            "app.request.latency",
            latency,
            tags=["endpoint:/api/users", "method:GET"],
        )

    # Tamanho de resposta
    response_sizes = [1024, 2048, 512, 4096, 1024, 8192]

    for size in response_sizes:
        record_histogram(
            "app.response.size",
            size,
            tags=["endpoint:/api/users"],
        )

    print("✓ Métricas HISTOGRAM enviadas")


def example_distribution_metrics():
    """Exemplo de métricas DISTRIBUTION (distribuições globais)."""
    print("\n=== Exemplo: DISTRIBUTION Metrics ===")

    # Latência global entre datacenters
    global_latencies = [0.10, 0.15, 0.12, 0.18, 0.14]

    for latency in global_latencies:
        record_distribution(
            "app.request.latency.global",
            latency,
            tags=["region:us-east-1"],
        )

    print("✓ Métricas DISTRIBUTION enviadas")


def example_with_tags():
    """Exemplo de métricas com tags para segmentação."""
    print("\n=== Exemplo: Métricas com Tags ===")

    # Segmentar por região
    increment_counter(
        "app.requests",
        tags=["region:us-east-1", "env:production"],
    )
    increment_counter(
        "app.requests",
        tags=["region:us-west-2", "env:production"],
    )

    # Segmentar por tipo de pagamento
    increment_counter(
        "app.payments",
        tags=["payment_method:credit_card", "region:us-east-1"],
    )
    increment_counter(
        "app.payments",
        tags=["payment_method:paypal", "region:us-east-1"],
    )

    print("✓ Métricas com tags enviadas")
    print("  Tags automáticas aplicadas: env, service, version")


def example_error_handling():
    """Exemplo de métricas em tratamento de erros."""
    print("\n=== Exemplo: Métricas de Erro ===")

    try:
        # Simular operação que pode falhar
        simulate_operation()
        increment_counter("app.operations.success", tags=["operation:process"])
    except ValueError as e:
        increment_counter(
            "app.operations.error",
            tags=["operation:process", "error_type:validation"],
        )
        print(f"  Erro capturado: {e}")
    except Exception as e:
        increment_counter(
            "app.operations.error",
            tags=["operation:process", "error_type:unknown"],
        )
        print(f"  Erro desconhecido: {e}")


def simulate_operation():
    """Simula uma operação que pode falhar."""
    import random

    if random.random() < 0.3:  # 30% de chance de erro
        raise ValueError("Validation error")
    return {"status": "success"}


def example_periodic_metrics():
    """Exemplo de métricas atualizadas periodicamente."""
    print("\n=== Exemplo: Métricas Periódicas ===")

    # Simular atualização periódica de métricas
    for i in range(5):
        # Atualizar gauge periodicamente
        active_users = 100 + (i * 10)
        set_gauge("app.active_users", active_users, tags=["region:us-east-1"])

        # Contar eventos
        increment_counter("app.events.processed", tags=["batch:periodic"])

        time.sleep(0.5)

    print("✓ Métricas periódicas enviadas")


def main():
    """Executar todos os exemplos."""
    print("🚀 Exemplos de Métricas Customizadas com DogStatsD\n")

    try:
        example_count_metrics()
        example_gauge_metrics()
        example_histogram_metrics()
        example_distribution_metrics()
        example_with_tags()
        example_error_handling()
        example_periodic_metrics()

        # Flush para garantir que todas as métricas sejam enviadas
        print("\n=== Flush de Métricas ===")
        flush()
        print("✓ Métricas enviadas para Datadog")

        print("\n✅ Todos os exemplos executados com sucesso!")
        print("\n💡 Dica: Verifique as métricas no Datadog:")
        print("   1. Acesse Metrics → Explorer")
        print("   2. Procure por: app.requests, app.active_users, app.request.latency")
        print("   3. Filtre por tags: env, service, version (aplicadas automaticamente)")

    except Exception as e:
        print(f"\n❌ Erro ao executar exemplos: {e}")
        print("\n💡 Verifique:")
        print("   1. Se o Datadog Agent está rodando (localhost:8125)")
        print("   2. Se DD_DOGSTATSD_ENABLED=true")
        print(
            "   3. Se a biblioteca datadog está instalada: pip install otel-observability[metrics]"
        )


if __name__ == "__main__":
    main()
