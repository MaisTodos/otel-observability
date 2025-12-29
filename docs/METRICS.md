# Métricas Customizadas com DogStatsD

Este documento é um guia completo e educativo sobre como usar métricas customizadas via DogStatsD na biblioteca `otel-observability`. Se você é novo em DogStatsD, comece pela Seção 1.

---

## Seção 1: Introdução ao DogStatsD

### O que é DogStatsD?

**DogStatsD** é um protocolo de métricas baseado em StatsD, estendido pelo Datadog. Ele permite que você envie métricas customizadas da sua aplicação para o Datadog de forma eficiente.

### Por que usar métricas customizadas?

Métricas, traces e logs servem a propósitos diferentes:

- **Traces**: Rastreamento detalhado de requisições individuais (ex: "esta requisição levou 150ms")
- **Logs**: Eventos textuais com contexto (ex: "erro ao processar pedido #123")
- **Métricas**: Agregações numéricas ao longo do tempo (ex: "média de 1000 requisições/segundo")

**Use métricas quando você precisa:**
- Medir taxas de conversão (funis)
- Monitorar KPIs de negócio (vendas, usuários ativos)
- Agregar dados de múltiplas requisições
- Criar alertas baseados em tendências

### Arquitetura: Como Funciona

```
┌─────────────────┐
│  Sua Aplicação  │
│  (Python)       │
└────────┬────────┘
         │
         │ increment_counter("app.checkout.start")
         │
         ▼
┌─────────────────┐
│ Cliente DogStatsD│
│ (UDP/TCP/HTTP)  │
└────────┬────────┘
         │
         │ localhost:8125
         │
         ▼
┌─────────────────┐      ┌─────────────────┐
│ Datadog Agent   │  OU   │ Lambda Extension│
│ (Container/EC2)│       │ (AWS Lambda)     │
└────────┬────────┘      └────────┬────────┘
         │                        │
         │                        │
         └────────────┬────────────┘
                      │
                      ▼
              ┌───────────────┐
              │ Datadog Cloud │
              │ (Dashboards)  │
              └───────────────┘
```

A aplicação envia métricas via protocolo DogStatsD para um agente local (Agent ou Extension), que agrega e envia para o Datadog Cloud.

---

## Seção 2: Conceitos Fundamentais

### Tipos de Métricas

DogStatsD suporta 4 tipos principais de métricas:

#### 1. COUNT - Contadores

**O que é:** Métricas incrementais que contam eventos.

**Quando usar:**
- Número de requisições
- Número de erros
- Eventos de negócio (checkouts iniciados, pagamentos processados)

**Exemplo:**
```python
from otel_observability.metrics import increment_counter

# Contar requisições
increment_counter("app.requests.total")

# Contar erros
increment_counter("app.errors", tags=["error_type:validation"])
```

**Características:**
- Valores são somados ao longo do tempo
- Útil para taxas (requisições por segundo)
- Não armazena valores negativos

#### 2. GAUGE - Medidores

**O que é:** Valores instantâneos em um ponto específico no tempo.

**Quando usar:**
- Número de usuários ativos
- Tamanho de filas
- Uso de memória/CPU customizado

**Exemplo:**
```python
from otel_observability.metrics import set_gauge

# Usuários ativos
set_gauge("app.active_users", 150)

# Tamanho de fila
set_gauge("app.queue.size", queue_length, tags=["queue:orders"])
```

**Características:**
- Substitui o valor anterior (não soma)
- Útil para valores que mudam ao longo do tempo
- Pode aumentar ou diminuir

#### 3. HISTOGRAM - Histogramas

**O que é:** Distribuição estatística de valores.

**Quando usar:**
- Latência de requisições
- Tamanho de respostas
- Tempo de processamento

**Exemplo:**
```python
from otel_observability.metrics import record_histogram

# Latência de requisição
record_histogram("app.request.latency", 0.125, tags=["endpoint:/api/users"])

# Tamanho de resposta
record_histogram("app.response.size", 1024, tags=["endpoint:/api/users"])
```

