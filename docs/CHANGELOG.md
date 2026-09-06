# Changelog

## [CNT-3524] — Chaves de PII no RedactionFilter, máscara parcial e `mask_document` público

### Contexto

O ticket CNT-3524 reportava que a recursão do `RedactionFilter` não alcançava chaves aninhadas dentro de `props`. O diagnóstico está incorreto: a recursão sobre `dict`/`list`/`tuple` já funcionava. O caso real (`account_document` em claro dentro de `props.header`) ocorria porque chaves de dado pessoal nunca fizeram parte de `DEFAULT_SENSITIVE_KEYS` — a lista só tinha credencial. O que mascarava o documento no topo era a função `_mask_document` duplicada em cada serviço, que não roda sobre valores aninhados.

### Mudanças

#### `logging.py`

- Nova constante `DEFAULT_PARTIAL_MASK_KEYS`, separada de `DEFAULT_SENSITIVE_KEYS`: chaves de dado pessoal (`document`, `document_number`, `account_document`, `cpf`, `cnpj`, `email`, `phone`, `pix_key`, `addressing_key`) com mascaramento PARCIAL — últimos 4 caracteres preservados, que a sustentação usa para localizar cliente (ver CNT-3618, no mesmo épico)
- `DEFAULT_SENSITIVE_KEYS` (credencial) segue com mascaramento TOTAL
- `RedactionFilter` ganha parâmetro `partial_mask_keys` e aplica a máscara certa por lista
- Chave de credencial agora mascara qualquer tipo de valor (`int`, `dict`, `bytes`) — antes só `str`, e CPF/CNPJ como `int` passavam em claro
- Chave de PII com valor não-`str` cai em `_REDACTED` total (não dá pra mascarar parcialmente o que não é texto)
- `name` e `key` genéricos, sugeridos pelo ticket, NÃO foram incluídos: mascarariam nome de serviço/módulo e chave de dicionário arbitrária, produzindo log ilegível

#### `__init__.py`

- `mask_document` exportado publicamente — extração da `_mask_document` que vive duplicada em credit-api, payroll-api e transactional-facade (e ausente no account-api); é a peça que a migração dos serviços vai consumir

#### Testes

- 4 novos casos em `test_logging.py`: documento aninhado em `props`, valor não-`str` em chave sensível, máscara parcial preservando últimos dígitos e `mask_document` público tolerante a `None`/`""`
- Os 4 falhavam antes do fix, confirmando o diagnóstico corrigido

---

## [Fase 1] — Endpoints por sinal e OTLP log export

### Contexto

A lib usava um único `OTEL_EXPORTER_OTLP_ENDPOINT` para todos os sinais, passado diretamente ao `OTLPSpanExporter`. Isso criou dois problemas no cenário de AWS App Runner + Datadog direto:

1. **Endpoint incorreto**: o SDK usa o valor exatamente como fornecido (sem append de `/v1/traces`), então `https://api.datadoghq.com` resultava em POST para a raiz — que retorna a HTML do web UI do Datadog (404)
2. **Sem suporte a endpoints por sinal**: o Datadog tem URLs diferentes para logs (`otlp.datadoghq.com/v1/logs`), métricas (`otlp.datadoghq.com/v1/metrics`) e traces (endpoint região-específico, Preview)

### Mudanças

#### `config.py`

- Adicionados 4 campos ao dataclass: `otlp_traces_endpoint`, `otlp_metrics_endpoint`, `otlp_logs_endpoint`, `traces_enabled`
- Lógica de resolução por sinal: `OTEL_EXPORTER_OTLP_{SIGNAL}_ENDPOINT` → `OTEL_EXPORTER_OTLP_ENDPOINT` → `None`
- Nova env `OTEL_TRACES_ENABLED=false` para desabilitar traces explicitamente
- Warning emitido quando nenhum endpoint de traces está configurado
- Campo `otlp_endpoint` mantido para backwards compatibility

#### `tracer.py`

