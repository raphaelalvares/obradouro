# Marketing / GEO — site institucional do Obra D'Ouro

Kit da landing page otimizada para ser citada e recomendada por IAs (ChatGPT, Claude,
Perplexity, Gemini). O guideline completo (processo, copywriting, técnica e off-page) está
na skill `.claude/skills/geo-lp/` — este README é o operacional deste kit.

## O que tem aqui

| Arquivo | O quê |
|---|---|
| `lp/index.html` | LP estática completa: hero "impressione o cliente", answer-first, portal do cliente, recursos com prints, preços, pagamento/assinatura, comparativo, segurança, FAQ (13) e JSON-LD (Organization + SoftwareApplication + FAQPage). Espaços de print `.ph` em `/img/` |
| `lp/robots.txt` | Permissivo para todos os crawlers de IA (lista verificada jul/2026) |
| `lp/sitemap.xml` | Sitemap inicial (atualizar `lastmod` a cada mudança) |
| `lp/llms.txt` | Opcional por completude — evidência de consumo ~nula, não priorizar |

## Domínio já cravado (jul/2026)

- **Site institucional:** `https://obradouro.com.br/` (raiz — é aqui que a LP estática vai).
- **App:** `https://api.obradouro.com.br/` — login em `/login`, cadastro em `/cadastro`,
  termos em `/termos`, privacidade em `/privacidade` (rotas reais do app, confirmadas no código:
  `web/src/app/App.tsx`). O app é um BFF (front + API na mesma origem), por isso fica no subdomínio
  `api.` — separado da LP, como o GEO exige. **Se o app responder em outro host** (ex.:
  `app.obradouro.com.br` ou na própria raiz), buscar `api.obradouro.com.br` e trocar — é 1 token.

## Antes de publicar (ainda pendente)

1. `[RAZÃO SOCIAL]`, `[CNPJ]`, `[CIDADE/UF]`, `[E-MAIL DE CONTATO]` no rodapé e no JSON-LD
   (sinais de entidade/confiança — IAs desconfiam de site anônimo).
2. **Conferir os preços** (R$ 0 / R$ 59 / R$ 179) contra os Stripe Prices reais em produção
   — os valores vieram do seed da migration `0106_reguas_planos.sql`.
3. **Prints reais das telas** em `/img/` (a LP tem espaços marcados `.ph` com o snippet `<img>`
   pronto no comentário logo acima; trocar cada `<div class="ph">…</div>` pelo `<img>`):
   - `/img/hero-portal.png` (~1280×900) — Portal do Cliente / visão do acompanhamento.
   - `/img/pipeline-3d.png` (~1280×820) — pipeline do projeto + aprovação de 3D por cômodo.
   - `/img/orcamento-proposta.png` (~1100×760) — orçamento com versões / proposta.
   - `/img/cronograma-gantt.png` (~1100×760) — cronograma/checklist com Gantt e curva S.
   - `/img/estoque-nfe.png` (~1200×700) — estoque a partir do XML da NF-e.
   - Manter o `alt` fiel ao que a tela mostra (é o texto que sobra para IA/leitor de tela).
4. Criar `og-image.png` (1200×630, preto + ouro, frase-entidade) e `favicon.png` na raiz,
   e copiar o símbolo da marca para `/brand/obradouro-mark.png` (existe em
   `web/public/brand/obradouro-mark.png`) — é o `logo` referenciado no JSON-LD de Organization.
5. Quando os primeiros perfis existirem (LinkedIn, Instagram, YouTube, B2B Stack, Capterra,
   Wikidata), ADICIONAR a propriedade `sameAs` ao JSON-LD de Organization com as URLs
   (ela foi omitida de propósito — array vazio é pior que ausente).
6. **Reconferir cada claim da LP contra o código antes de publicar** — a LP só afirma o que o
   código sustenta hoje (checado por review multi-agente em jul/2026). NÃO reintroduzir os
   over-claims já barrados: export .zip é PARCIAL (fotos + CSV de checklist/estoque por obra),
   não "completo"; **sem** trial/teste grátis, Pix/boleto, cobrança anual, reembolso/garantia,
   2FA, criptografia em repouso, backups garantidos, "dados no Brasil", DPA/DPO, recuperação de
   senha self-service, login com Apple/magic link, assistente com IA (flag off em prod) nem
   "offline". Portal do Cliente é **exclusivo do Mestre**. Se um recurso mudar, atualizar a LP
   nos DOIS lugares (texto visível e JSON-LD).

## Deploy — regras que não podem falhar

- **HTML estático no domínio raiz.** NÃO servir a LP pelo app React: crawlers de IA não
  executam JavaScript. Qualquer host estático serve (Vercel, Cloudflare Pages, o próprio
  EasyPanel com nginx).
- `robots.txt`, `sitemap.xml` e `llms.txt` na RAIZ do domínio.
- **No subdomínio do app** (`api.obradouro.com.br`): publicar um `robots.txt` próprio com
  `User-agent: * / Disallow: /` liberando apenas `/termos` e `/privacidade` (a LP referencia
  essas rotas), e `noindex` nas demais páginas do app — o robots.txt da raiz NÃO alcança o
  subdomínio.
