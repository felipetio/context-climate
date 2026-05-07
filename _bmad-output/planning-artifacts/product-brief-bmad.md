---
title: "Product Brief: Context Climate"
status: "complete"
created: "2026-03-23"
updated: "2026-03-23"
inputs:
  - "_bmad-output/brainstorming/brainstorming-report.md"
  - "_bmad-output/planning-artifacts/research/domain-research-report.md"
  - "_bmad-output/planning-artifacts/research/technical-context-climate-stack-research-2026-03-23.md"
---

# Product Brief: Context Climate

## Resumo Executivo

Vivemos uma crise de confiança. Desinformação sobre mudanças climáticas circula mais rápido que os fatos, e os dados que poderiam combatê-la estão trancados em bancos de dados complexos, planilhas e APIs técnicas que a maioria das pessoas nunca vai acessar. O Banco Mundial mantém um dos datasets climáticos mais ricos do planeta (300M+ pontos de dados, 200+ economias, 10.000+ indicadores), mas um jornalista em deadline, um analista de política pública ou um estudante preparando uma apresentação para a COP não consegue simplesmente *fazer uma pergunta*.

**Context Climate** muda isso. É uma ferramenta de IA conversacional que permite a qualquer pessoa consultar dados climáticos do Banco Mundial em linguagem natural e receber respostas verificadas, com fontes, que podem ser citadas e compartilhadas. Pergunte "Como a seca aumentou no Brasil na última década?" e receba uma narrativa fundamentada em dados com atribuição completa de fonte, não um dashboard ou um CSV.

Construído para o Data 360 Global Challenge (Media Party + Banco Mundial, categoria Data Dialogue), o Context Climate é a primeira camada de dados verificados para narrativas climáticas. Cada afirmação é citável por design: a atribuição de fonte não é uma feature, é um princípio de design. Num mundo onde conteúdo gerado por IA é rotineiramente questionado, essa garantia faz do Context Climate uma ferramenta em que jornalistas e editores podem realmente confiar.

## O Problema

O desafio Data 360 Global Challenge existe porque vivemos uma crise de confiança sem precedentes. Desinformação, manipulação digital e o colapso de fatos compartilhados ameaçam a democracia e o bem-estar público. Dados climáticos existem em abundância, mas as pessoas que mais precisam deles não conseguem acessá-los:

- **Jornalistas em deadline** precisam de números rápidos e confiáveis para sustentar uma matéria. Hoje, navegam múltiplos bancos de dados, cruzam fontes, e frequentemente se contentam com o número mais fácil de encontrar, não necessariamente o mais preciso.
- **Analistas de políticas públicas** preparando comparações entre países gastam horas extraindo e formatando dados de APIs feitas para desenvolvedores, não pesquisadores.
- **Cidadãos e ativistas** tentando entender a realidade climática local acham dashboards intimidadores e planilhas impenetráveis.
- **Fact-checkers** durante períodos eleitorais precisam verificar afirmações climáticas rapidamente. As ferramentas atuais exigem expertise técnico que a maioria das redações não possui.

O custo dessa lacuna é real: desinformação climática fica sem resposta porque os dados oficiais para combatê-la são difíceis demais de acessar para quem quer verificar fatos mas não tem habilidades técnicas. Matérias são publicadas com evidências fracas. Políticas públicas são feitas com análises incompletas. A confiança pública sofre.

## A Solução

Context Climate combina investigação jornalística guiada com consulta conversacional de dados climáticos do Banco Mundial. O artefato primário é um dossiê markdown estruturado e publicável — não apenas respostas de chat. O sistema:

