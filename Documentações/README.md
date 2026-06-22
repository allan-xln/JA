# Eletrofrio AI - Plataforma Operacional de Refrigeração

## 1. O Que É O Sistema

O Eletrofrio AI é uma plataforma de monitoramento operacional para ambientes de refrigeração comercial. O sistema coleta dados reais dos endpoints oficiais da Eletrofrio, organiza essas informações em uma base operacional no Supabase, identifica ocorrências relevantes e ajuda a equipe a acompanhar lojas, sensores, equipamentos, alarmes e telemetria.

Apesar de usar recursos de inteligência artificial, o foco do produto não é ser um chatbot. A proposta é ser um cockpit corporativo de operação: um painel para visualizar a situação da rede, um motor de priorização para indicar o que exige ação e um canal de comunicação via WhatsApp para levar alertas e consultas para a equipe.

## 2. Problema Que Ele Resolve

Operações de refrigeração lidam com muitos equipamentos distribuídos em várias lojas. Alarmes, variações de temperatura, falhas de comunicação e recorrências podem aparecer em grande volume. Sem uma camada de organização, a equipe precisa interpretar dados soltos, alternar entre sistemas e descobrir manualmente o que é mais importante.

O sistema resolve esse problema ao:

- centralizar dados reais de unidades, dispositivos, alarmes e telemetria;
- classificar ocorrências por criticidade;
- indicar lojas e equipamentos com maior atenção operacional;
- gerar insights com evidência;
- enviar alertas pelo WhatsApp;
- permitir consultas operacionais por mensagem, como "quais equipamentos estão offline?" ou "como está a loja Sítio Cercado?";
- manter histórico de coletas e automação.

## 3. Arquitetura Geral

```text
Endpoints oficiais Eletrofrio
  -> Backend FastAPI
  -> Normalização e deduplicação
  -> Supabase
  -> Collector / Scheduler
  -> Métricas, regras e análise operacional
  -> Diagnóstico operacional / RAG
  -> WhatsApp Baileys
  -> Frontend Next.js
  -> Docker Compose
```

### FastAPI / Backend

O backend é o centro da plataforma. Ele expõe endpoints internos para o frontend, executa coletas, consulta o Supabase, aciona a análise operacional, faz proxy para o serviço WhatsApp e responde às consultas do módulo operacional.

Principais rotas:

- `GET /api/eletrofrio/health`
- `GET /api/eletrofrio/overview`
- `GET /api/eletrofrio/units`
- `GET /api/eletrofrio/devices`
- `GET /api/eletrofrio/alarms`
- `GET /api/eletrofrio/telemetry`
- `GET /api/eletrofrio/insights`
- `POST /api/eletrofrio/assistant/ask`
- `POST /api/eletrofrio/assistant/query`
- `GET /api/collector/status`
- `PUT /api/collector/settings`
- `POST /api/collector/run-now`

### Supabase

O Supabase funciona como banco operacional remoto. Ele armazena dados normalizados e também preserva payloads originais para auditoria.

Tabelas principais:

- `eletrofrio_units`
- `eletrofrio_devices`
- `eletrofrio_alarms`
- `eletrofrio_telemetry`
- `eletrofrio_ai_insights`
- `eletrofrio_collector_runs`

Tabelas de automação, quando aplicadas:

- `eletrofrio_collector_settings`
- `eletrofrio_anomalies`
- `eletrofrio_anomaly_events`
- `eletrofrio_anomaly_notes`
- `eletrofrio_anomaly_tickets`
- `eletrofrio_anomaly_ai_solutions`
- `eletrofrio_retention_runs`

Tabelas multi-cliente, quando aplicada a migration `sql/005_multi_tenant_auth.sql`:

- `eletrofrio_customers`
- `eletrofrio_users`
- `eletrofrio_customer_units`
- `eletrofrio_customer_devices`
- `eletrofrio_sessions`

### Endpoints Oficiais Da Eletrofrio

O sistema usa somente os endpoints oficiais:

- Alarmes: `route=alarmes`
- Unidades: `route=unidades`
- Telemetria: `route=telemetria&dispositivoId=ID_DO_DISPOSITIVO`
- Abertura de chamado: `route=abrir-chamado`

Base:

```env
ELETROFRIO_API_BASE_URL=https://credenciamento.eletrofrio.com.br:5900/galileo/api/api_hackathon
```

### Collector / Scheduler

O collector executa a coleta dos dados oficiais, normaliza as respostas, salva no Supabase e registra a execução. O scheduler automatiza esse processo com intervalo configurável.

Funções principais:

- buscar unidades;
- buscar alarmes;
- buscar telemetria por dispositivo;
- salvar registros com deduplicação;
- gerar métricas e insights;
- registrar histórico de execução;
- acionar análise de anomalias e notificações quando configurado.

### Análise De Alarmes E Telemetria

A camada de análise calcula métricas e regras operacionais:

- recorrência de alarmes por dispositivo;
- concentração de alarmes por loja;
- temperatura atual, média, mínima e máxima;
- tendência de temperatura;
- severidade por tipo de evento;
- lojas críticas;
- equipamentos com maior atenção;
- evidência suficiente ou parcial.

### Diagnóstico Operacional / RAG

O endpoint de consulta operacional recebe perguntas e busca contexto real no Supabase. Ele usa unidades, dispositivos, alarmes, telemetria, insights e histórico de coletas para responder com base operacional.

Exemplos:

- "Me dá um resumo da operação."
- "Como está a loja Sítio Cercado?"
- "Quais equipamentos estão offline?"
- "Teve alguma anomalia hoje?"
- "Qual sensor deu problema?"

O sistema não inventa valores. Se não houver evidência suficiente, ele informa isso claramente.

Com login de cliente, o RAG recebe apenas lojas, dispositivos, alarmes, telemetria, insights e anomalias do tenant autenticado. Perguntas sobre loja fora do ambiente do cliente não retornam dados de terceiros.

### Login E Multi-cliente

O sistema possui autenticação em `/api/auth/login`, sessão por bearer token e dois perfis:

- admin: visão completa da operação;
- cliente: visão filtrada por lojas e dispositivos vinculados.

O seed `python -m api.scripts.seed_tenants` cria o usuário admin e usuários de demonstração por cliente/loja detectada. A documentação detalhada está em:

- `Documentações/MULTI_TENANT.md`
- `Documentações/USUARIOS_DEMO.md`
- `Documentações/LEVANTAMENTO_TECNICO_COMERCIAL_ELETROFRIO.md`
- `Documentações/VALORES_COMERCIAIS_ELETROFRIO.md`

### Motor De Regras Operacionais

O sistema agora possui um motor de regras auditável. A decisão operacional não depende apenas da síntese textual: ela vem de critérios técnicos cadastrados, como limite de temperatura, texto de alarme, tipo de equipamento, recorrência e ausência de telemetria.

O motor permite:

- cadastrar e editar regras;
- aplicar regras sugeridas;
- inferir tipo de equipamento por tag e texto técnico;
- explicar qual regra foi violada;
- calcular score operacional e nível de evidência;
- registrar avaliações recentes;
- enriquecer ocorrências e mensagens de WhatsApp com regra, evidência e primeira ação.

Assim, a IA fica como explicadora/sintetizadora. A decisão continua rastreável por regra, alarme, telemetria e histórico.

### Ocorrências Operacionais

Cada anomalia relevante vira uma ocorrência operacional com código público no formato `OC-AAAAMMDD-NNNN`. Esse código aparece no painel, pode ser copiado, enviado por WhatsApp e pesquisado para abrir diretamente o modal da ocorrência.

O modal de ocorrência mostra dados técnicos, loja, equipamento, severidade, status, evidências, sugestão de correção por IA, envio por WhatsApp, observações, chamados internos e histórico completo. As ações principais registram eventos no histórico e respeitam o isolamento multi-cliente.

### Retenção De Dados

