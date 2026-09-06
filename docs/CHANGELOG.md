# Changelog

## [CNT-3524] — `mask_policy`: mapa campo → estratégia, configurável pelo consumidor

### Contexto

O ticket CNT-3524 reportava que a recursão do `RedactionFilter` não alcançava chaves aninhadas dentro de `props`. O diagnóstico está incorreto: a recursão já funcionava — o caso real (`account_document` em claro dentro de `props.header`) era chaves de dado pessoal ausentes do mascaramento. O commit anterior desta PR desenhou a solução como duas listas paralelas (`DEFAULT_SENSITIVE_KEYS` e `DEFAULT_PARTIAL_MASK_KEYS`), com o tipo de máscara implícito em qual lista a chave caiu. A PR está em draft e nenhum serviço chegou a consumir, então o desenho foi substituído agora por um mapa campo → estratégia, antes do merge. Defeitos medidos das duas listas: e-mail mascarado com regra de documento vaza o domínio (`joao.silva@maistodos.com.br` → `*****m.br`); chave Pix não tem formato único (CPF, e-mail, telefone ou aleatória — tratamento como string uniforme já custou o bug de 2 anos e meio BANKS-4220/CNT-3280); e campo novo exigia PR + release + bump em 6 repos.

### BREAKING

- `DEFAULT_SENSITIVE_KEYS` e `DEFAULT_PARTIAL_MASK_KEYS` foram removidas da API pública
- `RedactionFilter` não aceita mais `sensitive_keys`/`partial_mask_keys` — aceita `mask_policy` (mapa campo → `Mask`); `redact_keys` segue funcionando (1 serviço usa) e passa a significar `Mask.FULL` via setdefault
- Campos genéricos (`email`, `phone`, `document_number`, `cpf`, `cnpj`, `document`) passam a ser mascarados em todos os consumidores sem opt-in

### Mudanças

#### `logging.py`

- Novo enum `Mask(str, Enum)`: `FULL` (credencial: nada aproveitável), `LAST4` (documento: sustentação localiza pelos 4 dígitos), `EMAIL` (`j***@maistodos.com.br` — domínio preservado), `PIX` (detecta o formato do valor e delega)
- `DEFAULT_MASK_POLICY` (PII universal) sempre entra; `CONTA_DIGITAL_MASK_POLICY` (`account_document`, `pix_key`, `addressing_key`) só entra se o serviço optar via `mask_policy` — o que o consumidor passa faz merge por cima e pode sobrescrever um default
- Estratégia inválida em `mask_policy` levanta `ValueError` no `__init__`, não em runtime
- `LAST4`/`EMAIL`/`PIX` aceitam qualquer tipo via `str(value)` — documento que chega como `int` vira máscara parcial (antes virava `*****` total)
- `_mask_last4` não devolve mais valores de até 4 caracteres em claro (`mask_document("1234")` devolvia `"1234"` em claro — vazamento corrigido de propósito); `mask_document` público segue intacto para a migração dos serviços
- `configure_logging` ganha `mask_policy` e repassa ao filtro

#### `fastapi.py` / `aws_lambda.py` / `chalice.py`

- Os três `instrument_*` ganham o parâmetro `mask_policy` e repassam ao `configure_logging`, documentado no docstring com o exemplo de merge

#### `__init__.py`

- Exportados: `Mask`, `DEFAULT_MASK_POLICY`, `CONTA_DIGITAL_MASK_POLICY`, `RedactionFilter`, `mask_document`

#### Testes

- 9 novos casos em `test_logging.py`: e-mail preserva domínio, Pix detecta os 4 formatos, documento `int` vira máscara parcial, consumidor estende e sobrescreve a policy, domínio de Conta Digital fora do default, estratégia inválida no startup, credencial mascara qualquer tipo e `redact_keys` não sobrescreve a policy
- Testes que usavam `sensitive_keys`/`partial_mask_keys` atualizados para `mask_policy`

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
