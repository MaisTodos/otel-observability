# Changelog

## [Doc + endpoint] — Endpoint genérico completa o path por sinal, gate de cobertura ativo e documentação consolidada

### Contexto

Dois achados que apareceram depois da entrada abaixo, na revisão da própria PR: a resolução de endpoint OTLP quebrava o cenário de Agent sidecar, e a documentação do repo descrevia comportamento que o código não tem.

### BREAKING

- `OTEL_EXPORTER_OTLP_ENDPOINT` (genérico) passa a receber o path do sinal. Antes o valor era repassado literalmente aos exporters, então `http://localhost:4318` fazia traces **e** logs postarem na raiz — exatamente o que a doc antiga recomendava para Agent sidecar, e que nunca funcionou. Agora o genérico resolve para `/v1/traces`, `/v1/metrics` e `/v1/logs`; a env específica por sinal (`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` etc.) continua sendo usada literalmente, sem sufixo. Quem já apontava o genérico para uma URL com path completo deve migrar para a env específica.

### Mudanças

#### `config.py`

- `_resolve_signal_endpoint` centraliza a precedência específico > genérico + path > `None`.

#### `pyproject.toml`

- `--cov=otel_observability` entra no `addopts`. O `--cov-fail-under=80` já existia, mas sem o `--cov=` o gate nunca era aplicado localmente: `make test` passava com qualquer cobertura. Cobertura real medida: 89,87%.

#### Documentação

- 18 arquivos em `docs/` viram 5 + `README.md` + `CLAUDE.md`. Uma auditoria contra o código encontrou ~44 afirmações erradas, 10 delas do tipo que faz alguém configurar produção errado — a mais grave dizia que a lib detecta Lambda e envia para `localhost:4318` sozinha (não detecta; sem env, traces ficam desabilitados).
- Estrutura nova: `CONFIGURATION.md` (env vars, precedência, campos mortos, cenários por plataforma), `USAGE.md` (a API que os serviços chamam, incluindo `RequestLoggingMiddleware` e redação de PII), `ENTRYPOINTS.md` (Lambda e Chalice), `TROUBLESHOOTING.md`, `CHANGELOG.md`.
- `@trace_sqs_message` é decorator nu. Estava documentado com parênteses em 6 lugares, inclusive nas docstrings de `chalice.py` e `__init__.py` — com parênteses levanta `TypeError`.
- Instalação é `git+ssh`, não PyPI. A lib não está publicada.
- A análise de arquitetura de fevereiro saiu do repo e foi arquivada fora dele; era registro histórico, não referência de uso.

## [CNT-3620] — Flush em Lambda/Chalice, teto de export, propagação e `OTEL_LOG_FORMAT` funcionando

### Contexto

Esta PR acumulou 13 commits desde a entrada abaixo. O arco de PII/logging tem entrada própria (`CNT-3524`, com `mask_document` público e `RedactionFilter` por `mask_policy`) e não se repete aqui. O restante — telemetria que se perdia sem erro e sem log, e configuração que existia mas não funcionava — está consolidado abaixo, agrupado pelo que muda para quem consome.

### BREAKING

- `OTEL_LOG_FORMAT` passa a funcionar de verdade. Era código morto: a env era copiada e nunca lida, e o único caminho pro JSON era o parâmetro explícito. Precedência agora: parâmetro > `OTEL_LOG_FORMAT` > default do entrypoint (`False` no FastAPI, `True` em Lambda/Chalice). Serviço que já tinha a env setada **muda de comportamento** no upgrade — passa a emitir JSON de verdade.
- Métricas param de sair com a tag duplicada (tag unificada removida das 4 funções públicas). Séries antigas no Datadog não são reescritas: dashboards que agrupam por `env`/`service`/`version` mostram descontinuidade no dia do deploy. É esperado, não é regressão.

### Mudanças

#### `config.py`

- `TelemetryConfig` ganha `log_format` e `export_timeout`, ambos com default e no fim do dataclass — quem constrói config própria não quebra; quem construía posicionalmente com os 16 campos originais deve conferir.
- `OTEL_EXPORTER_OTLP_TIMEOUT` (default 3s, nome da spec OTel) passa a limitar o export. Antes o timeout efetivo era 10s por sinal, com retry interno — 20s por invocação Lambda com o coletor fora.

#### `tracer.py`

- Sampler envolto em `ParentBased`: decisão de amostragem propagada pelo chamador é respeitada. Serviço com `sample_rate` baixo passa a gravar spans que antes descartava.
- `get_tracer()` sem argumento resolve o `__name__` do módulo chamador.
- `telemetry.sdk.version` passa a reportar a versão real do `pyproject.toml` (`__version__` via `importlib.metadata`), não mais o valor hardcoded desde o primeiro commit.

#### `propagation.py`

- `baggage` sobrevive ao round-trip via SQS/SNS.
- `extract` compõe sobre o contexto atual em vez de substituir: carrier não-vazio sem `traceparent` (produtor não-instrumentado) preserva o span pai e o baggage.

#### `aws_lambda.py` / `chalice.py`

- `redact_keys` exposto nos dois `instrument_*` (o FastAPI já repassava desde o CNT-2832; Lambda/Chalice herdavam só as chaves de credencial).
- Ordem de init corrigida: `configure_logging` roda antes de `init_telemetry` — antes o `handlers.clear()` removia o handler OTLP recém-instalado e, com `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` setado, nenhum log saía via OTLP.
- `flush_telemetry` ao fim de cada invocação (handler no Lambda; middleware HTTP e handler SQS no Chalice) em vez de `shutdown_telemetry` — em container warm, o shutdown matava o `BatchSpanProcessor` e toda telemetria da 2ª invocação em diante se perdia.

#### `logging.py`

- `JSONFormatter` reutiliza `_STANDARD_LOGRECORD_ATTRS` — elimina a segunda lista de atributos, que não continha `taskName` (campo do Python 3.12+) e o fazia vazar como extra em todo log.

#### `fastapi.py`

- Access log filtra por path (`parse_excluded_urls`), não por substring da linha inteira. Serviço que dependia, sem saber, da supressão excedente vai ver mais access log.

#### CI

- Lint usa `uv` em vez de `pip` solto, pra casar com o lock.
- `validate-release-pr.yml` exige que o título da PR bata com a versão do `pyproject.toml`. A partir daqui, release PR precisa bumpar o pyproject antes de abrir; mudança local de versão exige `uv sync` (a metadata instalada fica congelada).

---

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