O projeto possui SQLs de retenção para evitar crescimento sem limite no Supabase. A migration `sql/009_data_retention_and_cleanup.sql` cria a camada de limpeza controlada. Para ambiente em plano free, o arquivo `sql/011_free_plan_retention_cleanup.sql` mantém uma janela curta de dados operacionais e preserva usuários, clientes, regras, destinatários, auth e sessão do WhatsApp.

### WhatsApp / Baileys

O serviço WhatsApp é um processo Node.js separado, usando Baileys. Ele conecta por QR Code, mantém sessão persistida e conversa com o backend para enviar mensagens e responder consultas operacionais.

Funções:

- conectar aparelho via QR Code;
- consultar status da sessão;
- enviar mensagens de teste;
- processar insights pendentes;
- receber perguntas operacionais;
- chamar `/api/eletrofrio/assistant/ask`;
- responder no próprio WhatsApp.

### Frontend Next.js

O frontend é a interface corporativa do cockpit. Ele organiza a operação em telas simples de explicar: visão geral, ativos, ocorrências, rotina, comunicação e consulta operacional.

### Docker

O projeto possui Docker Compose com quatro serviços:

- `api`: backend FastAPI;
- `scheduler`: automação da coleta;
- `frontend`: Next.js;
- `whatsapp`: serviço Baileys.

O banco continua sendo o Supabase remoto.

## 4. Telas Do Sistema

### Visão Geral / Dashboard Operacional

Mostra a operação como um todo:

- total de lojas;
- total de equipamentos;
- quantidade de ocorrências;
- volume de telemetria;
- prioridades recentes;
- lojas com maior atenção;
- canal operacional.

Mensagem para apresentação: "Aqui eu vejo a saúde geral da operação."

### Ativos Monitorados / Dispositivos

Mostra equipamentos identificados, loja associada, tag, número de ocorrências, última telemetria e temperatura. Ajuda a acompanhar comportamento operacional por ativo.

Mensagem para apresentação: "Aqui eu acompanho os equipamentos e vejo quais ativos apresentam recorrência ou leitura recente."

### Ocorrências / Alertas Operacionais

Lista ocorrências priorizadas com severidade, resumo, motivo técnico, ação recomendada e evidência. Essa tela ajuda a equipe a decidir o que precisa de atenção primeiro.

Mensagem para apresentação: "Aqui eu priorizo o que exige ação."

### Centro Operacional

Centraliza o snapshot operacional, a rotina de sincronização e o diagnóstico baseado em evidências:

- automação ligada/desligada;
- intervalo de coleta;
- último snapshot válido salvo no Supabase;
- totais operacionais de lojas, alarmes e telemetria;
- próxima execução;
- status;
- cooldown de comunicação;
- histórico de execuções úteis;
- ocorrências abertas.
- envio/processamento da fila de ocorrências para WhatsApp;
- diagnóstico operacional com perguntas rápidas, fontes consultadas, confiança e avisos de evidência.

Tentativas automáticas sem dados, como timeouts pontuais da API oficial de unidades, são filtradas da experiência principal para manter o painel limpo e focado no estado operacional.

Mensagem para apresentação: "Aqui eu acompanho o recorte operacional válido, configuro a rotina, faço diagnóstico rápido e encaminho ocorrências para o WhatsApp."

### Comunicação / WhatsApp

Gerencia o canal operacional com a equipe:

- conexão por QR Code;
- status do aparelho;
- envio de teste;
- processamento de fila de ocorrências;
- modo de validação;
- sessão persistida.

Mensagem para apresentação: "Aqui eu acompanho o canal que leva a informação para a equipe."

### Diagnóstico Operacional

O diagnóstico operacional fica integrado ao Centro Operacional. Ele funciona como apoio técnico para validar perguntas, fontes consultadas, confiança operacional e avisos de evidência sem transformar o produto em uma tela de chat.

Mensagem para apresentação: "O diagnóstico está dentro da operação: eu pergunto, vejo evidências e decido o próximo passo."

## 5. WhatsApp Operacional

O WhatsApp é um dos principais diferenciais do projeto porque leva a informação para onde a equipe já trabalha.

### Conexão Por QR Code

O serviço gera um QR Code quando iniciado. Depois de escaneado, a sessão fica salva em `whatsapp/sessions/eletrofrio`.

