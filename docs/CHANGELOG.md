# Changelog

## [Feat] — `mask_policy` casa por sufixo de chave, camelCase e kebab, e ganha `Mask.NAME` (CNT-3524)

### Contexto

A comparação era exata depois de `lower()`. Vazavam `documentNumber`, `customerDocument`, `pixKey`, `taxId`, `sender_document`, `recipient_document`, `account_number`, `account_branch`, `holder_name`, `user_email` e parentes. Além disso, bytes sob chave sensível saíam com sobra de dígitos: `str(b"12345678901")` é `"b'12345678901'"`, e a máscara de 4 caracteres deixava `**********901'`.

### BREAKING

- Quem usa `CONTA_DIGITAL_MASK_POLICY` passa a ter mascarados todos os campos que terminam em `_document`, `_cpf`, `_cnpj` e `_email`, além de `tax_id`, `account_number`, `account_branch`, `pix_key`, `addressing_key` e os nomes `account_name`, `holder_name`, `trade_name`, `user_name` (cada um também como sufixo, ex.: `sender_account_number`). Quem lia esses campos em claro no Datadog deixa de ver.
- A chave é normalizada antes da busca (camelCase e kebab viram snake, depois lower), inclusive no `DEFAULT_MASK_POLICY`: `documentNumber` agora casa `document_number` e `Pix-Key` casa `pix_key`. A `DEFAULT_MASK_POLICY` em si não mudou.
- `bytes` e `bytearray` sob chave sensível são decodificados (UTF-8, `errors="replace"`) antes de mascarar. Antes sobravam o prefixo `b'` e o apóstrofo final.

### Mudanças

#### `logging.py`

- Sintaxe de sufixo: chave da policy com `*` na frente, `{"*_document": Mask.LAST4}`. Casa qualquer chave que termine em `_document`; a chave `document` sozinha não casa e continua sendo declarada à parte (já está no default). `*document` sem o sublinhado vale como `*_document`. Sufixo vazio (`"*"`, `"*_"`) levanta `ValueError` no startup.
- Ordem de resolução: chave exata, depois o sufixo mais longo, depois nada (valor intocado).
- `Mask.NAME`: iniciais de cada palavra (`"Joao da Silva"` vira `"J. d. S."`, `"Maria"` vira `"M."`, vazio continua vazio). Aceita o nome em qualquer caixa como as outras estratégias.
- A policy não tem `*_name`, nem `key` ou `name` sozinhos: `event_name` e `file_name` são atributos de negócio, `key` é chave de cache e de S3 e `name` é atributo reservado do `LogRecord`. Cada nome sensível é listado.
- `mask_document` aceita `bytes`.

## [Fix] — Objetos e strings JSON dentro de `extra` passam pelo mascaramento (CNT-3942)

### Contexto

Dois defeitos medidos com `extra={"input": dto}`: o `JSONFormatter` levantava `TypeError` (`json.dumps` sem `default`) e a linha sumia do stdout, enquanto o caminho OTLP fazia `str(obj)` e mandava o dado em claro. E `extra={"props": {"event": json.dumps(event)}}`, `model_dump_json()` e `response.text` chegavam inteiros, porque o `RedactionFilter` só abria dict, lista e tupla.

### BREAKING

- Objetos pydantic v2 (`model_dump`) e dataclasses em `extra` saem como dict mascarado, não mais como `str(obj)`. Quem consultava no Datadog o atributo `input` como texto passa a encontrar `input.<campo>`.
- String de até 64 KB que começa com `{` ou `[` e é JSON válido é aberta, mascarada e serializada de novo. Só é reescrita se algo foi mascarado; sem dado sensível, sai byte a byte igual. Acima de 64 KB passa direto, sem mascarar.
- Conjuntos (`set`, `frozenset`) agora são percorridos.

### Mudanças

#### `logging.py`

