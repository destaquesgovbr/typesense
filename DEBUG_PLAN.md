# Plano de Debug: Performance Crítica do Typesense

## Análise do Problema ATUALIZADA

**Problema Real Identificado**: O Typesense está extremamente lento - levando ~44 segundos por documento durante indexação, com TimeoutErrors constantes. Com 295k documentos, isso levaria **12+ dias** para completar.

### Logs Observados (VM)
```
20:06:11 - TimeoutError documento 999
20:06:45 - TimeoutError documento 1000 (+34s)
20:07:29 - TimeoutError documento 1001 (+44s)
20:08:13 - TimeoutError documento 1002 (+44s)
20:08:57 - TimeoutError documento 1003 (+44s)
```

**Padrão**: Cada documento está causando timeout de conexão após ~44 segundos, indicando sobrecarga severa.

### Contexto Importante
- Portal em **desenvolvimento** - sem tráfego real
- VM: e2-medium (2 vCPUs, 4GB RAM)
- Dataset: 295k documentos
- Auto-initialization no entrypoint.sh é **ESPERADO e CORRETO**
- Workflow Full foi disparado manualmente pelo usuário (não deveria estar rodando simultaneamente)

### Mudanças Recentes que Podem Ter Impactado

**PR #11** (merged hoje): Mudou workflows para usar `typesense-write-conn`
- ✅ Workflows atualizados corretamente
- ❌ Não adicionou timeouts nos steps

**PR #10** (merged hoje): Desacoplou config local/produção
- ✅ Adicionou suporte para ambiente local
- ✅ Adicionou parâmetro `--limit` para testes
- ❌ Não adicionou timeout no `load_dataset()`
- ❌ Mudou entrypoint.sh para buscar `typesense-write-conn` mas sem timeout nos curls

## Arquivos Críticos

### Workflows
- `.github/workflows/typesense-daily-load.yml` - sem timeout no step de carga
- `.github/workflows/typesense-full-reload.yml` - sem timeout no step de carga

### Scripts Python
- `src/typesense_dgb/dataset.py:41` - `load_dataset()` sem timeout
- `src/typesense_dgb/indexer.py:212` - `documents.import_()` sem timeout per-batch
- `src/typesense_dgb/client.py:86` - health check com timeout de 5s (OK)
- `src/typesense_dgb/collection.py:188-227` - delete collection sem timeout total

### Entrypoint
- `entrypoint.sh:12-21` - curls sem timeout para GCP metadata/secrets

## Hipóteses para Lentidão

1. **VM subdimensionada**: e2-medium pode ser insuficiente para indexar 295k documentos
2. **Memória esgotada**: Swap causando lentidão extrema
3. **Disco lento**: Disco HDD ao invés de SSD
4. **Configuração Typesense**: Parâmetros de performance mal configurados
5. **Bug no código de indexação**: Loop ou operação ineficiente por documento
6. **Conexão de rede**: Latência ao acessar APIs externas durante indexação

## Plano de Debug em Fases

### Fase 1: Diagnóstico de Recursos da VM (10 min)

**Objetivo**: Identificar se é problema de recursos (CPU, RAM, Disk I/O)

1. **Verificar uso de CPU e memória**
   ```bash
   gcloud compute ssh destaquesgovbr-typesense --command="
   echo '=== CPU ==='
   top -bn1 | head -20
   echo '=== MEMORY ==='
   free -h
   echo '=== DISK I/O ==='
   iostat -x 1 3
   echo '=== SWAP ==='
   swapon -s
   "
   ```

2. **Verificar recursos do container Typesense**
   ```bash
   gcloud compute ssh destaquesgovbr-typesense --command="
   docker stats klt-typesense-ulrt --no-stream
   "
   ```

3. **Verificar tipo de disco**
   ```bash
   gcloud compute disks describe destaquesgovbr-typesense-data \
     --zone=southamerica-east1-a --project=inspire-7-finep \
     --format='value(type,provisionedIops)'
   ```

**Indicadores de problema**:
- CPU > 90% constantemente → VM subdimensionada
- Memória swap > 0 → RAM insuficiente
- I/O wait > 30% → Disco lento
- Disk type = pd-standard → Usar pd-ssd

### Fase 2: Análise do Processo de Indexação (10 min)

**Objetivo**: Identificar se o problema está no código ou na infraestrutura

1. **Analisar logs detalhados do processo**
   ```bash
   gcloud compute ssh destaquesgovbr-typesense --command="
   docker logs klt-typesense-ulrt 2>&1 | grep -E '(INFO|WARNING|ERROR)' | tail -200
   "
   ```

2. **Verificar se há operações de rede durante indexação**
   - Checar se cada documento faz chamadas externas
   - Verificar se há download de imagens/assets por documento

3. **Inspecionar código de preparação de documentos**
   - Ler `src/typesense_dgb/indexer.py` - função `prepare_document()`
   - Verificar se há operações síncronas pesadas (HTTP requests, processamento de imagens, etc.)

### Fase 3: Teste com Dataset Reduzido (15 min)