### Envio De Alertas

Insights e ocorrências relevantes podem ser enviados para destinatários autorizados. O envio respeita regras de cooldown para evitar spam por equipamento e por loja.

O serviço prioriza mensagens quando existe evidência operacional:

- criticidade alta;
- alerta de warning com repetição;
- loja crítica;
- alta temperatura;
- nível de líquido;
- falha de compressor;
- offline/comunicação;
- baixa pressão;
- degelo;
- múltiplos alarmes recentes.

O serviço não envia alerta quando a evidência é fraca, quando o item já foi enviado, quando está em cooldown, quando `WHATSAPP_ENABLED=false` ou quando não existe destinatário autorizado.

Para apresentação, se `WHATSAPP_ALLOWED_RECIPIENTS` estiver vazio e a sessão estiver conectada, o serviço usa o número conectado como destino de demonstração. Para produção, a recomendação é sempre preencher a lista de destinatários autorizados.

### Processamento De Insights

O endpoint `/api/eletrofrio/whatsapp/process-insights` processa insights pendentes e envia mensagens quando permitido.

Com `WHATSAPP_DRY_RUN=true`, o serviço não envia mensagem real e retorna uma simulação do que seria enviado. Isso é ideal para demonstração e validação em sala.

Exemplo de mensagem automática:

```text
Ocorrência operacional detectada

Loja: Sítio Cercado
Equipamento: 1C2 - CF. CONGELADOS 2
Prioridade: Alta

Evidência: alarme de alta temperatura registrado recentemente.
Recomendação: verificar operação local, porta, carga térmica e condição do equipamento.

Obs.: causa raiz não confirmada automaticamente.
```

### Diagnóstico Operacional Por Mensagem

Quando alguém envia uma pergunta operacional, o serviço WhatsApp identifica o tipo de consulta, chama o backend e responde com uma mensagem curta e profissional.

Esse canal não é apresentado como chatbot genérico. Ele funciona como canal operacional: recebe perguntas objetivas da equipe, consulta dados reais e devolve situação, evidências e recomendação.

Exemplos de perguntas:

- "me dá um resumo da operação"
- "qual sensor deu problema?"
- "teve alguma anomalia hoje?"
- "quais equipamentos estão offline?"
- "como está a loja Sítio Cercado?"
- "qual equipamento está com problema agora?"
- "como está a temperatura do sensor X?"
- "o compressor 2 está normal?"

## 6. Como O Diagnóstico Operacional Funciona

O diagnóstico operacional funciona como um RAG operacional:

1. Recebe a pergunta.
2. Detecta intenção: loja, sensor, equipamento, anomalia, resumo, offline, temperatura etc.
3. Busca dados reais no Supabase.
4. Recupera unidades, dispositivos, alarmes, telemetria, insights e histórico.
5. Aplica regras operacionais.
6. Se houver OpenAI configurado, sintetiza uma resposta com base apenas no contexto recuperado.
7. Se a OpenAI falhar ou não estiver configurada, usa fallback local por regras.
8. Retorna resposta com fontes, avisos e confiança operacional.

Princípios:

- não inventar sensores;
- não inventar temperaturas;
- não inventar lojas;
- não confirmar falha sem evidência;
- avisar quando a telemetria estiver vazia;
- avisar quando os dados estiverem antigos;
- pedir mais contexto quando a pergunta for ambígua.

## 7. Como Rodar Localmente Em 4 Terminais

### Terminal 1 - Backend

```bash
cd /caminho/onde/voce/clonou/JA
conda activate eletrofrio-ai
uvicorn api.main:app --reload
```

### Terminal 2 - Collector Ou Scheduler

Coleta manual:

```bash
cd /caminho/onde/voce/clonou/JA
conda activate eletrofrio-ai
python -m api.collector
```

Scheduler:

```bash
cd /caminho/onde/voce/clonou/JA
conda activate eletrofrio-ai
python -m api.scheduler
```

### Terminal 3 - Frontend

```bash
cd /caminho/onde/voce/clonou/JA/Frontend/JA-IA-ELETROFRIO
npm run dev
```