**Características:**
- Calcula média, mediana, percentis (p50, p95, p99)
- Agregado por host (cada host mantém sua própria distribuição)
- Útil para entender distribuição de valores

#### 4. DISTRIBUTION - Distribuições Globais

**O que é:** Histogramas globais que agregam entre todos os hosts.

**Quando usar:**
- Latência entre datacenters
- Métricas que precisam ser agregadas globalmente

**Exemplo:**
```python
from otel_observability.metrics import record_distribution

# Latência global
record_distribution("app.request.latency", 0.125, tags=["region:us-east-1"])
```

**Características:**
- Agregação global (não por host)
- Útil para métricas distribuídas
- Mais custoso que histogram (use com cuidado)

### Tags: Segmentação e Filtragem

**Tags** são pares chave-valor que permitem segmentar e filtrar métricas.

**Formato:** `chave:valor` (ex: `region:us-east-1`, `env:production`)

**Exemplo:**
```python
increment_counter(
    "app.checkout.start",
    tags=["region:us-east-1", "payment_method:credit_card"]
)
```

**Tags Automáticas:**

A biblioteca aplica automaticamente as seguintes tags a todas as métricas:
- `env:{OTEL_ENVIRONMENT}` - Ambiente (dev, staging, production)
- `service:{OTEL_SERVICE_NAME}` - Nome do serviço
- `version:{OTEL_SERVICE_VERSION}` - Versão do serviço

Você não precisa adicionar essas tags manualmente!

### Cardinalidade: Impacto nos Custos

**Cardinalidade** é o número de combinações únicas de tags.

**Exemplo de baixa cardinalidade:**
```python
# 3 regiões × 2 ambientes = 6 combinações
tags=["region:us-east-1", "env:production"]  # OK ✅
```

**Exemplo de alta cardinalidade:**
```python
# 1 milhão de usuários = 1 milhão de combinações
tags=["user_id:12345"]  # ❌ EVITAR!
```

**Por que importa?**

- Alta cardinalidade aumenta drasticamente os custos no Datadog
- Cada combinação única de tags cria uma nova série temporal
- Tags como `user_id`, `session_id`, `request_id` devem ser evitadas

**Solução:** Use logs para dados de alta cardinalidade, não métricas.

### Nomenclatura de Métricas

**Convenções recomendadas:**

1. **Use pontos para separar hierarquia:**
   - ✅ `app.checkout.start`
   - ❌ `app_checkout_start`

2. **Use minúsculas:**
   - ✅ `app.request.latency`
   - ❌ `App.Request.Latency`

3. **Seja descritivo:**
   - ✅ `app.payment.gateway.latency`
   - ❌ `pg_lat`

4. **Use prefixo do serviço:**
   - ✅ `payment.checkout.start`
   - ❌ `checkout.start`

---

## Seção 3: Como Funciona o Protocolo

### Protocolo StatsD Estendido

DogStatsD é baseado no protocolo StatsD, com extensões do Datadog.

### Comunicação: UDP vs TCP vs HTTP

**UDP (padrão):**
- Mais rápido e eficiente
- Sem garantia de entrega (fire-and-forget)
- Usado por padrão (localhost:8125)

**TCP:**
- Garantia de entrega
- Mais lento que UDP
- Use quando precisar de confiabilidade

**HTTP:**
- Usado principalmente em Lambda Extension
- Suporta batching
- Mais overhead que UDP/TCP

### Formato de Mensagens DogStatsD

**Formato básico:**
```
<nome_metrica>:<valor>|<tipo>|@<sample_rate>|#<tags>
```

**Exemplos:**
```
app.requests:1|c
app.latency:0.125|h|#region:us-east-1
app.users:150|g|#env:production
```

**Tipos:**
- `c` = COUNT
- `g` = GAUGE
- `h` = HISTOGRAM
- `d` = DISTRIBUTION

