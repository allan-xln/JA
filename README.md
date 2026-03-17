===================================================================
ELETROFRIO - SISTEMA INTELIGENTE DE MONITORAMENTO DE REFRIGERAÇÃO
===================================================================

Autores:
Allan da Silva Pereira
Igor Martins
Victor Odelan
Matheus Antunes
Leonardo Henrique

Projeto acadêmico desenvolvido no contexto da disciplina de Inteligência Artificial aplicada a sistemas industriais.

===================================================================
VISÃO GERAL DO PROJETO
===================================================================

O projeto Eletrofrio consiste no desenvolvimento de um sistema inteligente capaz de monitorar, analisar e interpretar o funcionamento de sistemas de refrigeração utilizados em ambientes comerciais e industriais, como supermercados e centros logísticos.

A solução proposta integra conceitos de Internet das Coisas (IoT), processamento de dados em fluxo contínuo e aprendizado de máquina, com o objetivo de transformar dados operacionais brutos em informações estratégicas para tomada de decisão.

Diferentemente dos sistemas tradicionais baseados em limites fixos de temperatura, o Eletrofrio utiliza inteligência artificial para compreender padrões dinâmicos de operação, permitindo a identificação de comportamentos anômalos antes que se tornem falhas críticas.

O sistema foi inicialmente desenvolvido com dados simulados, garantindo controle total sobre os cenários e permitindo validar a eficácia do modelo antes da integração com sensores reais.

===================================================================
OBJETIVO DO SISTEMA
===================================================================

O objetivo central do sistema é aumentar a confiabilidade e eficiência operacional de sistemas de refrigeração por meio da detecção precoce de falhas e da análise inteligente de dados.

Objetivos específicos:

• Monitorar continuamente variáveis físicas e operacionais dos equipamentos
• Identificar padrões de funcionamento normal e desvios comportamentais
• Detectar anomalias em tempo real
• Classificar a severidade das anomalias detectadas
• Gerar diagnósticos automáticos baseados em regras e padrões aprendidos
• Apoiar estratégias de manutenção preditiva
• Reduzir perdas operacionais e desperdício de energia

O sistema foi concebido para ser escalável, podendo atender desde uma única loja até redes com múltiplas unidades e grande volume de dados.

===================================================================
PROBLEMA ABORDADO
===================================================================

Sistemas de refrigeração são críticos para a conservação de produtos perecíveis, sendo amplamente utilizados em supermercados e na indústria alimentícia.

Falhas nesses sistemas podem gerar impactos significativos, como:

• Perda de produtos e prejuízo financeiro
• Riscos sanitários
• Aumento no consumo energético
• Paradas inesperadas de operação
• Custos elevados de manutenção corretiva

Grande parte dos sistemas atuais utiliza monitoramento baseado apenas em limites estáticos, o que impede a identificação de falhas em estágio inicial.

O Eletrofrio propõe uma abordagem baseada em análise de comportamento, permitindo detectar padrões anormais mesmo quando os valores ainda estão dentro de limites aceitáveis.

===================================================================
ARQUITETURA DO SISTEMA
===================================================================

O sistema foi estruturado em camadas, seguindo uma arquitetura modular e evolutiva.

Camadas principais:

1. Geração/Coleta de Dados
2. Processamento e Armazenamento
3. Inteligência Artificial
4. API de Integração
5. Visualização (Dashboard)

Fluxo de dados:

Simulador/Sensores → Arquivo de stream → IA → API → Frontend

Descrição:

• O simulador gera dados contínuos representando sensores reais
• Os dados são armazenados em formato JSONL (stream incremental)
• O módulo de IA processa os dados e detecta anomalias
• A API organiza e disponibiliza as informações
• O frontend apresenta os dados em tempo real ao usuário

Essa arquitetura permite substituição gradual de componentes, como troca do simulador por sensores reais.

===================================================================
TECNOLOGIAS UTILIZADAS
===================================================================

O sistema foi desenvolvido utilizando ferramentas consolidadas no ecossistema de dados e desenvolvimento web.

Backend e IA:

• Python
• Pandas (manipulação de dados)
• NumPy (operações numéricas)
• Scikit-learn (modelos de IA)
• Isolation Forest (detecção de anomalias)

API:

• FastAPI (framework de alta performance para APIs REST)

Frontend:

• Next.js (React)
• TypeScript
• Tailwind CSS
• Recharts (visualização de dados)

Ambiente:

• Anaconda (gerenciamento de dependências)
• Jupyter Lab (ambiente de análise e experimentação)

===================================================================
GERAÇÃO DE DADOS SIMULADOS
===================================================================

Devido à ausência inicial de sensores físicos, foi desenvolvido um simulador capaz de reproduzir o comportamento de sistemas reais.

Variáveis simuladas:

• Temperatura interna do equipamento
• Umidade (quando aplicável)
• Corrente elétrica do compressor
• Pressão do sistema
• Temperatura externa

Características da simulação:

• Variações suaves baseadas em ciclos diários (funções senoidais)
• Inserção de ruído estatístico (distribuição normal)
• Injeção controlada de anomalias

Exemplos de anomalias simuladas:

• Porta aberta
• Sobrecarga do compressor
• Perda de eficiência
• Queda crítica de pressão
• Falha de refrigeração

Essa abordagem permite validar o comportamento do modelo em diferentes cenários.

===================================================================
MODELO DE INTELIGÊNCIA ARTIFICIAL
===================================================================

O modelo utilizado é o Isolation Forest, um algoritmo de aprendizado não supervisionado voltado para detecção de anomalias.

Características principais:

• Não requer dados rotulados
• Baseado em isolamento de pontos anômalos
• Alta eficiência computacional
• Escalável para grandes volumes de dados

Funcionamento:

• O modelo é treinado com dados históricos
• Aprende o padrão normal de operação
• Pontos que diferem significativamente são isolados
• Esses pontos recebem classificação de anomalia

O modelo é re-treinado continuamente com novos dados, permitindo adaptação ao comportamento do sistema.

===================================================================
PROCESSO DE APRENDIZADO
===================================================================

O aprendizado ocorre de forma contínua no módulo de IA.

Etapas:

1. Coleta de dados do stream
2. Tratamento e normalização (StandardScaler)
3. Treinamento do modelo (fit)
4. Avaliação de novas leituras
5. Cálculo de score de anomalia

Cada leitura recebe:

• is_anomaly (booleano)
• anomaly_score (nível de desvio)

Isso permite classificar eventos em diferentes níveis de risco.

===================================================================
DIAGNÓSTICO INTELIGENTE
===================================================================

Além da detecção estatística, o sistema aplica regras heurísticas para interpretar os dados.

Exemplos:

• Temperatura elevada + corrente baixa → possível porta aberta
• Temperatura elevada + corrente alta → sobrecarga
• Pressão baixa → possível falha no circuito

Essa combinação de IA + regras de negócio aumenta a interpretabilidade do sistema.

===================================================================
VISUALIZAÇÃO E DASHBOARD
===================================================================

O frontend apresenta uma interface moderna para acompanhamento operacional.

Funcionalidades:

• Métricas gerais (ativos, alertas, risco médio)
• Lista de ativos monitorados
• Alertas em tempo real
• Gráfico de temperatura com limite operacional
• Atualização periódica automática

O dashboard permite visão centralizada do sistema, facilitando tomada de decisão.

===================================================================
BENEFÍCIOS DO SISTEMA
===================================================================

• Redução de perdas de produtos
• Detecção precoce de falhas
• Aumento da eficiência energética
• Redução de manutenção corretiva
• Melhor gestão de ativos
• Base para manutenção preditiva

===================================================================
EVOLUÇÕES FUTURAS
===================================================================

• Integração com sensores reais (ESP32 / IoT)
• Armazenamento em banco de dados
• WebSockets para tempo real
• Notificações automáticas (WhatsApp / email)
• Modelos preditivos (forecasting)
• ERP logístico integrado

===================================================================
APLICAÇÕES
===================================================================

• Supermercados
• Centros de distribuição
• Indústrias alimentícias
• Armazenamento refrigerado
• Logística frigorificada

===================================================================
CONSIDERAÇÕES FINAIS
===================================================================

O projeto Eletrofrio demonstra a aplicação prática de inteligência artificial em um contexto industrial real.

A solução vai além do monitoramento tradicional, utilizando análise de padrões para identificar riscos operacionais antes que se tornem críticos.

Mesmo em fase inicial, o sistema já apresenta uma arquitetura próxima de aplicações reais de mercado, podendo evoluir para um produto completo de monitoramento inteligente.

O projeto integra conhecimentos de:

• aprendizado de máquina
• engenharia de software
• análise de dados
• sistemas distribuídos

Constituindo uma base sólida para aplicações futuras em ambientes industriais.

===================================================================