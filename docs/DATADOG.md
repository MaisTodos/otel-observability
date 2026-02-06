# Observabilidade no Datadog

Este documento explica como visualizar traces e logs no Datadog e como resolver problemas comuns.

## Visualizando Traces

No Datadog, acesse **APM → Traces**:

1. **Flame Graph** - Visualização hierárquica dos spans
2. **Trace Timeline** - Linha do tempo com latências
3. **Span Tags** - Filtrar por atributos customizados
4. **Logs Correlacionados** - Ver logs relacionados ao trace

## Service Map

Datadog gera automaticamente um **mapa de serviços** mostrando:
- Quais serviços se comunicam
- Latência entre serviços
- Taxa de erros por conexão

## Troubleshooting

### Traces não aparecem no Datadog

1. **Verificar endpoint OTLP:**
   ```bash
   echo $OTEL_EXPORTER_OTLP_ENDPOINT
   # Deve ser http://localhost:4318 (SEM /v1/traces)
   ```

2. **Verificar Datadog Agent/Extension:**
   ```bash
   # Lambda: verificar se Extension está na layer
   # Container: curl http://localhost:4318/v1/traces
   ```

3. **Ativar console export para debug:**
   ```bash
   export OTEL_CONSOLE_EXPORT=true
   # Verá spans impressos no console
   ```

### Trace context não propaga

1. **Verificar injeção** - Produtor deve usar helpers de propagação
2. **Verificar extração** - Consumidor extrai automaticamente
3. **Logs debug:**
   ```bash
   export OTEL_LOG_LEVEL=DEBUG
   # Verá mensagens como "Extracted context from SQS"
   ```

### Performance

- **Sampling**: Reduza `OTEL_TRACES_SAMPLER_ARG` para < 1.0 em alta carga
- **Overhead**: ~1-5ms por span em média

## Datadog Lambda Extension

A **Datadog Lambda Extension** é a forma recomendada de enviar telemetria (traces, métricas, logs) de funções AWS Lambda para o Datadog.

### Por que usar a Extension?

- ✅ **Menor latência**: Envio direto, sem passar pelo CloudWatch Logs
- ✅ **Redução de custos**: Menos processamento de logs no CloudWatch
- ✅ **Tracing completo**: Captura traces mesmo em falhas catastróficas (timeouts, OOM)
- ✅ **Enhanced Metrics**: Métricas de alta resolução (segundo a segundo)
- ✅ **Métricas customizadas**: Suporte a DogStatsD via localhost:8125

### Como Configurar

1. **Adicionar a Extension Layer à sua Lambda:**

   ```bash
   # Obter a ARN da layer mais recente
   # Para Python 3.10 em us-east-1:
   arn:aws:lambda:us-east-1:464622532012:layer:Datadog-Python310:XX
   ```

   Ou via Terraform:

   ```hcl
   resource "aws_lambda_function" "my_function" {
     # ... outras configurações ...

     layers = [
       "arn:aws:lambda:${var.aws_region}:464622532012:layer:Datadog-Python310:XX"
     ]

     environment {
       variables = {
         DD_API_KEY = var.datadog_api_key
         DD_SITE = "datadoghq.com"
         DD_APM_ENABLED = "true"
         DD_LOGS_ENABLED = "true"
         DD_TRACE_ENABLED = "true"
       }
     }
   }
   ```

2. **Configurar variáveis de ambiente:**

   ```bash
   DD_API_KEY=your-api-key
   DD_SITE=datadoghq.com  # ou datadoghq.eu
   DD_APM_ENABLED=true
   DD_LOGS_ENABLED=true
   DD_TRACE_ENABLED=true
   ```

3. **A biblioteca detecta automaticamente:**

   A biblioteca `otel-observability` detecta automaticamente se está rodando em Lambda e envia traces para `localhost:4318`, que é o endpoint padrão da Extension.

### Diferenças: Forwarder vs Extension