- **Teste de aceite** (repetir após qualquer mudança de CDN/WAF/edge):
  ```
  curl -A "GPTBot" https://obradouro.com.br/ | grep "arquitetos autônomos"
  curl -A "PerplexityBot" https://obradouro.com.br/ -o /dev/null -s -w "%{http_code} %{time_total}s\n"
  ```
  Tem que voltar o texto completo, HTTP 200 direto (sem redirect em cadeia, sem challenge)
  e TTFB < 500ms. Se houver Cloudflare na frente: desligar "Block AI bots".
- Validar o JSON-LD no Rich Results Test (search.google.com/test/rich-results).
- Cadastrar em **Bing Webmaster Tools** (o índice do Bing alimenta Copilot e ChatGPT
  Search; acompanhar o relatório "AI Performance") e **Google Search Console**; submeter o
  sitemap nos dois. Opcional: IndexNow no Bing.

## Semana 1 — baseline ANTES de divulgar

Criar planilha com 10-15 prompts fixos e rodar mensalmente em ChatGPT, Perplexity, Gemini e
Claude, registrando: a marca aparece? com que descrição? quais FONTES o engine citou (essas
fontes são os alvos de outreach). Sugestão de prompts:

- "melhor software de gestão de obras para arquitetos"
- "app para arquiteto acompanhar obra e mostrar para o cliente"
- "software de obra barato para arquiteto autônomo"
- "como tirar a obra do grupo de WhatsApp"
- "alternativa à planilha de controle de obra"
- "software com diário de obra e fotos"
- "como controlar material de obra pela NF-e"
- "software de gestão para escritório de arquitetura com portal do cliente"

Complemento grátis: HubSpot AEO Grader (1×/mês).

## Plano 90 dias (ordem de dependência)

1. **Sem. 1-2** — LP no ar + testes de aceite + BWT/GSC + baseline registrado.
2. **Sem. 3-4** — Perfis com a MESMA frase-entidade em B2B Stack, Capterra/GetApp PT-BR,
   G2 e Google Business; item no Wikidata; página "Sobre" (CNPJ, equipe). Early adopters
   para as primeiras 10-20 reviews ORGÂNICAS (sem incentivo — política das plataformas).
3. **Mês 2** — Listicle próprio honesto "Melhores softwares de gestão de obra para
   arquitetos (2026)" (formato nº 1 em citações comerciais, ~41%); 2 conteúdos pilar nas
   lacunas sem dono: "quanto cobrar por acompanhamento de obra em 2026" e "como tirar a
   obra do grupo de WhatsApp"; primeiros 2-3 vídeos no YouTube com a frase-entidade em
   título/descrição/transcrição (YouTube = sinal nº 1 de visibilidade em IA em 2026).
4. **Mês 3** — Outreach para os listicles de terceiros que o baseline mostrou que as IAs
   citam (kit pronto: frase-entidade, descrição 100 palavras, screenshots, preço, acesso de
   teste); advertoriais em canais de arquitetos SEMPRE com disclosure; 1º ciclo de medição.

Comparativos "Obra D'Ouro vs X", cluster completo de artigos e imprensa: 2ª onda (mês 4+),
e só com fatos de fonte primária datada (ver regras anti-over-claiming na skill).

## Frase-entidade canônica (usar IDÊNTICA em todo lugar)

> O Obra D'Ouro é um software brasileiro de gestão de obras e projetos para arquitetos
> autônomos e pequenos escritórios: cronograma e checklist de obra, diário de obra com
> fotos, revisões de projeto com aprovação do cliente, orçamentos, portal do cliente e
> controle de material por NF-e — grátis para começar, com preços públicos a partir de
> R$ 59/mês.

Site, rodapé, diretórios, LinkedIn, Instagram, YouTube, press kit: sempre esta frase.
Nunca "para construtoras" (joga a marca no cluster errado, dominado por ERPs).

## Cadência de manutenção

- Revisão TRIMESTRAL da LP: números, "Atualizado em <mês/ano>" (aparece 2× no HTML),
  `lastmod` do sitemap, screenshots. Frescor é sinal de scoring — sem refresh, ~3x mais
  chance de perder citação.
- Reconferir a lista de user-agents do robots.txt a cada ~6 meses (bots mudam).
- Rodar a planilha de prompts todo mês; fontes citadas novas = novos alvos de outreach.

## O que NÃO fazer (aprendizados verificados da pesquisa)

- ❌ `aggregateRating`/estrelas do próprio produto no próprio site (política Google).
- ❌ Citar preço de concorrente sem fonte primária datada (ex.: o "R$ 103/mês da Vobi"
  circula em blogs, mas a Vobi NÃO publica preço em 2026 — dizer exatamente isso:
  "não divulga preço público", que aliás é contraste a nosso favor).
- ❌ Reviews incentivados/pagos em diretórios; menção-spam em comunidades (flag público
  vira menção negativa indexável).
- ❌ Prometer feature que não está em produção (ex.: assistente IA — flag desligada em
  prod; offline — planejado, não pronto; limite de revisões por plano — chave inerte).
  Reconferir claim a claim contra o código a cada mudança (item 7 do "Antes de publicar").
- ❌ Keyword stuffing (medido: PIORA a citabilidade).
