# Testes - otel-observability

Este diretório contém os testes da biblioteca `otel-observability`.

## Estrutura

```
tests/
├── conftest.py              # Fixtures compartilhadas
├── unit/                   # Testes unitários
│   ├── test_config.py
│   ├── test_logging.py
│   └── test_tracer.py
└── integration/           # Testes de integração
    └── test_logging_integration.py
```

## Executando Testes

### Todos os testes

```bash
pytest
```

### Apenas testes unitários

```bash
pytest tests/unit/
```

### Apenas testes de integração

```bash
pytest tests/integration/
```

### Com cobertura

```bash
pytest --cov=src/otel_observability --cov-report=html
```

### Testes específicos

```bash
# Por arquivo
pytest tests/unit/test_logging.py

# Por função
pytest tests/unit/test_logging.py::TestLogContext::test_set_log_context

# Por marcador
pytest -m unit
pytest -m integration
```

## Marcadores

- `@pytest.mark.unit` - Testes unitários
- `@pytest.mark.integration` - Testes de integração
- `@pytest.mark.slow` - Testes lentos

## Fixtures Disponíveis

- `mock_env_vars` - Mocka variáveis de ambiente
- `telemetry_config` - Configuração de telemetria para testes
- `reset_telemetry` - Reseta estado de telemetria entre testes
- `reset_log_context` - Limpa contexto de log entre testes
- `mock_otlp_exporter` - Mock do OTLP exporter
- `mock_tracer_provider` - Mock do TracerProvider

## Escrevendo Novos Testes

### Exemplo de teste unitário

```python
import pytest
from otel_observability.logging import set_log_context, get_log_context

@pytest.mark.unit
class TestMyFeature:
    def test_my_function(self, reset_log_context):
        set_log_context(key="value")
        context = get_log_context()
        assert context["key"] == "value"
```

### Exemplo de teste de integração

```python
import pytest

@pytest.mark.integration
class TestMyIntegration:
    def test_end_to_end(self, reset_telemetry):
        # Teste completo
        pass
```

## Boas Práticas

1. Use fixtures para setup/teardown
2. Isole testes (cada teste deve ser independente)
3. Use mocks para dependências externas
4. Teste casos de sucesso e erro
5. Mantenha testes rápidos e determinísticos