### Terminal 4 - WhatsApp

```bash
cd /caminho/onde/voce/clonou/JA/whatsapp
npm run dev
```

## 8. Como Rodar Com Docker

Prepare o `.env`:

```bash
cd /caminho/onde/voce/clonou/JA
cp .env.docker.example .env
nano .env
```

Subir tudo:

```bash
docker compose up --build
```

Subir em background:

```bash
docker compose up -d --build
```

Parar:

```bash
docker compose down
```

Limpar volumes:

```bash
docker compose down -v
```

Atenção: limpar volumes apaga a sessão persistida do WhatsApp.

## 9. Como Testar

### Backend

```bash
curl http://127.0.0.1:8000/api/eletrofrio/health
curl http://127.0.0.1:8000/api/eletrofrio/overview
curl http://127.0.0.1:8000/api/eletrofrio/units
curl http://127.0.0.1:8000/api/eletrofrio/devices
```

### Frontend

Abra:

```text
http://localhost:3000
```

### WhatsApp

```bash
curl http://127.0.0.1:8091/status
curl http://127.0.0.1:8000/api/eletrofrio/whatsapp/status
curl -X POST http://127.0.0.1:8000/api/eletrofrio/whatsapp/start
curl http://127.0.0.1:8000/api/eletrofrio/whatsapp/qr
```