- `RedactionFilter` converte pydantic v2 (detectado por `hasattr(v, "model_dump")`, sem importar pydantic) com `model_dump(mode="json")` e dataclass com `asdict`, e segue na recursão normal. Se a conversão falhar, o valor vira `*****`.
- Profundidade máxima de 32 níveis; o excedente vira `*****`. JSON que estoura a pilha do parser também vira `*****`, nunca sai em claro.
- `JSONFormatter` usa `json.dumps(..., default=str)`: `UUID`, `Decimal`, `datetime` e objetos arbitrários não derrubam mais a linha.
- O filtro continua rodando uma vez por record (idempotente), então o handler OTLP recebe o valor já mascarado.

## [Fix] — Texto da exceção fora do log e do span, e env numérica inválida sem repetir o valor

### Contexto

O texto de uma exceção costuma carregar o dado que a levantou. Confirmado por execução com `ValueError("secret-value-123")` dentro de uma função com `@trace`: o marcador saía em `status.description`, em dois eventos `exception` do span (um da lib e outro do SDK, que também registra sozinho na saída do `with`) e no log JSON. Já `float(os.getenv(...))` com valor inválido levantava `ValueError` repetindo o valor da variável no traceback.

### BREAKING

- Por padrão, a mensagem da exceção não sai mais em log nem em span. O span fica com status `ERROR`, descrição só com o nome da classe e um evento `exception` com `exception.type`, sem `exception.message` nem `exception.stacktrace`. O log traz tipo e frames (arquivo, linha, função), sem a mensagem e sem a linha de código. Vale para `trace`, `instrument_lambda_handler`, `instrument_chalice` (HTTP) e `trace_sqs_message`; para qualquer `logger.exception` que passe pelo handler da lib (stdout e OTLP); para o log `app.log` do próprio Chalice, que captura a exceção da view e responde 500 sem passar pelo `except` do middleware (o span agora fecha como `ERROR`); e para qualquer span do processo, inclusive filho aberto com `get_tracer` e o da auto-instrumentação do FastAPI, por um `SpanProcessor` instalado por `init_telemetry` antes dos exporters.
- `OTEL_RECORD_EXCEPTION_MESSAGE=true` restaura o comportamento anterior (mensagem e stacktrace completos, status no formato `Tipo: mensagem`). Diferença que sobra: o evento `exception` sai uma vez, não duas. Atenção: o `RedactionFilter` mascara por nome de campo, não varre texto livre, então com o opt-in ligado a mensagem sai como está.
- Quem consulta `status.description` ou `exception.message` em monitor ou dashboard precisa ligar o opt-in ou migrar para `exception.type`.
- `OTEL_EXPORTER_OTLP_TIMEOUT`, `OTEL_TRACES_SAMPLER_ARG` e `DD_DOGSTATSD_PORT` passam a ser validados no startup: timeout finito e maior que 0 (antes aceitava `0`, negativo, `nan` e `inf`), amostragem entre 0.0 e 1.0 (antes `nan` passava só pelo erro do `__post_init__`), porta de 1 a 65535.

### Limites conhecidos

- Exceção relançada ao runtime da Lambda: o runtime registra o traceback, com a mensagem, no CloudWatch por conta própria. Isso está fora do alcance da lib.
- O sanitizador de span limpa status no formato `Tipo: mensagem` e os campos `exception.message` e `exception.stacktrace`. Status escrito à mão pelo serviço, como `str(e)` sem o prefixo do tipo, não é reconhecido e passa como está.

### Mudanças

#### `_excecao.py` (novo)

- Ponto único do tratamento de exceção: `mark_span_error` e `safe_exception_text`, usados pelos pontos de instrumentação.
- `ExceptionSanitizingSpanProcessor`: remove `exception.message` e `exception.stacktrace` dos eventos e a mensagem do status (`Tipo: mensagem` vira `Tipo`) de qualquer span ao encerrar. Descrição escrita à mão que não tenha o formato `Tipo: ` fica como está. Altera `_events` e `_status` do span, campos privados do SDK; há teste contra o SDK real.

#### `aws_lambda.py`, `chalice.py`, `propagation.py`

- `string_attribute` lê o texto de um atributo de mensagem e devolve `None` quando o atributo é Binary, não traz o campo ou não é um dict. Antes, `traceparent` Binary em SQS ou SNS levantava `KeyError` no decorator da Lambda, o handler não rodava e o lote voltava até a DLQ. Sem carrier W3C, o contexto atual é mantido.