1. **Cria dossiês jornalísticos completos** guiando o jornalista por uma investigação estruturada com dados reais do Banco Mundial. Um checklist invisível de 10 itens (tópico, geografia, recorte temporal, público, validação de dados, estatísticas-chave, estrutura, estudos de caso, sugestões de pauta, metodologia) conduz uma entrevista conversacional. A partir do 5º item concluído, uma interface split-panel abre automaticamente: chat à esquerda, dossiê markdown ao vivo à direita. O resultado é um documento publicável com capa, resumo executivo com grandes números, partes temáticas com tabelas de dados, perfis municipais, caixas "Pauta Sugerida" e seção de Metodologia — editado pelo LLM via patch ops cirúrgicos, nunca inline no chat.
2. **Encontra os dados certos** usando a busca vetorial da API Data360 para mapear perguntas aos indicadores corretos
3. **Gera narrativas contextuais** que vão além dos números, fornecendo contexto histórico, comparações e tendências
4. **Cita cada ponto de dado** com atribuição completa de fonte do Banco Mundial (campos DATA_SOURCE extraídos diretamente da API), para que jornalistas possam citar com confiança
5. **Mostra a atualidade dos dados** exibindo o ano mais recente disponível, com avisos claros quando os dados têm mais de 2 anos
6. **Permite verificação de afirmações** onde o usuário pode colar uma afirmação climática e receber um veredito baseado em dados oficiais
7. **Cruza dados oficiais com documentos do usuário** permitindo upload de arquivos (CSV, PDF, TXT, MD) para busca semântica e análise comparativa contra os indicadores do Banco Mundial
8. **Suporta diálogo de acompanhamento** para que usuários possam refinar, comparar e explorar mais fundo

Quando nenhum indicador relevante é encontrado, o sistema diz isso de forma transparente, porque um "não tenho dados para isso" confiável é mais valioso que uma resposta errada com confiança.

**Exemplo de investigação com dossiê:**

> **Jornalista:** "Quero investigar a seca no Nordeste do Brasil para uma matéria do Nexo."
>
> **Context Climate:** "Vamos montar seu dossiê. Qual o recorte temporal que você quer cobrir?"
>
> **Jornalista:** "Última década, 2014-2024."
>
> **Context Climate:** "Perfeito. Você quer focar em estados específicos ou toda a região?"
>
> [após 5 itens do checklist concluídos, o painel do dossiê abre automaticamente à direita]
>
> **Dossiê (ao vivo, painel direito):**
> ```
> # Seca no Nordeste: Uma Década de Crise Hídrica (2014–2024)
> **Estatística-chave:** +38% em dias consecutivos sem chuva no Nordeste vs. +12% na média global
> Fonte: WB_WDI_EN_CLC_DRHT, World Bank Data360 | Dados mais recentes: 2024
> ```
>
> [o jornalista continua o chat; o dossiê é atualizado via patches sem interromper a conversa]

**Exemplo de cruzamento de dados:**

> **Usuário:** [faz upload de CSV com dados de precipitação de estações meteorológicas locais do Ceará, 2018-2024]
>
> **Usuário:** "Como esses dados locais se comparam com os indicadores de seca do Banco Mundial para o Brasil?"
>
> **Context Climate:** "Seus dados mostram uma redução média de 31% na precipitação nas estações do Ceará entre 2018 e 2024. Segundo o Banco Mundial, o índice de seca nacional do Brasil aumentou 23% no mesmo período. A discrepância sugere que o Nordeste está sendo mais afetado que a média nacional... [Fonte dados oficiais: WB_WDI_EN_CLC_DRHT, World Bank Data360 | Dados do usuário: upload CSV, 12 estações]"

**Exemplo de verificação de fato:**

> **Usuário:** "Vi no Twitter que o desmatamento no Brasil caiu 50% desde 2020. Isso é verdade?"
>
> **Context Climate:** "Segundo os dados do Banco Mundial, a área florestal do Brasil diminuiu de X para Y entre 2020 e 2024, representando uma redução de Z%. A afirmação de queda de 50% no desmatamento não é sustentada pelos indicadores disponíveis. [Fonte: WB_WDI_AG_LND_FRST_K2, World Bank Data360 | Dados mais recentes: 2023]"

## O Que Torna Isso Diferente