### Buffer e Batching

O cliente DogStatsD:
1. **Buffer local**: Acumula métricas em memória
2. **Batching**: Envia múltiplas métricas em um único pacote
3. **Flush automático**: Envia periodicamente (ex: a cada 10 segundos)

**Flush manual:**
```python
from otel_observability.metrics import flush

# Garantir que todas as métricas sejam enviadas
flush()
```

Útil em Lambda handlers antes de retornar.

### Timeout e Retry

- **Timeout padrão**: 5 segundos
- **Retry**: Não há retry automático (UDP é fire-and-forget)
- **Fallback**: Se o Agent/Extension não estiver disponível, métricas são descartadas silenciosamente (com warning em logs)

---

## Seção 4: Guia Passo a Passo

### Passo 1: Instalação

```bash
# Instalar com suporte a métricas
pip install otel-observability[metrics]

# Ou com Poetry
poetry add otel-observability[metrics]
```

### Passo 2: Configuração

**Variáveis de ambiente:**
```bash
# Obrigatórias
export OTEL_SERVICE_NAME=my-service
export OTEL_ENVIRONMENT=production
export OTEL_SERVICE_VERSION=1.0.0

# DogStatsD (opcionais, têm defaults)
export DD_DOGSTATSD_ENABLED=true  # default: true
export DD_DOGSTATSD_HOST=localhost  # default: localhost
export DD_DOGSTATSD_PORT=8125  # default: 8125
```

**Em Lambda:** A Extension já está configurada, apenas certifique-se de que `DD_DOGSTATSD_ENABLED=true`.

**Em Container:** Certifique-se de que o Datadog Agent está rodando e escutando em `localhost:8125`.

### Passo 3: Primeira Métrica

```python
from otel_observability.metrics import increment_counter

# Métrica simples
increment_counter("app.requests.total")
```

Execute sua aplicação e verifique no Datadog:
1. Acesse **Metrics → Explorer**
2. Procure por `app.requests.total`
3. Você verá a métrica aparecendo!

### Passo 4: Adicionando Tags

```python
from otel_observability.metrics import increment_counter

# Métrica com tags
increment_counter(
    "app.requests.total",
    tags=["region:us-east-1", "endpoint:/api/users"]
)
```

No Datadog, você pode filtrar por tags:
- `region:us-east-1`
- `endpoint:/api/users`
- `env:production` (automático)
- `service:my-service` (automático)

### Passo 5: Criando Funis de Conversão

```python
from otel_observability.metrics import track_funnel_step

# Funil de checkout
track_funnel_step("checkout", "start", tags=["region:us-east-1"])
track_funnel_step("checkout", "payment_success", tags=["region:us-east-1"])
track_funnel_step("checkout", "completed", tags=["region:us-east-1"])
```

Veja a Seção 6 para mais detalhes sobre funis.

### Passo 6: Visualizando no Datadog

1. **Metrics Explorer:**
   - Acesse **Metrics → Explorer**
   - Selecione sua métrica
   - Aplique filtros por tags
   - Visualize gráficos

2. **Dashboards:**
   - Crie dashboards customizados
   - Adicione widgets de métricas
   - Configure alertas

3. **Funis:**
   - Use fórmulas para calcular taxas de conversão
   - Veja Seção 6 para detalhes

---

## Seção 5: Exemplos Práticos

### Exemplo 1: Métricas de Negócio (Funil)

```python
from otel_observability.metrics import track_funnel_step

@app.post("/checkout")
async def checkout(order_data: dict):
    # Etapa 1: Checkout iniciado
    track_funnel_step("checkout", "start", tags=["region:us-east-1"])

    # Validar pedido
    if not validate_order(order_data):
        return {"error": "invalid_order"}

    # Etapa 2: Pagamento processado
    track_funnel_step("checkout", "payment_success", tags=["region:us-east-1"])

    # Criar pedido
    order = create_order(order_data)

    # Etapa 3: Pedido criado
    track_funnel_step("checkout", "completed", tags=["region:us-east-1"])

    return {"order_id": order.id}
```

