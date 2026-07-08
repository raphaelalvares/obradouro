# Configuração técnica — como ser LIDO pelos crawlers e engines de IA

Verificado em jul/2026 nas docs oficiais (OpenAI developers.openai.com/api/docs/bots;
Anthropic support.claude.com; Perplexity docs.perplexity.ai/docs/resources/perplexity-crawlers;
Google developers.google.com/crawling). User-agents mudam — reconferir a cada ~6 meses.

## 0. Decisão arquitetural: site estático separado do app

Nenhum crawler de IA relevante executa JavaScript (exceção: ecossistema Google, que usa o
render do Googlebot). GPTBot, OAI-SearchBot, ClaudeBot, Claude-SearchBot, PerplexityBot e
os fetchers `*-User` leem só o HTML da primeira resposta, sem retry. Portanto:

- Site de marketing = **HTML estático/SSG** no domínio raiz (`www.dominio.com.br`).
- App SPA = subdomínio (`app.dominio.com.br`), com `noindex` e bloqueio em robots.txt.
- **Teste operacional** (repetir após qualquer mudança de CDN/WAF):
  `curl -A "GPTBot" https://dominio/ | grep "<frase da LP>"` — o texto completo tem que
  estar no HTML bruto. Repetir com `PerplexityBot` e `ClaudeBot`.
- Velocidade é piso de elegibilidade: bots têm timeout de 1-5s; TTFB alvo < 500ms; resposta
  200 direta (sem cadeia de redirects, sem challenge/interstitial JS para esses UAs).
  Cloudflare/WAF "Block AI bots" LIGADO anula tudo — conferir a camada edge.

## 1. Os 3 tipos de bot e o que cada um alimenta

| Tipo | Bots (tokens exatos) | Alimenta |
|---|---|---|
| Treino | GPTBot, ClaudeBot, Meta-ExternalAgent, Amazonbot, Applebot-Extended (token), CCBot | modelos futuros (conhecimento paramétrico) |
| Busca/índice | OAI-SearchBot, Claude-SearchBot, PerplexityBot, Bingbot (alimenta Copilot E ChatGPT Search), Googlebot (AI Overviews/AI Mode) | **ser citado em respostas — os que mais importam** |
| Fetch on-demand | ChatGPT-User, Claude-User, Perplexity-User | página aberta na hora da pergunta do usuário |

`Google-Extended` é um TOKEN de robots.txt (não um crawler; usa o crawl do Googlebot) que
controla treino/grounding do Gemini; não afeta ranking nem AI Overviews. Não bloquear.

## 2. robots.txt de referência

```
# Crawlers de IA — permitidos (queremos ser encontrados e citados)
User-agent: GPTBot
User-agent: OAI-SearchBot
User-agent: ChatGPT-User
User-agent: ClaudeBot
User-agent: Claude-SearchBot
User-agent: Claude-User
User-agent: PerplexityBot
User-agent: Perplexity-User
User-agent: Google-Extended
User-agent: Meta-ExternalAgent
User-agent: Amazonbot
User-agent: Applebot-Extended
User-agent: CCBot
Allow: /

# Todo o resto (inclui Googlebot/Bingbot)
User-agent: *
Allow: /
Disallow: /app/
Disallow: /api/

Sitemap: https://SEU-DOMINIO.com.br/sitemap.xml
```

## 3. JSON-LD (inline no HTML estático, nunca injetado via JS)

Schema é **higiene, não alavanca**: Microsoft (SMX 2025) e Google (2025/2026) confirmam que
ajuda os LLMs deles a entender o conteúdo, mas estudos (Search Atlas dez/2025; Ahrefs
diff-in-diff mai/2026) mostram efeito ~nulo de adicionar schema sobre citações. Implementar
porque é barato e remove atrito; não esperar milagre.

Conjunto para SaaS: `Organization` (name, url, logo, **sameAs** → LinkedIn, Instagram,
YouTube, Capterra/B2B Stack, Wikidata) + `SoftwareApplication` (name, description =
frase-entidade, `applicationCategory: "BusinessApplication"`, `operatingSystem: "Web"`,
`inLanguage: "pt-BR"`, `featureList`, `offers` com `price`/`priceCurrency: "BRL"` por
plano) + `FAQPage` (espelhando o texto visível) + `BreadcrumbList`/`Article` (com author e
datas) nas páginas internas. Validar no Rich Results Test.

**PROIBIDO: `aggregateRating` self-serving** (nota do próprio produto no próprio site) —
política do Google torna inelegível e cheira a spam. Prova social = diretórios terceiros.

FAQ rich results morreram (Google removeu de vez em mai/2026), mas o markup FAQPage é
inofensivo e outros serviços leem; o valor real é o texto visível.

## 4. Indexação

- **Bing Webmaster Tools** (o índice do Bing alimenta Copilot e ChatGPT Search — para site
  novo, é o caminho mais rápido para respostas de IA): verificar site, submeter sitemap,
  acompanhar o relatório "AI Performance". Implementar **IndexNow** (chave na raiz + ping
  em api.indexnow.org a cada publicação). Google NÃO suporta IndexNow.
- **Google Search Console**: verificar + sitemap.
- sitemap.xml só com páginas públicas de valor, `lastmod` real.
- `rel=canonical` auto-referente; uma única versão de URL (https, com/sem www — escolher).
- Title: `[Produto] — [categoria] para [público]`. Meta description ~150 chars factual
  (categoria + público + preço/diferencial), não slogan. OpenGraph + twitter:card completos.

## 5. llms.txt — opcional de 15 minutos, por último

Evidência jul/2026: ~10% de adoção, nenhum provedor grande confirma consumo (Google
declarou que ignora), 97% dos arquivos publicados recebem ZERO requests de bots de IA.
Único uso real: índice de docs para assistentes de código. Se custar 15 min: `/llms.txt`
em Markdown (H1 nome + blockquote resumo + links anotados p/ preços, features, FAQ).
Nunca no lugar de qualquer item acima.
