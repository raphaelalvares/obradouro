# Copywriting para GEO — como escrever texto que IAs citam

Fontes-chave (verificadas jul/2026): estudo GEO Princeton/IIT/AI2 (KDD 2024,
arxiv.org/abs/2311.09735, 10k queries — único estudo acadêmico de larga escala; replicações
2025-26 confirmam a direção); Ahrefs "freshness" (17M citações, 2025); Ahrefs/Glen Allsopp
(dez/2025, 26.283 URLs de 750 prompts comerciais); Wix AI Search Lab/Peec AI (mar/2026, 1,06M
citações); Ahrefs brand-visibility (dez/2025, 75k marcas).

## 1. Escreva para retrieval em nível de chunk

LLMs recuperam TRECHOS por embedding, não páginas. Cada seção deve sobreviver sozinha:

- **Heading em forma de pergunta específica** ("Quanto custa um software de gestão de obras
  para arquitetos?"), não rótulo genérico ("Preços", "Recursos"). Headings são fronteiras de
  chunking e viram metadados do embedding.
- **Resposta nas 2 primeiras frases** (~40-60 palavras) de cada seção; detalhe depois
  (answer-first). O usuário da IA nunca vê o resto se o começo não responde.
- **Parágrafo autocontido**: a entidade nomeada por extenso + categoria na mesma frase
  ("O Obra D'Ouro é um software de gestão de obras para arquitetos que..."). Proibido
  "ele/isso/nós" referindo a seção anterior — o chunk chega ao modelo sem o contexto.
- **Listas e tabelas HTML reais** (`<ul>`, `<table>`) — extraíveis; imagem de tabela não é.

## 2. As 3 táticas com maior efeito medido (Princeton/KDD 2024)

1. **Estatísticas com fonte e ano**: +41% de visibilidade. Prefira dado proprietário
   ("escritórios no produto registram em média N fotos/obra") — vira citável COM a marca.
2. **Citações de especialistas nomeados** (+28-41%): nome + credencial + aspas.
3. **Citar fontes externas confiáveis inline** (+115% justamente para domínios mal
   ranqueados — o caso de domínio novo): linkar CAU/BR, IBGE, gov.br, normas.

Anti-tática medida: **keyword stuffing PIORA** o resultado. Densidade natural.

## 3. Formatos por probabilidade de citação (intent comercial, Wix/Peec mar/2026)

| Formato | Share de citações (comercial) | Prioridade |
|---|---|---|
| Listicle "melhores X para Y (ano)" | ~40,9% | **1ª — pilar** |
| Listas não-blog (diretórios G2/Capterra etc.) | alto | via off-page |
| Discussões (Reddit/fóruns) | ~17% no Perplexity | via off-page |
| Comparação "X vs Y" | ~4% | 2ª onda |
| "Alternativas a Y" | ~0,5% | 2ª onda |

O listicle próprio deve ser HONESTO: 8-10 opções reais com critérios declarados, tabela,
"para quem é cada um", incluindo a própria ferramenta no segmento onde ela ganha de verdade.
Listicle-panfleto não é citado.

## 4. FAQ

8-12 perguntas com a formulação REAL do usuário (como ele digita/fala, com os termos do
nicho), respostas autocontidas de **50-100 palavras**. O valor está no TEXTO visível no
HTML; o markup FAQPage é higiene barata (Google removeu FAQ rich results em mai/2026, mas
manter o markup não prejudica e outros serviços leem).

## 5. Frescor (sinal explícito de scoring)

- Conteúdo citado por IA é ~25,7% mais recente que o top orgânico (Ahrefs, 17M citações);
  no ChatGPT, ~76% das páginas mais citadas foram atualizadas em <30 dias.
- "Atualizado em <mês de ano>" visível no topo + `datePublished`/`dateModified` no JSON-LD.
- Revisão trimestral agendada das páginas-chave (preços, listicle, LP): atualizar números,
  ano no título ("em 2026") e screenshots. Sem refresh ≈ 3x mais chance de perder citação.

## 6. Linguagem do nicho (exemplo Obra D'Ouro / arquitetos BR)

Usar os termos que o público realmente busca — corpo, headings, meta, alt-text:
"gestão de obra para arquitetos", "acompanhamento de obra", "diário de obra (RDO)",
"cronograma de obra", "orçamento de obra", "planilha de obra" (porta de entrada de quem
ainda não usa software), "portal do cliente", "app para arquiteto", "quanto cobrar por
acompanhamento de obra". Evitar anglicismos ("workflow", "construction management") e
jargão de incorporadora ("empreendimento", "viabilidade") — jogam a página no cluster
errado (ERP de construtora). Para outra ferramenta: repetir a pesquisa de vocabulário do
nicho antes de escrever.

Enquadramento aprendido (2026): a dor "obra no grupo de WhatsApp" está sem dono, mas há
contra-tendência "gerencie PELO WhatsApp com IA" — o ângulo defensável é "tire a obra do
GRUPO de WhatsApp" (o caos do grupo), não "abandone o WhatsApp".

## 7. E-E-A-T visível

Página "Sobre" com quem está por trás (nome, CNPJ, credenciais, LinkedIn); autor nomeado
com bio em cada artigo; depoimentos com nome + cidade + tipo de escritório; casos com
métrica. IAs desconfiam de site anônimo ao recomendar software que guardará dados de
clientes.

## 8. Anti-over-claiming editorial (obrigatório)

- Toda estatística com fonte + ano. Número que só existe em blogs que se citam em círculo
  (ex.: o "2,8x do Clearscope") não vai a público.
- Preço/dado de concorrente: só de fonte primária, com data visível. Se o concorrente não
  publica preço, escrever isso ("não divulga preço público; contratação por contato
  comercial") — que, aliás, é um contraste citável a favor de quem publica.
- Publicidade comparativa no Brasil: factual, verificável, datada (CDC/CONAR).
- Segurança/jurídico: descrever o que está implementado ("mídia nunca em URL pública",
  "export completo dos dados", "aceite versionado") e dizer "construído com a LGPD em
  mente" enquanto os docs jurídicos não forem versão final de advogado.