### Exemplo 2: Métricas Técnicas (Latência)

```python
from otel_observability.metrics import record_histogram
import time

@app.get("/api/users/{user_id}")
async def get_user(user_id: int):
    start_time = time.time()

    try:
        user = await fetch_user(user_id)

        # Registrar latência
        latency = time.time() - start_time
        record_histogram(
            "app.request.latency",
            latency,
            tags=["endpoint:/api/users", "method:GET"]
        )

        return user
    except Exception as e:
        # Registrar latência mesmo em erro
        latency = time.time() - start_time
        record_histogram(
            "app.request.latency",
            latency,
            tags=["endpoint:/api/users", "method:GET", "status:error"]
        )
        raise
```

### Exemplo 3: Métricas de Erro

```python
from otel_observability.metrics import increment_counter

try:
    process_payment(amount)
except ValidationError as e:
    increment_counter(
        "app.errors",
        tags=["error_type:validation", "component:payment"]
    )
    raise
except PaymentGatewayError as e:
    increment_counter(
        "app.errors",
        tags=["error_type:gateway", "component:payment"]
    )
    raise
```

### Exemplo 4: Métricas de Recursos

```python
from otel_observability.metrics import set_gauge

# Atualizar tamanho de fila periodicamente
def update_queue_metrics():
    queue_length = get_queue_length("orders")
    set_gauge("app.queue.size", queue_length, tags=["queue:orders"])

    active_workers = get_active_worker_count()
    set_gauge("app.workers.active", active_workers)
```

---

## Seção 6: Funis de Conversão

### Conceito de Funis

Um **funil de conversão** é uma sequência de etapas que um usuário deve completar para alcançar um objetivo (ex: fazer uma compra).

**Exemplo de funil de checkout:**
1. Usuário inicia checkout
2. Usuário preenche informações de pagamento
3. Pagamento é processado com sucesso
4. Pedido é criado

### Implementação Passo a Passo

**1. Instrumentar cada etapa:**

```python
from otel_observability.metrics import track_funnel_step

# Etapa 1: Checkout iniciado
track_funnel_step("checkout", "start")

# Etapa 2: Pagamento processado
track_funnel_step("checkout", "payment_success")

# Etapa 3: Pedido criado
track_funnel_step("checkout", "completed")
```

**2. Adicionar tags para segmentação:**

```python
# Segmentar por região
track_funnel_step("checkout", "start", tags=["region:us-east-1"])
track_funnel_step("checkout", "payment_success", tags=["region:us-east-1"])
track_funnel_step("checkout", "completed", tags=["region:us-east-1"])
```

### Cálculo de Taxas de Conversão

No Datadog, use fórmulas para calcular taxas de conversão:

**Fórmula básica:**
```
(sum:app.funnel.checkout.completed{env:production} /
 sum:app.funnel.checkout.start{env:production}) * 100
```

Isso calcula: `(pedidos completados / checkouts iniciados) * 100`

**Exemplo no Dashboard:**

1. Crie um widget "Query Value"
2. Use a fórmula acima
3. Configure para mostrar como porcentagem

### Visualização no Datadog

**Método 1: Query Value (Taxa de Conversão)**
- Widget tipo "Query Value"
- Fórmula: `(sum:app.funnel.checkout.completed / sum:app.funnel.checkout.start) * 100`
- Formato: Porcentagem

**Método 2: Timeseries (Tendência)**
- Widget tipo "Timeseries"
- Múltiplas métricas: `app.funnel.checkout.start`, `app.funnel.checkout.completed`
- Visualize tendências ao longo do tempo

**Método 3: Funnel Analysis (RUM)**
- Se você usa RUM (frontend), use o widget nativo "Funnel Analysis"
- Para backend, use Query Value ou Timeseries

