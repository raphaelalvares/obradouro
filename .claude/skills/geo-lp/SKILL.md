---
name: geo-lp
description: Criar ou revisar landing page, site institucional ou conteúdo de marketing otimizado para ser citado e RECOMENDADO por IAs (ChatGPT, Claude, Perplexity, Gemini/AI Overviews) — GEO/AEO. Usar quando o usuário pedir LP, página de preços, comparativo/listicle, "ser achado/sugerido por IA", ou estratégia de presença web para uma ferramenta/SaaS.
---

# GEO / AEO — landing pages e presença web que IAs citam e recomendam

Objetivo: fazer a ferramenta aparecer quando alguém pergunta a uma IA "qual o melhor software
para X". Baseado em pesquisa verificada (jul/2026); os números citados abaixo têm fonte em
`references/copywriting-geo.md`, `references/config-tecnica.md` e `references/off-page.md` —
leia o reference da etapa antes de executá-la.

## As 4 verdades que ordenam tudo (não pular)

1. **Crawlers de IA não executam JavaScript** (exceção: ecossistema Google). SPA sem
   prerender = invisível para ChatGPT/Claude/Perplexity. Site de marketing é **HTML
   estático/SSG, separado do app** (app em subdomínio). Teste: `curl -A "GPTBot" <url>`
   tem que devolver o texto completo.
2. **IAs citam chunks, não páginas.** Cada seção precisa ser autocontida: heading em forma
   de pergunta + resposta nas 2 primeiras frases + entidade nomeada por extenso (nunca
   "nós"/"a plataforma" sozinho).
3. **Off-page pesa mais que on-page.** Menções da marca fora do site (YouTube ~0,737 de
   correlação — sinal nº 1 em 2026; menções web 0,656–0,709; backlinks só ~0,2) e presença
   em diretórios de review (Capterra/G2/B2B Stack ≈ portão binário de inclusão para software
   B2B) decidem se a marca entra no conjunto que a IA considera.
4. **Só fatos extraíveis entram na resposta da IA.** Preço público em R$, limites de plano,
   features reais. "Fale com vendas" e adjetivos vagos não são citáveis. E fato errado
   (preço de concorrente desatualizado, estatística sem fonte primária) é risco jurídico
   (CDC/CONAR) e mina a credibilidade — ver regras anti-over-claiming abaixo.

## Processo

### 1. Extrair fatos reais do produto (nunca inventar)

Do repo/produto: o que existe HOJE (features com nome da UI), planos com preço em R$ e
limites, postura de segurança/privacidade real, público e papéis. Feature planejada não
entra; postura jurídica em rascunho vira "construído com a LGPD em mente", nunca
"compliance certificado".

### 2. Definir a frase-entidade canônica

Uma frase de ~40-60 palavras: **[Nome] é um [categoria em PT-BR] para [público
hiperespecífico], que faz [3-5 capacidades nas palavras do nicho], a partir de R$ X/mês**.
Hiperespecífico vence: "para arquitetos autônomos e pequenos escritórios", não "para o
mercado de construção". Essa frase idêntica vai em: title/H1/answer-first da LP, rodapé,
diretórios, LinkedIn, Instagram, YouTube, press kit. Consistência entidade↔nicho é o que
faz o modelo recomendar para o perfil certo.

### 3. Escrever a LP (padrões em `references/copywriting-geo.md`)

- Title/H1 com a query exata do nicho; bloco answer-first logo após o hero.
- Headings-pergunta; resposta nas 2 primeiras frases; seções autocontidas.
- Página/seção de **preços com números em R$** (nunca esconder preço).
- **FAQ com 8-12 perguntas na linguagem real do usuário**, respostas de 50-100 palavras.
- "Atualizado em <mês/ano>" visível + revisão trimestral agendada.
- Estatísticas com fonte e ano; sem keyword stuffing (piora o resultado, medido).

### 4. Higiene técnica (checklist em `references/config-tecnica.md`)

robots.txt permissivo aos bots de IA (lista de user-agents verificada no reference) +
sitemap.xml + canonical + meta/OG factuais + JSON-LD inline (Organization,
SoftwareApplication com offers em BRL, FAQPage) **sem aggregateRating do próprio site** +
Bing Webmaster Tools/IndexNow + Google Search Console + teste `curl -A` contra o
WAF/CDN/edge real. llms.txt é opcional (15 min, evidência de consumo ~nula).

### 5. Baseline ANTES de divulgar (métodos em `references/off-page.md`)

Planilha com 10-15 prompts fixos em PT-BR rodados mensalmente em ChatGPT, Perplexity,
Gemini e Claude: registrar se/como a marca é citada e QUAIS fontes o engine usa (essas
fontes viram os alvos de outreach). Sem baseline, impossível atribuir resultado.

### 6. Off-page na ordem de custo-benefício (detalhe em `references/off-page.md`)

(1) Diretórios de review com a frase-entidade + reviews orgânicos de early adopters;
(2) **listicle próprio honesto** "Melhores X para Y (ano)" — formato nº 1 em citações
comerciais (~41%); comparativos "vs" são secundários (~4%); (3) outreach para os listicles
de terceiros que o baseline mostrou que as IAs citam; (4) **YouTube em PT-BR com a
frase-entidade em título/descrição/transcrição** (prioridade alta, não média); (5) Wikidata
+ página Sobre com CNPJ/equipe; (6) imprensa tech quando houver marco.

### 7. Medir e manter

KPIs: share of voice nos prompts do baseline, referral de IA (user-agent/UTM), signups
atribuídos. Refresh trimestral de LP/preços/listicle (frescor é sinal de scoring: conteúdo
citado é ~25,7% mais recente; sem refresh, ~3x mais chance de perder citação).

## Regras anti-over-claiming (aplicar em TODO conteúdo)

- Número de concorrente: só com **fonte primária datada e visível**; se o concorrente não
  publica preço, dizer exatamente isso ("não publica preço; venda por contato comercial").
- Nunca `aggregateRating`/estrelas do próprio produto no próprio domínio (política Google
  contra self-serving reviews; prova social citável vem de diretórios terceiros).
- Reviews só orgânicos (Capterra/G2 proíbem incentivo); conteúdo pago sempre com disclosure.
- Estatística de marketing reciclada (sem estudo primário localizável) não vai a público.
- Feature futura não entra na LP; postura jurídica descrita com precisão.