| Aspecto | Forwarder (Legado) | Extension (Recomendado) |
|---------|-------------------|-------------------------|
| **Latência** | Alta (via CloudWatch Logs) | Baixa (envio direto) |
| **Custos AWS** | Maior (processamento de logs) | Menor |
| **Traces em falhas** | Pode perder traces finais | Captura sempre |
| **Métricas customizadas** | Limitado | Suporte completo (DogStatsD) |
| **Enhanced Metrics** | Não | Sim (alta resolução) |

### Enhanced Metrics

A Extension habilita automaticamente **Enhanced Metrics**, que são métricas de distribuição de alta resolução:

- `aws.lambda.enhanced.duration` - Latência segundo a segundo
- `aws.lambda.enhanced.errors` - Erros segundo a segundo
- `aws.lambda.enhanced.invocations` - Invocações segundo a segundo

Essas métricas aparecem automaticamente no Datadog quando a Extension está configurada.

## Datadog Forwarder (Configuração de Logs)

O **Datadog Forwarder** é uma Lambda function que assina Log Groups do CloudWatch e reencaminha logs para o Datadog. Embora a Extension seja recomendada para novas implementações, o Forwarder ainda é útil em alguns cenários.

### Configuração do Forwarder

Para garantir que os logs sejam corretamente segmentados por serviço no Datadog, configure a variável `DD_ENRICH_CLOUDWATCH_TAGS` no Forwarder.

#### Via Terraform

```hcl
resource "aws_lambda_function" "datadog_forwarder" {
  function_name = "datadog-forwarder"
  # ... outras configurações ...

  environment {
    variables = {
      DD_API_KEY = var.datadog_api_key
      DD_SITE = "datadoghq.com"
      DD_ENRICH_CLOUDWATCH_TAGS = "true"  # IMPORTANTE!
    }
  }
}
```

#### Via CloudFormation

```yaml
DatadogForwarder:
  Type: AWS::Lambda::Function
  Properties:
    Environment:
      Variables:
        DD_API_KEY: !Ref DatadogApiKey
        DD_SITE: datadoghq.com
        DD_ENRICH_CLOUDWATCH_TAGS: "true"  # IMPORTANTE!
```

### Como Funciona o Enriquecimento de Tags

Quando `DD_ENRICH_CLOUDWATCH_TAGS=true`:

1. O Forwarder consulta as **Resource Tags** da AWS aplicadas ao Log Group ou à Lambda de origem
2. Essas tags são aplicadas aos logs ingeridos no Datadog
3. Se a Lambda tiver a tag `service:payment-api`, os logs aparecerão automaticamente com essa tag

### Tags Recomendadas nos Recursos AWS

Para garantir segmentação correta, aplique as seguintes tags aos seus recursos:

```hcl
resource "aws_lambda_function" "my_function" {
  # ... configurações ...

  tags = {
    env     = "production"
    service = "payment-api"
    version = "1.2.0"
  }
}
```

Essas tags serão automaticamente aplicadas aos logs quando o Forwarder estiver configurado com `DD_ENRICH_CLOUDWATCH_TAGS=true`.

### Nota sobre Logs da Biblioteca

A biblioteca `otel-observability` já inclui as tags `env`, `service` e `version` explicitamente nos logs JSON (via `JSONFormatter`). Isso garante que as tags apareçam mesmo quando o Forwarder não está configurado para enriquecimento.

## Navegação

- [README](../README.md) - Visão geral e quick start
- [Guia de Implementação](./IMPLEMENTATION_GUIDE.md) - Roteiro de uso da lib em serviços
- [Arquitetura](./ARCHITECTURE.md) - Entenda o fluxo de dados
- [Configuração](./CONFIGURATION.md) - Configuração de endpoints
- [Conceitos](./CONCEPTS.md) - Propagação de contexto

## Referências Externas

- [Datadog APM Docs](https://docs.datadoghq.com/tracing/)