### Diagnóstico Operacional

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/assistant/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Me dá um resumo da operação agora"}'
```

### Collector / Scheduler

```bash
python -m api.collector
python -m api.scheduler
```

Endpoints da automação:

```bash
curl http://127.0.0.1:8000/api/collector/status
curl http://127.0.0.1:8000/api/collector/runs?limit=5
curl 'http://127.0.0.1:8000/api/collector/anomalies?limit=5&status=open'
curl -X POST http://127.0.0.1:8000/api/eletrofrio/whatsapp/process-insights
```

### Motor De Regras

```bash
curl http://127.0.0.1:8000/api/eletrofrio/rules
curl http://127.0.0.1:8000/api/eletrofrio/rules/defaults/preview
curl -X POST http://127.0.0.1:8000/api/eletrofrio/rules/defaults/apply
curl -X POST http://127.0.0.1:8000/api/eletrofrio/rules/evaluate
curl http://127.0.0.1:8000/api/eletrofrio/rule-evaluations
```

## 10. Principais Diferenciais

- Usa dados reais dos endpoints oficiais da Eletrofrio.
- Preserva payload bruto para auditoria.
- Organiza operação por loja, equipamento, alarme e telemetria.
- Prioriza ocorrências em vez de apenas listar dados.
- Integra WhatsApp como canal operacional.
- Permite consulta por mensagem, sem depender de abrir o painel.
- Usa IA de forma controlada, baseada em evidências.
- Tem fallback por regras quando a OpenAI não está disponível.
- Pode rodar localmente ou via Docker.
- Tem arquitetura separada por backend, frontend, collector, scheduler e WhatsApp.

## 11. Limitações E Pontos Futuros

- O Supabase precisa estar com as migrations aplicadas. Em ambiente novo, execute `sql/001_initial_schema.sql` e depois `sql/002_collector_runtime_schema.sql` no SQL Editor.
- Para usar o motor de regras auditável, execute também `sql/003_operational_rules.sql`.
- A qualidade das respostas depende da disponibilidade e atualidade da telemetria.
- O sistema não deve confirmar falha quando só existe ausência de dados.
- O envio real pelo WhatsApp exige configuração cuidadosa de destinatários.
- A abertura automática de chamados deve ser ativada apenas após validação operacional.
- Próximos passos possíveis:
  - melhorar dashboards por loja;
  - criar visão de SLA;
  - adicionar histórico por equipamento;
  - agrupar ocorrências recorrentes;
  - criar perfis de usuário;
  - gerar relatórios executivos.

## Atualizar Schema Supabase

Quando o backend mostrar mensagens como tabela `eletrofrio_collector_settings` ausente, tabela `eletrofrio_anomalies` ausente ou coluna `trigger_source` ausente em `eletrofrio_collector_runs`, o problema é o schema do Supabase desatualizado.

Para corrigir:

```text
1. Abra o projeto no Supabase.
2. Acesse SQL Editor.
3. Em instalação nova, execute primeiro sql/001_initial_schema.sql.
4. Execute sql/002_collector_runtime_schema.sql.
5. Execute sql/003_operational_rules.sql.
6. Reinicie os containers com docker compose up -d --build.
```

As migrations `sql/002_collector_runtime_schema.sql` e `sql/003_operational_rules.sql` são idempotentes: usam `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` e `CREATE INDEX IF NOT EXISTS`, então podem ser executadas novamente com segurança.

## Motor De Regras Operacionais

O diferencial é que a plataforma não apenas recebe alarmes: ela cruza alarmes, telemetria e regras técnicas editáveis para explicar por que uma ocorrência é prioridade e qual ação tomar primeiro.

Exemplo de regra:

```text
Nome: Alta temperatura em congelados
Condição: temperatura acima do limite configurado ou alarme de alta temperatura
Severidade: crítica
Explicação: equipamento de congelados deve operar abaixo da faixa configurada para preservar produto.
Ação: verificar porta, carga térmica, evaporador, degelo, vedação e leitura local.
```

No painel, a tela **Regras Operacionais** permite aplicar regras sugeridas, editar critérios, ativar/desativar uma regra e reavaliar ocorrências recentes. As ocorrências priorizadas passam a mostrar regra aplicada, tipo inferido do equipamento, nível de evidência e score operacional.

## Pitch Para Apresentação Na Faculdade

Este projeto é uma plataforma de monitoramento inteligente para operações de refrigeração comercial, desenvolvida a partir de um cenário real da Eletrofrio.

O problema que ele resolve é bem comum em operações com muitos equipamentos distribuídos em várias lojas: existe um grande volume de alarmes, sensores, leituras de temperatura e eventos técnicos, mas nem sempre é fácil saber o que realmente exige atenção primeiro. A equipe pode receber muitos dados, mas ainda precisar interpretar manualmente quais lojas estão críticas, quais equipamentos estão com recorrência e onde existe risco operacional.

A solução que eu desenvolvi organiza esse fluxo em uma plataforma operacional. O sistema coleta dados reais dos endpoints oficiais da Eletrofrio, como unidades, alarmes e telemetria dos dispositivos. Esses dados são normalizados e salvos no Supabase, mantendo também o payload original para auditoria. A partir disso, o backend calcula métricas, identifica recorrências, classifica severidades e gera insights operacionais.

No painel, a operação consegue ver a visão geral da rede, acompanhar ativos monitorados, priorizar ocorrências e configurar a rotina de coleta automática. Mas um dos pontos mais importantes é que a informação não fica presa no dashboard. O sistema também integra um canal de WhatsApp usando Baileys. Assim, a equipe pode receber alertas e também fazer perguntas diretamente pelo WhatsApp, como "quais equipamentos estão offline?", "teve alguma anomalia hoje?" ou "como está a loja Sítio Cercado?".

A camada de consulta operacional funciona com uma lógica de RAG: ela busca dados reais no banco, usa alarmes, telemetria, insights e unidades, e só responde com base nessas evidências. Se não houver dado suficiente, o sistema informa isso. Ou seja, a inteligência artificial não é usada para inventar diagnóstico, mas para sintetizar informações operacionais de forma clara e útil.

O valor prático do projeto está em transformar dados técnicos em decisão operacional. Em vez de apenas mostrar alarmes, ele ajuda a priorizar ação, orientar equipes e reduzir o tempo entre a identificação de uma ocorrência e a resposta. Para uma operação real de refrigeração, isso pode significar menos perda de produto, mais controle sobre equipamentos críticos e uma comunicação mais rápida entre sistema e equipe de campo.

Em resumo, o Eletrofrio AI não é apenas um painel. Ele é um cockpit operacional com coleta real, análise de evidências, automação e comunicação integrada pelo WhatsApp, pensado para aproximar dados técnicos da tomada de decisão.
