# Off-page para IA — menções, diretórios, YouTube, comunidades, medição

O maior preditor de visibilidade em respostas de IA é o que existe FORA do site (Ahrefs
dez/2025, 75k marcas: menções no YouTube ~0,737 de correlação — sinal nº 1; menções web
0,656–0,709; backlinks só ~0,15–0,25). Correlação ≠ causação, mas a direção é consistente
em todos os estudos 2025-26: para domínio novo sem autoridade, menção em fonte de terceiro
vale mais que página própria.

Contexto B2B: 51% dos compradores B2B já começam a pesquisa num chatbot (G2, nov/2025);
1/3 comprou de marca que não conhecia antes — a janela de entrada para marcas novas.

## 1. Diretórios de review — portão binário de inclusão

Pesquisa Quoleady (jun/2026): 100% das ferramentas citadas pelo ChatGPT em queries de
software B2B tinham perfil no Capterra e 99% no G2. Sem perfil, a marca tende a nem entrar
no conjunto considerado. Volume de reviews NÃO determina posição (relevância e consistência
pesam mais) — 10-20 reviews orgânicos bastam para existir.

- Ordem para BR: **B2B Stack** (citado em respostas PT-BR), **Capterra/GetApp em PT-BR**,
  **G2**, Google Business Profile. (G2 comprou Capterra/GetApp/Software Advice em fev/2026
  — é um canal só agora.)
- Mesma **frase-entidade** em todos; categoria certa; preço público; screenshots.
- Reviews: programa de early adopters (acesso em troca de USO real e feedback) e pedido de
  review pós-onboarding por e-mail — **sem incentivo/pagamento** (políticas das plataformas
  proíbem; review comprado descoberto vira menção negativa que as IAs também leem).

## 2. Listicles de terceiros (outreach dirigido pelo baseline)

Em queries comerciais os engines sintetizam o consenso de listicles existentes. Processo:
1. Rodar os prompts do baseline com busca ativa e anotar QUAIS artigos são citados.
2. Priorizar portais neutros (não blog de concorrente) que listam 3+ concorrentes.
3. Oferecer kit pronto: frase-entidade, descrição de 100 palavras, screenshots, preço,
   acesso de teste. Facilitar ao máximo a inclusão.
4. Advertorial/review pago em canais do nicho: sempre com disclosure de conteúdo pago.

## 3. YouTube — prioridade ALTA (não média)

Evidência 2026: menções no YouTube são o sinal com maior correlação de visibilidade em IA
(~0,737) e o YouTube é a fonte nº 1 do Perplexity (32,4% das citações, Ahrefs jun/2026;
Reddit caiu para 16,6%). Transcrição conta como texto.

- 4-6 vídeos curtos respondendo queries reais do nicho, com a marca + categoria no TÍTULO,
  descrição com a frase-entidade + link, e legenda/caption revisada (a transcrição é lida).
- Vale mais que blog próprio para mover visibilidade em IA no curto prazo.

## 4. Comunidades — com regra anti-astroturfing

Reddit importa nos dois engines (mais seletivamente que em 2025); grupos de
Facebook/WhatsApp e fóruns do nicho influenciam o que terceiros escrevem. Regra: conta
real, participação útil, mencionar a ferramenta só quando responde a dor da thread, nunca
em volume. Um flag público de spam é menção NEGATIVA indexável.

## 5. Sinais de entidade

- **Wikidata**: criar item (software; desenvolvedor; país; público-alvo). A barra de
  notabilidade do Wikidata é MUITO mais baixa que a da Wikipedia (basta fonte estrutural
  externa — registro CNPJ, Crunchbase, diretório). Wikipedia: não priorizar (barra alta).
- Página "Sobre" com CNPJ, endereço, equipe nomeada — torna a entidade resolvível.
- `sameAs` no JSON-LD apontando para todos os perfis.
- Imprensa tech BR (Baguete, Startupi, Exame PME) quando houver marco noticiável — é o tipo
  de fonte que alimenta o conhecimento paramétrico dos modelos entre treinos.

## 6. Baseline e medição (ANTES de qualquer ação)

- **Planilha de prompts**: 10-15 prompts fixos em PT-BR (ex.: "melhor software de gestão de
  obras para arquitetos", "app para arquiteto acompanhar obra com cliente", "alternativa
  barata a [líder] para arquiteto autônomo"), rodados mensalmente em ChatGPT, Perplexity,
  Gemini e Claude. Registrar: a marca aparece? em que posição? com que descrição? QUAIS
  fontes o engine citou (→ alvos de outreach).
- Ferramentas: HubSpot AEO Grader (grátis, snapshot de share of voice/sentimento);
  Otterly.ai (~US$29/mês) quando houver volume; Profound é enterprise (US$499+) — pular.
- KPIs: share of voice por prompt; tráfego referral de IA (user-agent + utm nos links de
  diretórios); signups atribuídos; relatório "AI Performance" do Bing Webmaster Tools.
- Cadência: mensal. Sem baseline anterior às mudanças, nada é atribuível.

## 7. Sequenciamento realista (time de ~1 pessoa, 90 dias)

1. **Semana 1-2**: site estático no ar + higiene técnica + baseline registrado.
2. **Semana 3-4**: diretórios (B2B Stack, Capterra, G2, Google Business) + Wikidata + Sobre.
3. **Mês 2**: listicle próprio + 2 conteúdos pilar nas lacunas do nicho + primeiros vídeos.
4. **Mês 3**: outreach para listicles de terceiros (guiado pelo baseline) + reviews de
   early adopters + medição do 1º ciclo.
Comparativos "vs", cluster completo de artigos e imprensa: 2ª onda (mês 4+).