#### `tracer.py`

- O log `Telemetry initialized` mostra os endpoints OTLP só com scheme e host.

#### `chalice.py`

- Filtro no handler de `app.log`: marca o span como `ERROR` (só o tipo) e tira a mensagem do traceback. O middleware não sobrescreve mais com `OK` uma resposta 5xx.

#### `tracer.py`, `aws_lambda.py`, `chalice.py`

- Os spans nascem com `record_exception=False` e `set_status_on_exception=False`. Só remover as linhas manuais não bastava: o `start_as_current_span` registra a exceção sozinho na saída do `with`. Efeito colateral corrigido: o evento `exception` saía duplicado.

#### `logging.py`

- `ExceptionMessageFilter` novo nos handlers de stdout e OTLP: descarta `exc_info` e deixa tipo e frames em `exc_text` e nos atributos `exception.type` e `exception.stacktrace`.
- `JSONFormatter` usa a mesma forma segura quando usado sozinho.
- Os avisos da própria lib (exporter OTLP de logs, flush, DogStatsD, auto-instrumentação) registram só o tipo da exceção. O log de inicialização do exporter OTLP mostra só scheme e host do endpoint, sem usuário nem query string.
- Os atributos internos `_otel_redacted` e `_otel_exc_sanitized` deixam de ir para o OTLP.

#### `config.py`

- `_read_env_number` lê a env numérica e, se inválida, levanta `ValueError` citando só o nome da variável e a regra. O parse fica fora do `except`, então `__cause__` e `__context__` também não carregam o valor.
- O aviso de `OTEL_LOG_FORMAT` não reconhecido deixa de ecoar o valor.
- `DD_DOGSTATSD_PORT` só é validada com `DD_DOGSTATSD_ENABLED=true`.

## [Fix] — Loop de flush em Lambda, máscara de Pix aplicada duas vezes e três arestas de configuração

### Contexto

Achados de uma revisão adversarial desta PR, todos reproduzidos por execução antes do fix.

### Mudanças

#### `logging.py`

- `ExporterLoopGuardFilter` novo no handler OTLP: log dos próprios `opentelemetry`, `urllib3` e `requests` não é exportado. Com o handler OTLP no root logger, o aviso do exporter (backend fora, retry) virava um log novo para exportar, que gerava outro aviso — o `flush_telemetry` do `finally` nunca esvaziava a fila. Medido com o coletor recusando conexão: a primeira invocação passava de 110 segundos; com o guard, 5,3s e 2,9s. O log continua saindo no stdout, que não realimenta nada.
- `RedactionFilter` virou idempotente. O mesmo record passa pelo handler de stdout e pelo OTLP; a segunda passada remascarava o valor já mascarado e a chave Pix perdia os 4 dígitos finais (`*******8901` no stdout, `*****` no Datadog). O marcador interno entra em `_STANDARD_LOGRECORD_ATTRS`, então não vira campo no JSON nem atributo no OTLP.
- `mask_policy` aceita o nome da estratégia em qualquer caixa (`"LAST4"` e `"last4"`). Valor inexistente continua levantando `ValueError` no startup.

#### `tracer.py`

- `flush_telemetry(timeout=...)` passa a ser orçamento total da invocação, dividido entre logs e traces, em vez de valor por sinal.
- Limite medido e documentado na docstring: com o coletor inalcançável por rede (pacote descartado, sem RST), o `force_flush` do SDK só retorna quando o export em curso termina, então o piso de cada sinal é `OTEL_EXPORTER_OTLP_TIMEOUT` vezes as tentativas, e não o valor pedido no flush.

#### `config.py`

- `OTEL_EXPORTER_OTLP_TIMEOUT` aceita fração de segundo (`1.5` derrubava o startup com `ValueError`).
- `OTEL_LOG_FORMAT` com valor não reconhecido cai no default do entrypoint e emite warning, em vez de desligar o JSON em silêncio. `json` liga; `text`, `plain` e `console` desligam.

### Verificação

- 248 testes (eram 247), cobertura 90,08%.
- Flush com o coletor recusando conexão: 5,3s e 2,9s em duas invocações seguidas do mesmo handler.

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