**Objetivo**: Isolar se problema é escala ou código

1. **Reiniciar VM limpa**
   ```bash
   gcloud compute instances reset destaquesgovbr-typesense \
     --zone=southamerica-east1-a --project=inspire-7-finep
   ```

2. **Modificar entrypoint.sh temporariamente para usar --limit**
   - SSH na VM e editar entrypoint.sh
   - Mudar linha 76: `python scripts/load_data.py --mode full --limit 1000`
   - Objetivo: Testar com apenas 1000 documentos
   - Tempo esperado: ~2 minutos se código estiver OK

3. **Monitorar performance**
   ```bash
   # Em uma janela
   watch -n 1 'curl -s http://34.39.186.38:8108/health'

   # Em outra janela
   gcloud compute ssh destaquesgovbr-typesense --command="
   watch -n 2 'docker logs klt-typesense-ulrt 2>&1 | tail -20'
   "
   ```

**Resultado esperado**:
- Se indexar 1000 docs rapidamente (< 5 min): Problema é escala/recursos
- Se ainda estiver lento: Problema é código/configuração

### Fase 4: Análise do Código de Indexação (10 min)

**Objetivo**: Verificar se há bugs ou ineficiências no código

1. **Ler função prepare_document()**
   ```bash
   cat /Users/nitai/Dropbox/dev-mgi/destaquesgovbr/typesense/src/typesense_dgb/indexer.py | grep -A 50 "def prepare_document"
   ```

2. **Verificar se há:**
   - Requisições HTTP síncronas por documento
   - Processamento pesado de texto/imagens
   - Operações de I/O por documento
   - Conversões de dados ineficientes

3. **Verificar batch size**
   - Checar se batch_size=1000 é apropriado
   - Testar com batch menor (100) para ver se melhora

### Fase 5: Soluções Baseadas no Diagnóstico

**Se problema for RECURSOS:**

1. **Upgrade da VM**
   - Mudar de e2-medium (2 vCPU, 4GB) para e2-standard-4 (4 vCPU, 16GB)
   - Comandos Terraform para upgrade

2. **Upgrade do disco**
   - Mudar de pd-standard para pd-ssd
   - Aumentar IOPS provisionados

**Se problema for CÓDIGO:**

1. **Otimizar batch processing**
   - Reduzir batch size para diminuir memória
   - Adicionar paralelização com threading/async

2. **Remover operações síncronas pesadas**
   - Cache de operações repetidas
   - Pré-processar dados antes de indexar

**Se problema for CONFIGURAÇÃO:**

1. **Ajustar parâmetros Typesense**
   - Aumentar timeouts
   - Ajustar configurações de memória/cache

### Fase 6: Implementação de Timeouts (APÓS resolver performance)

**Importante**: Só implementar após resolver o problema de performance principal. Timeouts não resolvem lentidão, apenas previnem travamentos.

**Arquivos a modificar:**
1. `.github/workflows/typesense-daily-load.yml` - adicionar `timeout-minutes: 30`
2. `.github/workflows/typesense-full-reload.yml` - adicionar `timeout-minutes: 120`
3. `entrypoint.sh` - adicionar `timeout` nos curls (linhas 12, 16, 20)
4. `src/typesense_dgb/dataset.py` - wrapper de timeout no `load_dataset()`

Detalhes de implementação serão definidos após diagnóstico da Fase 1-5.

## Estratégia Recomendada

### Abordagem Imediata (Sugestão do Usuário)
1. **Reiniciar Typesense produção**
2. **Acompanhar carregamento em tempo real**
3. **Monitorar recursos durante inicialização**
4. **Identificar gargalo pela observação**

Esta é a abordagem mais direta e pragmática. Executar Fase 1 e Fase 3 do plano simultaneamente.

### Próximos Passos

1. **Agora**: Executar Fase 1 (Diagnóstico de Recursos) - 10 min
2. **Se houver problema de recursos**: Upgrade VM/Disco antes de reiniciar
3. **Reiniciar VM**: Fase 3 com monitoramento ativo
4. **Análise pós-mortem**: Identificar causa raiz
5. **Fix permanente**: Implementar solução baseada no diagnóstico
6. **Prevenção**: Adicionar timeouts (Fase 6) após resolver performance

## Notas Importantes

- Auto-initialization no entrypoint.sh é **comportamento esperado e correto**
- Portal em desenvolvimento - sem tráfego real para causar carga
- VM atual: e2-medium (2 vCPU, 4GB RAM) - pode ser insuficiente
- Dataset: 295k documentos - carga significativa para VM pequena
- Problema da chave API já resolvido - VM usando `typesense-write-conn` corretamente
- TimeoutErrors a cada ~44 segundos indicam sobrecarga severa, não problema de rede

## Métricas de Sucesso

**Performance aceitável:**
- Indexação de 1000 documentos: < 1 minuto
- Indexação de 10k documentos: < 10 minutos
- Indexação completa (295k docs): < 2 horas
- CPU usage: < 80% durante indexação
- Memória: sem swap, < 90% RAM usage
- Portal responde em < 500ms após inicialização completa