**Cada afirmação é citável por design.** Em 2026, a alucinação de IA no jornalismo é uma crise de credibilidade. Context Climate resolve isso estruturalmente: citações de fonte (campos DATA_SOURCE) são extraídas diretamente da resposta da API do Banco Mundial, não geradas pelo LLM. A IA interpreta e narra, mas não pode fabricar os dados subjacentes ou sua atribuição.

- **Dados oficiais, acesso conversacional.** Não é mais um chatbot que inventa números. O LLM é restrito a narrar apenas o que a API retornou, com atribuição de fonte determinística.
- **Verificação de fatos integrada.** Usuários podem colar afirmações climáticas e receber vereditos baseados em dados oficiais do Banco Mundial, restaurando confiança na informação.
- **Narrativas, não dashboards.** A saída não é um gráfico que você precisa interpretar. É um parágrafo com fontes que você pode colocar numa matéria, num briefing ou numa apresentação.
- **Cruzamento de dados oficiais com documentos do usuário.** Upload de arquivos (PDF, CSV, TXT, MD) permite busca semântica e análise comparativa contra indicadores oficiais do Banco Mundial, sempre diferenciando claramente a origem de cada dado na resposta.
- **Busca vetorial faz o trabalho pesado.** A busca semântica da API Data360 (`/searchv2`) mapeia linguagem natural para os indicadores certos automaticamente, sem necessidade de conhecer códigos ou navegar taxonomias.
- **300M+ pontos de dados como diferencial.** A plataforma Data360 do Banco Mundial cobre 200+ economias e 10.000+ indicadores. Isso não é uma fonte de dados, é um ativo que nenhum concorrente pode replicar sem o mesmo acesso institucional.
- **Construído por quem sente a dor.** Gustavo (co-fundador, jornalista) navegou esses desafios de acesso a dados profissionalmente. Isso não são engenheiros adivinhando as necessidades de jornalistas.

## Quem Isso Atende

**Primário: Jornalistas climáticos (Ana)**
Jornalistas de carreira cobrindo meio ambiente para grandes veículos. Precisam de dados rápidos, citáveis e com fonte em deadline. Sucesso = dados precisos na matéria em até 5 minutos.

**Secundário: Analistas e pesquisadores (Kofi)**
Pesquisadores em think tanks preparando análises comparativas entre países. Precisam de dados multi-país com transparência metodológica. Sucesso = horas economizadas na extração e formatação de dados.

**Terciário: Cidadãos e ativistas (Clara)**
Estudantes, ativistas e cidadãos engajados preparando apresentações, verificando afirmações ou tentando entender o impacto climático em seu país. Sucesso = compreender dados complexos sem habilidades técnicas.

## Critérios de Sucesso

| Métrica | Meta | Como Medido |
|---------|------|-------------|
| Precisão query-para-indicador | >90% | Avaliado contra conjunto de teste com 30+ queries com indicadores conhecidos |
| Citação de fonte em toda resposta com dados | 100% | Verificação automática: toda resposta com dados inclui DATA_SOURCE |
| Transparência de atualidade dos dados | 100% | Toda resposta mostra o ano mais recente disponível |
| Tempo da pergunta à resposta com fonte | <15s (sem cache), <5s (com cache) | Medição de latência ponta a ponta |
| EOI para seleção como finalista | Selecionado até 30 Abr | Marco do desafio |
| Protótipo funcional | Implantado até 31 Mai | Marco do desafio |
| Adoção pós-desafio | Pelo menos um usuário externo (não-equipe) completa uma tarefa real em 30 dias do lançamento | Rastreamento de uso |

## Escopo

### MVP (Protótipo do Desafio)