- `OTLPSpanExporter` agora é criado condicionalmente (`if config.traces_enabled`)
- Quando desabilitado, `TracerProvider` ainda é criado — trace context e correlação de logs continuam funcionando
- Endpoint do exporter passou de `config.otlp_endpoint` para `config.otlp_traces_endpoint`
- `init_telemetry` chama `init_otlp_log_export` automaticamente ao final
- `shutdown_telemetry` chama `shutdown_log_export` automaticamente

#### `logging.py`

- Adicionado `init_otlp_log_export(config, resource)`: inicializa `OTLPLogExporter` como handler adicional ao stdout, ativado por `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`
- Adicionado `shutdown_log_export(timeout)`: flush e shutdown do `LoggerProvider`
- Singleton `_logger_provider` para gerenciamento de ciclo de vida
- Falha silenciosa com warning se SDK não suportar (try/except)

#### Testes

- 8 novos casos em `test_config.py`: resolução de endpoints por sinal, `traces_enabled`, warnings
- 2 novos casos em `test_tracer.py`: exporter não criado quando desabilitado, endpoint correto sendo usado
- 4 testes pré-existentes corrigidos: patch target errado (`trace` local ao invés de `trace_api`)
- `conftest.py`: reset de `_logger_provider` no fixture `reset_telemetry`

### Novas variáveis de ambiente

| Variável | Descrição | Status |
|---|---|---|
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | Endpoint específico para traces | Aguarda aprovação Datadog CSM |
| `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` | Endpoint específico para logs | GA — disponível agora |
| `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` | Endpoint específico para métricas | Armazenado, não wired ainda (Phase 2) |
| `OTEL_TRACES_ENABLED` | Desabilitar traces explicitamente | Opcional |

### Variáveis removidas / depreciadas

| Variável | Status | Motivo |
|---|---|---|
| `DD_SITE` | Removida dos projetos | Injetada como `DD-SITE` header que o Datadog não usa no OTLP |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Mantida como fallback | Substituída pelos signal-specific para novos deployments |
| `DD_DOGSTATSD_ENABLED/HOST/PORT` | Não configurar em App Runner | DogStatsD requer Agent local — indisponível sem sidecar |

### Backwards compatibility

| Cenário | Comportamento |
|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` configurado | Sem mudança — usado como fallback por todos os sinais |
| Nenhuma env OTLP configurada | Traces desabilitados (antes: tentava `localhost:4318` e falhava silenciosamente) |
| DogStatsD metrics | Sem mudança |

---

## Fase 2 — Roadmap

### Traces diretos ao Datadog

**Bloqueio:** Endpoint em Preview, requer aprovação do Customer Success Manager do Datadog.

**O que fazer:** Solicitar acesso ao CSM. Quando aprovado:
1. Configurar `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=<endpoint-fornecido>`
2. Configurar `OTEL_EXPORTER_OTLP_HEADERS=dd-otlp-source=<source-id-fornecido>`
3. Nenhuma mudança de código necessária

### Métricas OTLP

**Bloqueio:** Implementação na lib. O endpoint Datadog (`otlp.datadoghq.com/v1/metrics`) já está GA.

**Por que foi adiado:** A API pública de métricas atual usa DogStatsD (`increment_counter`, `gauge`, `histogram`). Migrar para OTLP exige `MeterProvider` + `OTLPMetricExporter`, que tem API incompatível com os call sites existentes.

**Dependências:** Nenhuma nova — `OTLPMetricExporter` já está incluído no `opentelemetry-exporter-otlp-proto-http` que é dependência core.

**Arquivos que mudarão:**
- `config.py`: `otlp_metrics_endpoint` já existe, só precisa ser wired
- `metrics.py`: adicionar `MeterProvider` + `OTLPMetricExporter` como caminho paralelo ou substituto do DogStatsD
- Serviços consumidores: migrar call sites se a API pública mudar

**Nova env:**
```bash
OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=https://otlp.datadoghq.com/v1/metrics
```
