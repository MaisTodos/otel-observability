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

## Navegação

- [README](../README.md) - Visão geral e quick start
- [Arquitetura](./ARCHITECTURE.md) - Entenda o fluxo de dados
- [Configuração](./CONFIGURATION.md) - Configuração de endpoints
- [Conceitos](./CONCEPTS.md) - Propagação de contexto

## Referências Externas

- [Datadog APM Docs](https://docs.datadoghq.com/tracing/)