### Exemplo Completo: Funil de Checkout

```python
from fastapi import FastAPI
from otel_observability.fastapi import instrument_fastapi
from otel_observability.metrics import track_funnel_step

app = FastAPI()
instrument_fastapi(app)

@app.post("/checkout/start")
async def start_checkout(cart_id: str):
    """Etapa 1: Usuário inicia checkout."""
    track_funnel_step("checkout", "start", tags=["cart_id:" + cart_id])
    return {"status": "started"}

@app.post("/checkout/payment")
async def process_payment(payment_data: dict):
    """Etapa 2: Processar pagamento."""
    try:
        result = process_payment_gateway(payment_data)
        track_funnel_step("checkout", "payment_success", tags=["method:credit_card"])
        return result
    except Exception as e:
        # Não rastrear etapa de erro (ou criar etapa separada)
        raise

@app.post("/checkout/complete")
async def complete_checkout(order_data: dict):
    """Etapa 3: Pedido criado."""
    order = create_order(order_data)
    track_funnel_step("checkout", "completed", tags=["order_id:" + str(order.id)])
    return {"order_id": order.id}
```

**⚠️ Nota:** Evite usar `order_id` ou `cart_id` como tags (alta cardinalidade). Use apenas para logs se necessário.

---

## Seção 7: Boas Práticas

### Nomenclatura de Métricas

✅ **Bom:**
```python
app.checkout.start
app.payment.gateway.latency
app.errors.validation
```

❌ **Ruim:**
```python
checkout_start  # Sem prefixo
app_checkout_start  # Usa underscore
App.Checkout.Start  # Maiúsculas
```

### Cardinalidade de Tags

✅ **Baixa Cardinalidade (OK):**
```python
tags=["region:us-east-1", "env:production", "payment_method:credit_card"]
# 3 regiões × 2 ambientes × 3 métodos = 18 combinações
```

❌ **Alta Cardinalidade (EVITAR):**
```python
tags=["user_id:12345"]  # 1 milhão de usuários = 1 milhão de combinações
tags=["session_id:abc123"]  # Alta cardinalidade
tags=["request_id:xyz789"]  # Alta cardinalidade
```

**Solução:** Use logs para dados de alta cardinalidade:
```python
# ❌ Não faça isso:
increment_counter("app.requests", tags=["user_id:12345"])

# ✅ Faça isso:
logger.info("Request processed", extra={"user_id": "12345"})
```

### Quando Usar Cada Tipo de Métrica

| Tipo | Use Para | Exemplo |
|------|----------|---------|
| **COUNT** | Eventos incrementais | Requisições, erros, conversões |
| **GAUGE** | Valores instantâneos | Usuários ativos, tamanho de fila |
| **HISTOGRAM** | Distribuições por host | Latência, tamanho de resposta |
| **DISTRIBUTION** | Distribuições globais | Latência entre datacenters |

### Performance e Overhead

- **Overhead:** ~0.1-0.5ms por métrica
- **Batching:** Métricas são enviadas em lote (eficiente)
- **UDP:** Fire-and-forget (não bloqueia aplicação)

**Recomendações:**
- Não instrumente loops muito rápidos (ex: dentro de loops de 1ms)
- Use sample_rate para reduzir volume:
  ```python
  increment_counter("app.requests", sample_rate=0.1)  # 10% das requisições
  ```

### Governança de Custos

**Metrics without Limits™ (Datadog):**

Permite dissociar ingestão de indexação:
- Envie métricas com todas as tags
- Configure no Datadog quais tags preservar
- Reduza custos descartando dimensões desnecessárias

**Configuração no Datadog:**
1. Acesse **Metrics → Metrics without Limits**
2. Selecione sua métrica
3. Configure quais tags indexar
4. Tags não indexadas são descartadas antes da cobrança

---

## Seção 8: Troubleshooting Detalhado

### Métricas não aparecem no Datadog