- Modo Dossiê: interface split-panel (chat à esquerda, dossiê markdown ao vivo à direita)
- Checklist invisível de 10 itens para guiar a entrevista do LLM (ativa o painel após o 5º item)
- Estrutura fixa de dossiê (capa, resumo executivo, partes temáticas, estudos de caso, Pauta Sugerida, Metodologia)
- Edição cirúrgica do dossiê via apply_ops (patch ops) — nunca inline no chat
- Toda afirmação do dossiê fundamentada em chamadas reais às ferramentas MCP
- Consultas de dados climáticos em linguagem natural
- Integração com API Data360 do Banco Mundial via servidor MCP
- Respostas com dados por país, com citações de fonte e ano dos dados
- Respostas textuais contextuais (formato narrativo)
- Modo de verificação de fatos (colar afirmação, receber veredito com dados oficiais)
- Gráficos simples de série temporal inline (tipo único de visualização)
- Persistência de conversas
- Respostas transparentes de "dados não encontrados"
- Upload de arquivos (PDF, CSV, TXT, MD) com busca semântica para cruzamento com dados oficiais
- Diferenciação clara de origem dos dados nas respostas (oficial vs. usuário)

### Fora do Escopo (Pós-MVP)

- Dados sub-nacionais (municipal/regional), previsto para o futuro (ex: integração CEMADEM/CPTEC para o Brasil)
- Interface multi-idioma (Espanhol, Francês, Português planejados para alcance no Sul Global)
- Cards de resposta compartilháveis e links de conversa (nice to have)
- Dashboards customizados e visualizações avançadas

## Visão

O dossiê jornalístico é o artefato primário do Context Climate. Em vez de respostas conversacionais efêmeras, o jornalista sai de cada sessão com um documento estruturado, citável e pronto para publicação — construído sobre dados verificados do Banco Mundial.

Se o Context Climate tiver sucesso, ele se torna a forma padrão como jornalistas e cidadãos interagem com dados de desenvolvimento, não apenas climáticos. Os 10.000+ indicadores do Banco Mundial cobrem saúde, educação, economia, governança. O mesmo padrão conversacional se aplica a todos eles.

**Curto prazo (6 meses):** Ferramenta funcional para dados climáticos, aberta para jornalistas e pesquisadores. Integração com fontes de dados brasileiras (CEMADEM, CPTEC) para profundidade sub-nacional. Open-source do servidor MCP para medir adoção orgânica.

**Médio prazo (1-2 anos):** Expansão para todos os domínios de dados do Banco Mundial. Parcerias com redes de fact-checking (afiliados IFCN, Africa Check, Chequeado) e redações. Suporte multi-idioma. API para integrações de terceiros (CMS de redações, fluxos editoriais).

**Longo prazo:** Um modelo de como dados institucionais devem ser acessados: conversacional, verificado e transparente. O desafio em si é uma plataforma de lançamento, a história de fundação e o primeiro endosso institucional que abre portas para financiamento de fundações e adoção mais ampla.

## Abordagem Técnica

- **Stack:** Chainlit + FastAPI + PostgreSQL + FastMCP 3.0 + Claude API (Haiku 4.5)
- **Arquitetura:** App ASGI monolítico, deploy em container único
- **Integração principal:** Servidor MCP encapsulando API Data360, agnóstico de transporte (stdio para dev, HTTP Streamable para produção)
- **Estratégia de grounding:** System prompt do LLM restringe respostas apenas a dados retornados pela API; campos DATA_SOURCE repassados literalmente; respostas sem dados tratadas explicitamente
- **Equipe:** Felipe (engenheiro fullstack) + Gustavo (produto/jornalista)
- **Cronograma:** Servidor MCP até 31 Mar (deadline EOI), web app até 30 Abr, protótipo até 31 Mai

## Alinhamento com o Desafio

**Data 360 Global Challenge, Categoria Data Dialogue**

O desafio pede ferramentas que restaurem a confiança na informação. Context Climate atende isso diretamente: cada resposta carrega sua fonte, cada afirmação pode ser verificada, e a barreira para acessar dados oficiais cai de "saber usar uma API" para "fazer uma pergunta." O modo de verificação de fatos leva isso além, permitindo que usuários confrontem desinformação climática diretamente com dados oficiais do Banco Mundial. O desafio não é apenas um deadline, é uma plataforma de lançamento que fornece credibilidade institucional, uma história de fundação e acesso ao ecossistema do Banco Mundial.