**1. Verificar se DogStatsD está habilitado:**
```bash
echo $DD_DOGSTATSD_ENABLED
# Deve ser "true"
```

**2. Verificar conectividade com Agent/Extension:**
```bash
# Testar se Agent está escutando
nc -u localhost 8125

# Ou usar telnet
telnet localhost 8125
```

**3. Verificar logs da aplicação:**
```bash
# Procurar por warnings
grep -i "dogstatsd\|metrics" application.log
```

**4. Verificar se biblioteca está instalada:**
```bash
pip list | grep datadog
# Deve mostrar: datadog 0.45.0 (ou superior)
```

**5. Testar manualmente:**
```python
from otel_observability.metrics import increment_counter, flush

increment_counter("test.metric")
flush()  # Forçar envio
```

### Problemas de Conectividade

**Em Container (Agent):**
- Verificar se Agent está rodando: `docker ps | grep datadog`
- Verificar se porta 8125 está exposta
- Verificar firewall/security groups

**Em Lambda (Extension):**
- Verificar se Extension Layer está adicionada
- Verificar variáveis de ambiente: `DD_API_KEY`, `DD_SITE`
- Verificar logs do CloudWatch para erros da Extension

### Tags não Aplicadas Corretamente

**Problema:** Tags não aparecem no Datadog

**Solução:**
1. Verificar formato: deve ser `chave:valor`
2. Verificar se tags automáticas estão sendo aplicadas:
   ```python
   # Tags automáticas devem aparecer:
   # env:production, service:my-service, version:1.0.0
   ```
3. Verificar se não há caracteres especiais inválidos

### Alta Cardinalidade e Custos

**Sintoma:** Custos de métricas muito altos

**Diagnóstico:**
1. Acesse **Metrics → Metrics Summary** no Datadog
2. Identifique métricas com muitas séries temporais
3. Verifique tags de alta cardinalidade

**Solução:**
1. Remover tags de alta cardinalidade (user_id, session_id)
2. Usar Metrics without Limits para descartar dimensões
3. Mover dados de alta cardinalidade para logs

### Debugging com Logs

**Ativar logs de debug:**
```bash
export OTEL_LOG_LEVEL=DEBUG
```

**Procurar por:**
- `DogStatsD client initialized` - Cliente criado com sucesso
- `Failed to send` - Erro ao enviar métrica
- `High cardinality tag detected` - Aviso sobre tags

**Exemplo de log de sucesso:**
```
INFO:otel_observability.metrics:DogStatsD client initialized: host=localhost, port=8125
```

**Exemplo de log de erro:**
```
WARNING:otel_observability.metrics:Failed to send counter metric app.requests: Connection refused
```

---

## Seção 9: Integração com Outros Componentes

### Correlação com Traces

Métricas e traces podem ser correlacionados via tags:

```python
from otel_observability.metrics import increment_counter
from otel_observability.tracer import get_current_trace_id

# Adicionar trace_id como tag (opcional, para correlação)
trace_id = get_current_trace_id()
increment_counter(
    "app.request.processed",
    tags=[f"trace_id:{trace_id}"]  # ⚠️ Alta cardinalidade! Use apenas para debug
)
```

**⚠️ Atenção:** `trace_id` tem alta cardinalidade. Use apenas para debugging, não em produção.

**Melhor abordagem:** Use tags de serviço para correlacionar:
- Ambos (traces e métricas) têm tags `service`, `env`, `version`
- Filtre por essas tags no Datadog para correlacionar

### Correlação com Logs

Logs e métricas podem ser correlacionados via tags de serviço:

```python
# Métrica
increment_counter("app.errors", tags=["error_type:validation"])

# Log (com mesma tag implícita via service/env/version)
logger.error("Validation error", extra={"error_type": "validation"})
```

No Datadog, filtre por `service:my-service` e `env:production` para ver logs e métricas juntos.

### Uso com Service Map

O Service Map do Datadog mostra:
- Comunicação entre serviços (via traces)
- Métricas agregadas por serviço

Tags `service` e `env` conectam traces e métricas no Service Map.

### Dashboards e Alertas

**Criar Dashboard:**
1. Acesse **Dashboards → New Dashboard**
2. Adicione widgets de métricas
3. Configure fórmulas para funis
4. Adicione alertas

**Criar Alerta:**
1. Acesse **Monitors → New Monitor → Metric**
2. Selecione sua métrica
3. Configure condições (ex: `app.errors > 10`)
4. Configure notificações

---

## Seção 10: Referência Rápida

### Tabela Comparativa de Tipos de Métricas

| Tipo | Agregação | Use Para | Exemplo |
|------|-----------|----------|---------|
| **COUNT** | Soma | Eventos incrementais | `increment_counter("app.requests")` |
| **GAUGE** | Último valor | Valores instantâneos | `set_gauge("app.users", 150)` |
| **HISTOGRAM** | Por host | Distribuições locais | `record_histogram("app.latency", 0.125)` |
| **DISTRIBUTION** | Global | Distribuições globais | `record_distribution("app.latency", 0.125)` |

### Cheat Sheet de Funções

```python
# COUNT
increment_counter("app.requests", value=1.0, tags=["region:us-east-1"])

# GAUGE
set_gauge("app.users", 150, tags=["region:us-east-1"])

# HISTOGRAM
record_histogram("app.latency", 0.125, tags=["endpoint:/api/users"])

# DISTRIBUTION
record_distribution("app.latency", 0.125, tags=["region:us-east-1"])

# FUNIS
track_funnel_step("checkout", "start", tags=["region:us-east-1"])

# FLUSH
flush()  # Forçar envio de métricas pendentes
```

### Exemplos de Código para Casos Comuns

**Contar requisições:**
```python
increment_counter("app.requests.total", tags=["method:GET", "endpoint:/api/users"])
```

**Medir latência:**
```python
start = time.time()
# ... código ...
latency = time.time() - start
record_histogram("app.request.latency", latency, tags=["endpoint:/api/users"])
```

**Rastrear erros:**
```python
try:
    process()
except ValidationError:
    increment_counter("app.errors", tags=["error_type:validation"])
```

**Funil de conversão:**
```python
track_funnel_step("signup", "start")
track_funnel_step("signup", "email_verified")
track_funnel_step("signup", "completed")
```

### Links para Documentação Oficial

- [Datadog DogStatsD Docs](https://docs.datadoghq.com/developers/dogstatsd/)
- [Datadog Metrics Docs](https://docs.datadoghq.com/metrics/)
- [Datadog Metrics without Limits](https://docs.datadoghq.com/metrics/metrics-without-limits/)

### FAQ (Perguntas Frequentes)

**Q: Posso usar métricas sem o Datadog Agent?**
A: Não. O Agent ou Extension é necessário para receber métricas e enviá-las ao Datadog Cloud.

**Q: Métricas são enviadas em tempo real?**
A: Não. Métricas são enviadas em batch (lote) para eficiência. Use `flush()` para forçar envio imediato.

**Q: Posso usar tags com valores dinâmicos?**
A: Sim, mas evite alta cardinalidade. Tags como `user_id:12345` criam muitas séries temporais.

**Q: Qual a diferença entre HISTOGRAM e DISTRIBUTION?**
A: HISTOGRAM agrega por host, DISTRIBUTION agrega globalmente. Use DISTRIBUTION apenas quando precisar de agregação global.

**Q: Como calcular taxas de conversão?**
A: Use fórmulas no Datadog: `(sum:app.funnel.checkout.completed / sum:app.funnel.checkout.start) * 100`

---

## Navegação

- [README](../README.md) - Visão geral e quick start
- [Configuração](./CONFIGURATION.md) - Configuração detalhada
- [Datadog](./DATADOG.md) - Observabilidade no Datadog
- [Guia de Uso](./USAGE.md) - Exemplos práticos
