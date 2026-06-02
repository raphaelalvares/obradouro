# Briefing LGPD para Consultoria Jurídica — Projeto CRIA

> **AVISO IMPORTANTE — ISTO NÃO É ACONSELHAMENTO JURÍDICO.**
> Este documento é um **briefing técnico-operacional** preparado para orientar a contratação e o trabalho de um(a) **advogado(a) especializado(a) em LGPD**. Ele organiza, por tema, o contexto do produto CRIA, os pontos de atenção com a respectiva referência legal e — sobretudo — as **perguntas e decisões concretas** que precisam ser resolvidas **antes do lançamento**. As conclusões aqui são preliminares e não substituem parecer jurídico formal. Onde há incerteza regulatória ou lacuna na lei, isso está sinalizado expressamente como **dúvida a confirmar**.

## Sumário do produto (contexto para o(a) advogado(a))

- **CRIA / GoIdea**: SaaS de **gestão de obra para arquitetos** no Brasil — app Flutter (cliente/prestador), painel web React (arquiteto) e backend Python.
- **Arquiteto**: assina e **paga** a plataforma; cadastra clientes e prestadores; opera os dados da obra.
- **Cliente**: dono da obra/imóvel; **titular** dos dados da reforma, **inclusive fotos do interior do imóvel dele**.
- **Prestador**: executa serviços; sobe fotos/observações no checklist.
- **Infraestrutura**: mídia no **Google Drive** (service account + Shared Drives); banco/Auth no **Supabase** (Postgres); backend em **VPS Hostinger via EasyPanel**; painel web na **Vercel**; push via **Firebase Cloud Messaging (FCM)**.
- **Decisão deliberada de minimização**: **não coletar CPF**.
- **Política de produto já definida**: ao **cancelar**, o arquiteto **perde acesso imediato**; os dados são empacotados em **.zip disponível por 30 dias** e depois **expurgados de verdade** (inclusive do Drive). Cliente e prestador daquela obra **perdem acesso junto**.
- **Tensão central conhecida**: a foto é do **CLIENTE** (titular), mas quem cancela a conta é o **ARQUITETO** (contratante).

---

## Tema 1 — Papéis LGPD (controlador / operador / titular) e DPA

### (a) Contexto aplicado ao CRIA
A LGPD **não classifica empresas, e sim cada operação de tratamento**: o mesmo agente pode ser controlador de umas operações e operador de outras. No modelo SaaS B2B dominante, o cliente do SaaS (o **arquiteto**) tende a ser **controlador** dos dados que insere, e a plataforma (**CRIA**) é **operadora**, pois trata "por conta de" e "segundo instruções" do arquiteto. Porém o CRIA também trata dados para **finalidades próprias** — faturamento da assinatura, autenticação (Supabase), analytics, push (FCM) e, crucialmente, as **decisões de produto** (retenção de 30 dias, expurgo, perda de acesso de cliente/prestador) — e nesses pontos age como **controlador (ou cocontrolador)**. O **cliente** e o **prestador** são **titulares**; o cliente provavelmente **não** é controlador, mas isso precisa ser confirmado (é o coração da tensão do produto). Google, Supabase, Vercel e Firebase são **sub-operadores** contratados pelo CRIA.

### (b) Pontos relevantes com referência legal
- **Definição dos papéis**: Art. 5, VI (controlador = "a quem competem as decisões referentes ao tratamento"), VII (operador = "realiza o tratamento em nome do controlador"), IX (agentes de tratamento). **Verificado**: citações conferem com o texto oficial.
- **Operador segue instruções**: Art. 39.
- **Decisões de produto como ato de controlador**: a decisão de **expurgar em 30 dias** e a **perda de acesso imediato** do cliente/prestador são **políticas da plataforma**, não instruções do arquiteto — logo o CRIA age como **controlador** desses atos e responde por eles. Não se pode escudar dizendo "foi o arquiteto que mandou".
- **Cadeia de sub-operadores**: a LGPD **não tem artigo expresso** definindo "suboperador" (tratado pelo **Guia da ANPD v2.0**, não vinculante). O Guia recomenda **autorização expressa** do controlador para o uso de sub-operadores e o correto repasse de instruções. Sub-operador também responde como operador perante a ANPD (Art. 39; Art. 5, VII).
- **DPA (contrato controlador-operador)**: **não existe artigo da LGPD com o texto literal "DPA é obrigatório"**. A exigência é **derivada** dos deveres de seguir instruções (Art. 39), registro das operações (Art. 37), segurança (Arts. 46-49) e prestação de contas (Art. 6, X). É **prática exigível/recomendada** e prova-chave em fiscalização — não dispositivo expresso.
- **Responsabilidade**: Art. 42, caput; Art. 42, §1, I (operador responde **solidariamente** se descumprir a lei ou não seguir instruções lícitas — equipara-se a controlador); Art. 42, §1, II (controladores diretamente envolvidos respondem solidariamente); Art. 42, §2 (**inversão do ônus da prova** em favor do titular); Art. 43 (excludentes: não realizou o tratamento; não houve violação; culpa exclusiva do titular ou de terceiro).

### (c) Perguntas/decisões para o(a) advogado(a)
1. **Mapeamento operação por operação** — dados de obra inseridos pelo arquiteto; fotos do interior do imóvel do cliente; dados do prestador; dados de faturamento/login/analytics/push: em quais o CRIA é **operador** e em quais é **controlador**? Há operações de **controladoria conjunta** (ex.: retenção/expurgo de 30 dias, política da plataforma que afeta dados do cliente)?
2. O **cliente** é **somente titular** ou pode ser **cocontrolador** das fotos do próprio imóvel?
3. O contrato de assinatura/DPA deve conter **autorização prévia e genérica** para uso de sub-operadores (Google, Supabase, Vercel, Firebase), com dever de notificar mudanças? **Basta** listá-los em anexo/página pública atualizável?
4. O CRIA precisa de **DPA próprio assinado com cada sub-operador** (Google Cloud DPA, Supabase DPA, Vercel DPA), e como comprovar isso à ANPD?
5. Na visão do(a) advogado(a), o **DPA controlador-operador é juridicamente obrigatório ou fortemente recomendado**? Pode estar **embutido nos Termos de Uso** aceitos por clique pelo arquiteto, ou precisa ser **instrumento apartado** assinado? Quais **cláusulas mínimas** são indispensáveis?
6. Nas decisões de produto (expurgo, perda de acesso): como **documentar a fronteira** entre "instrução do arquiteto" e "política da plataforma" para acionar o Art. 43 e afastar a equiparação do Art. 42, §1, I? Qual **base legal** sustenta o expurgo mesmo contra a vontade do cliente-titular?

**Fontes:**
- https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm
- https://lgpd-brasil.info/capitulo_01/artigo_05
- https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/Segunda_Versao_do_Guia_de_Agentes_de_Tratamento_retificada.pdf
- https://www.gov.br/anpd/pt-br/assuntos/noticias/nova-versao-do-guia-dos-agentes-de-tratamento
- https://www.yapoli.com/post/desafios-da-lgpd-em-plataformas-saas-b2b-parte-1
- https://www.migalhas.com.br/coluna/migalhas-de-protecao-de-dados/359575/suboperador-possiveis-solucoes-diante-da-omissao-da-lgpd
- https://farinaeantunes.com.br/blog/contrato-entre-controlador-e-operador-na-lgpd-uma-salvaguarda-para-a-protecao-de-dados/
- https://lgpd-brasil.info/capitulo_06/artigo_42

---

## Tema 2 — Fotos da obra como dado pessoal e titularidade

### (a) Contexto aplicado ao CRIA
Quem faz o upload é o **arquiteto** (e o **prestador** no checklist), mas o dado pessoal pertence às pessoas que a imagem **identifica ou torna identificável**: o **cliente** (dono do imóvel), pessoas retratadas e, potencialmente, o próprio prestador. A imagem do **interior do lar** pode revelar identidade e intimidade **mesmo sem rostos** (objetos, documentos visíveis, layout, localização). **Quem subiu a foto nunca é, por esse ato, o titular dela** — embora possa figurar como controlador/operador, e seja também titular se aparecer identificável na imagem.

### (b) Pontos relevantes com referência legal
- **Dado pessoal e titular**: Art. 5, I (informação relacionada a pessoa natural identificada ou identificável) e Art. 5, V (titular); Art. 2, IV (inviolabilidade da intimidade, honra e imagem). **Verificado** literalmente.
- **Dado sensível por retrato ou por inferência**: Art. 5, II e Art. 11. Fotos podem ser sensíveis (a) por serem biométricas/retrato ou (b) por **inferência** do conteúdo (saúde, religião, origem racial, orientação sexual, opinião política). Fotos do interior de um lar têm **alta probabilidade** de revelar dado sensível por inferência. **Legítimo interesse NÃO serve de base para dado sensível.**
- **Bases legais**: Art. 7 (dado comum — consentimento I, execução de contrato V, legítimo interesse IX); Art. 10 (requisitos do legítimo interesse); Art. 11 (dado sensível — consentimento específico e destacado I, ou hipóteses sem consentimento II). **Atenção**: a execução de contrato (Art. 7, V) é **frágil** aqui porque o contrato é do **arquiteto**, não do **cliente** (titular). Para foto sensível, na prática exige-se **consentimento do cliente**.
- **Crianças/adolescentes**: Art. 14 (melhor interesse; §1 consentimento específico e destacado de pelo menos um dos pais/responsável; §5 esforços razoáveis de verificação; §6 transparência). Obras residenciais frequentemente envolvem lares com crianças — fator de risco duplo (menor + dado potencialmente sensível). Enunciado ANPD de 24/05/2023 e Enunciado 684 da IX Jornada de Direito Civil admitem outras bases dos Arts. 7/11 desde que prevaleça o melhor interesse.
- **Transferência internacional** (ver Tema 5): mídia no Google Drive provavelmente reside no exterior — Resolução CD/ANPD 19/2024.
- **Alto risco → RIPD**: Art. 6, I-III (finalidade, adequação, necessidade/minimização); Art. 10, §3 e Art. 38 (ANPD pode exigir RIPD). Fotos sensíveis em larga escala, com possíveis menores e transferência internacional, têm **perfil de alto risco**.
- **Direitos do titular sobre a foto**: Art. 18, II, III, IV, VI, IX — incluindo **eliminação**, que colide com a política de expurgo controlada pelo arquiteto (ver Tema 3).

### (c) Perguntas/decisões para o(a) advogado(a)
1. Para cada foto/mídia, **quem é o(s) titular(es)** (cliente, pessoas retratadas, prestador) e como documentar essa **pluralidade de titulares numa única mídia** subida por um terceiro?
2. As fotos do interior do imóvel são **dado sensível por padrão** (retrato/inferência) ou **caso a caso**? Que critério **operacional** adotar (ex.: tratar toda mídia de interior como potencialmente sensível) e isso exige base do Art. 11 para todo o acervo?
3. Qual **base legal** para (a) fotos comuns e (b) fotos sensíveis, dado que quem contrata é o arquiteto e quem é titular é o cliente? Será necessário **consentimento específico e destacado do CLIENTE** (e dos pais, no caso de crianças) **diretamente no app** — e como operacionalizar quando quem opera é o arquiteto?
4. Como tratar fotos que possam conter **crianças/adolescentes** — exigir consentimento parental, **instruir o arquiteto/prestador a não subir** tais imagens, ou implementar **salvaguardas** (aviso, marcação, blur, restrição)? Quais "esforços razoáveis" de verificação são exigíveis num app operado por terceiro?
5. O tratamento de fotos é de **alto risco a ponto de exigir RIPD antes do lançamento**? Qual o escopo (incluindo Drive/transferência internacional e dados de crianças)?
6. Quais **limites de finalidade/minimização** devem constar nos termos e na arquitetura (ex.: **vedação de uso das fotos para marketing/treino de IA**)?

**Fontes:**
- https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm
- https://lgpd-brasil.info/capitulo_01/artigo_05
- https://www.conjur.com.br/2022-mai-28/observatorio-constitucional-imagem-dado-pessoal-sensivel/
- https://www.jota.info/opiniao-e-analise/artigos/lgpd-fotos-inferencias-e-a-sensibilidade-de-dados-pessoais
- https://lgpd-brasil.info/capitulo_02/artigo_11
- https://lgpd-brasil.info/capitulo_02/artigo_14
- https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/guia_legitimo_interesse.pdf
- https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/relatorio-de-impacto-a-protecao-de-dados-pessoais-ripd
- https://www.conjur.com.br/2023-nov-17/tratamento-de-dados-de-criancas-e-adolescentes/

---

## Tema 3 — Direitos do titular (Art. 18) e operacionalização no CRIA

### (a) Contexto aplicado ao CRIA
Na prática, o **cliente** clica em algo **dentro do app CRIA** para pedir acesso/correção/eliminação das fotos do seu imóvel. Logo, o pedido chega **primeiro ao CRIA** (operador), não ao arquiteto (controlador). Isso exige um **fluxo definido**: ou o CRIA viabiliza para o arquiteto atender, ou (se contratualmente designado) atende em nome dele. Há ainda direitos **sem prazo legal expresso**, cujo regulamento da ANPD **ainda não foi publicado**.

### (b) Pontos relevantes com referência legal

> **CORREÇÃO IMPORTANTE INCORPORADA (verificação):** circulou no levantamento a ideia de que "o **operador** pode/deve redirecionar" o pedido com base no **Art. 18, §4**. **Isso está incorreto.** O Art. 18, §3 permite que o requerimento seja dirigido a **"agente de tratamento"** (gênero que abrange controlador e operador — Art. 5, IX), mas o **dever de responder e de redirecionar** ("comunicar que não é agente de tratamento e indicar, sempre que possível, o agente") é **expressamente atribuído ao CONTROLADOR** pelo Art. 18, §4. O operador atua **segundo instruções** do controlador (Art. 5, VII; Art. 39) e **não possui dever autônomo de redirecionamento** do §4. **Aplicação ao CRIA:** se o controlador é o **arquiteto** e o CRIA é operador, o pedido do cliente deve ser **tratado pelo controlador (arquiteto)**; o CRIA apenas **repassa/atende conforme instrução contratual**, e não por força do §4. *(A premissa "destinatário = agente de tratamento" procede; a conclusão "o operador redireciona pelo §4" não se sustenta.)*

- **Destinatário e exercício**: Art. 18, caput ("obter do controlador"), §3 (requerimento a agente de tratamento), §4 (resposta/redirecionamento **a cargo do controlador**).
- **Prazos**: **Art. 19** fixa prazo expresso **apenas para confirmação/acesso** ("formato simplificado, imediatamente" OU "declaração clara e completa... no prazo de até 15 dias"). Para **os demais direitos** (correção, eliminação, portabilidade, revogação, informação de compartilhamento), o **Art. 18, §5** remete a "prazos e termos previstos em regulamento" — **regulamento que ainda não existe** (tema prioritário nº 1 da ANPD para 2026-2027, conforme Resolução CD/ANPD nº 30, de 23/12/2025). Adotar **15 dias por analogia** ao Art. 19 é prática de mercado, mas é **decisão jurídica**, não texto legal.
- **Eliminação por revogação (Art. 18, VI; Art. 8, §5)** só se aplica se a base for **consentimento**. Se a base for execução de contrato ou legítimo interesse, o titular tem o direito do **inciso IV** (eliminação de dados desnecessários/excessivos/ilegais) e o de **oposição** (§2), com lógica diferente. **Revogar consentimento não apaga automaticamente** — precisa de pedido de eliminação separado.
- **Portabilidade (Art. 18, V)**: depende de **regulamentação da ANPD** (Art. 40 — padrões de interoperabilidade). Art. 19, §3 dá direito a **cópia eletrônica integral** quando a base for consentimento ou contrato. **O .zip do cancelamento é entregue ao arquiteto** — não necessariamente satisfaz a portabilidade/cópia do **cliente**.
- **Propagação da eliminação**: Art. 18, §6 obriga informar os agentes com quem houve uso compartilhado (Google Drive/Shared Drives, Supabase, FCM) para **repetirem a providência** — o expurgo precisa alcançar lixeira, versões/revisões e backups.
- **Verificação de identidade**: Art. 18, §3 (titular ou representante); Art. 6, III (minimização); Art. 19. **A autenticação no app (Supabase) pode bastar** como identificação do titular **sem pedir CPF/RG**, preservando a minimização. Pedidos **de fora do app** (e-mail externo) e de **representantes/menores** são mais delicados.
- **Revogação facilitada e gratuita**: Art. 8, §5; Art. 18, §5. Exige **botão/fluxo claro no app**, não pedido burocrático por e-mail.
- **Encarregado e canais externos**: Art. 41 e Resolução CD/ANPD nº 18/2024 (atuação do encarregado); Art. 18, §1 (peticionar à ANPD) e §8 (organismos de defesa do consumidor — **CDC em concorrência**, possível responsabilidade objetiva e inversão do ônus).

### (c) Perguntas/decisões para o(a) advogado(a)
1. O fluxo deve **sempre passar pelo arquiteto** (CRIA apenas notifica e fornece ferramentas), ou o DPA deve **autorizar/obrigar o CRIA a executar tecnicamente** certas providências (exportar, corrigir, eliminar) em nome do arquiteto? O que deve constar no DPA sobre **atendimento de direitos, prazos internos e SLA do arquiteto**?
2. Que **prazo interno** o CRIA deve prometer no canal e na Política para os direitos **sem prazo legal expresso**? Adotar **15 dias por analogia** ao Art. 19? Qual o **prazo do arquiteto** quando o CRIA repassa, sem estourar o prazo total perante o titular? Como deixar o produto **adaptável ao futuro regulamento da ANPD**?
3. Qual a **base legal de cada categoria** (cadastro do cliente, fotos do interior, observações/fotos do prestador, documentos de projeto no Drive)? Sendo consentimento, como conciliar a **eliminação imediata** pedida pelo cliente com a **retenção** desejada pelo arquiteto (portfólio/prova de serviço)?
4. É necessário **canal/função para o cliente exercer direitos sobre as próprias fotos independentemente do arquiteto**? Se o cliente pede eliminação durante a obra ativa, **quem decide** (arquiteto-controlador) e **em que prazo**, e o CRIA executa?
5. O **.zip atende à portabilidade/cópia integral** do cliente (formato, destinatário, escopo)? É preciso uma **exportação específica para o cliente**, separada do pacote de cancelamento do arquiteto? Que **formato** adotar antes de a ANPD definir padrões (Art. 40)?
6. A **autenticação no app é suficiente** como verificação de identidade sem coletar CPF/RG? Como tratar **pedidos de fora do app** e de **representantes/menores**? Qual o documento mínimo aceitável?
7. O CRIA deve **indicar e publicar encarregado próprio**? Cada arquiteto também precisa? Há **canal centralizado** que repassa ao arquiteto sem sobrecarregar microempreendedores (atendendo Resolução 18/2024 e Art. 41)?
8. Como a **sobreposição LGPD + CDC** afeta a responsabilidade do CRIA e do arquiteto? Que **cláusulas e logs de atendimento** demonstram diligência e mitigam a solidariedade do Art. 42?
9. Como **garantir e documentar** que correção/eliminação se propaga ao Google Drive (lixeira/versões/backup), Supabase e Firebase (Art. 18, §6)?
10. O fluxo de **revogação** precisa estar embutido no app de forma facilitada (botão), e como explicar ao cliente que **revogar não elimina automaticamente** sem induzir a erro?

**Fontes:**
- https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm
- https://lgpd-brasil.info/capitulo_03/artigo_18
- https://www.gov.br/anpd/pt-br/assuntos/titular-de-dados-1/direito-dos-titulares
- https://blog.bcompliance.com.br/2025/10/16/regulamentacao-direitos-dos-titulares-anpd/
- https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/atos-normativos/regulamentacoes_anpd
- https://privacidade.mpba.mp.br/requisicao-de-direitos-dos-titulares/
- https://www.brunomiragem.com.br/wp-content/uploads/2020/06/002-LGPD-e-o-direito-do-consumidor.pdf

---

## Tema 4 — Retenção, eliminação e a regra "cancelou, perde tudo"

### (a) Contexto aplicado ao CRIA
O modelo (perda de acesso imediato no cancelamento → **.zip por 30 dias** → **expurgo real** em banco e Drive; cliente/prestador perdem acesso junto) está alinhado à **regra geral de eliminação** após o término do tratamento, mas precisa ser **enquadrado nas hipóteses legais** e ter o **prazo justificado**. Aqui mora a **tensão central**: o expurgo é disparado pelo **arquiteto**, mas atinge dados do **cliente-titular**.

### (b) Pontos relevantes com referência legal
- **Eliminação é regra; conservação é exceção**: Art. 15 (término do tratamento) e **Art. 16**, incisos I a IV (hipóteses **exaustivas** de conservação: I obrigação legal/regulatória; II estudo por órgão de pesquisa com anonimização; III transferência a terceiro nos requisitos da lei; IV uso exclusivo do controlador, vedado acesso de terceiros, anonimizado); Art. 5, XIV (definição de eliminação). **Verificado**. *Nuance: a lei não usa a palavra "taxativa"; trata-se de leitura doutrinária/ANPD consolidada de rol exaustivo — não citação literal.*
- **A LGPD não fixa prazo de retenção**: a própria **FAQ da ANPD (item 5.5)** afirma que a lei não especifica prazo, "o que dependerá da circunstância e da finalidade". Os **30 dias** precisam de **justificativa de necessidade documentada** (janela razoável de download/portabilidade) — Art. 6, III (necessidade) e V (qualidade); Art. 15, I.
- **Direitos do cliente x expurgo do arquiteto**: Art. 18, II/IV/V/VI; Art. 17 (titularidade). O titular pode, **a qualquer momento**, pedir acesso, eliminação, portabilidade — independentemente do cancelamento do arquiteto. "Cliente perde acesso quando o arquiteto cancela" **não pode anular** os direitos do titular.
- **Expurgo em cadeia**: Art. 18, §6 (comunicar a eliminação aos agentes com quem houve compartilhamento); Art. 5, XIV; Arts. 46-47 (segurança). O expurgo prometido ("inclusive do Drive") só se cumpre se alcançar **lixeira, versões/revisões, backups do Supabase e caches** — sob pena de descumprimento do Art. 16/18 **e** de **propaganda enganosa/quebra contratual**.
- **Base legal das fotos do cliente**: Art. 7 (incl. IX legítimo interesse), Art. 10, Art. 11; **Guia ANPD de Legítimo Interesse (02/02/2024)** — teste de balanceamento em 3 fases. **Dúvida explícita**: fotos do interior podem tangenciar dado sensível/intimidade, hipótese em que **legítimo interesse não se aplica**.
- **Transparência prévia**: Art. 6, VI e IV; Art. 9 (finalidade, **forma e duração**, identificação do controlador, compartilhamento, direitos). A regra "cancelou, perde tudo" e a retenção/expurgo devem estar **declaradas antes do aceite**.
- **Mídia multi-titular** (lacuna): Art. 18 c/c Art. 16. **A LGPD não disciplina mídia com múltiplos titulares** — zona de interpretação a resolver.
- **Accountability e sanção**: Art. 6, X; Art. 37 (ROPA); Arts. 50-51 (boas práticas); Art. 52 (sanções); **Resolução CD/ANPD nº 4/2023** (Dosimetria — multa de até 2% do faturamento, limitada a R$ 50 mi por infração; boa-fé e boas práticas como atenuantes).

### (c) Perguntas/decisões para o(a) advogado(a)
1. O **expurgo total após 30 dias** é compatível com eventuais **prazos legais de guarda** (prescrição cível do Código Civil; logs de acesso a aplicação do **Marco Civil da Internet**; dados de faturamento/pagamento do arquiteto)? Que dados/metadados devem ser **retidos** (anonimizados ou não) e sob **qual inciso do Art. 16**?
2. O **.zip de 30 dias** é "conservação" (Art. 16) ou apenas mecanismo de **devolução** ao titular? Qual inciso o sustenta?
3. **30 dias** é prazo **proporcional** para arquiteto **e** cliente recuperarem dados de uma obra inteira (fotos pesadas no Drive)? Devemos **documentar a justificativa** no ROPA/política de retenção? Há risco de a ANPD considerá-lo **curto demais para o CLIENTE**, que pode nem saber do cancelamento?
4. Antes do expurgo, o **cliente (e o prestador) precisa ser notificado de forma independente** do arquiteto e ter **janela própria** para baixar/portar? O **.zip vai só ao arquiteto** ou também ao cliente? **Entregar a mídia do interior do cliente ao arquiteto cancelante é, ele próprio, um compartilhamento** que exige base legal?
5. Se o cliente pedir para **manter** suas fotos após o cancelamento do arquiteto, o CRIA pode/deve atender, e **sob qual base** manteria (já que o vínculo era com o arquiteto)?
6. Qual a **base legal das fotos/observações do cliente e do prestador**, dado que o contrato é do arquiteto? Há **aceite/consentimento próprio** do cliente e do prestador, separado do arquiteto? Foi (ou precisa ser) feito o **teste de balanceamento** de legítimo interesse?
7. O fluxo técnico de expurgo cobre **lixeira/versões/backups/caches** e é **comprovável** (log/atestado)? Qual o **prazo máximo** entre gatilho e eliminação efetiva em todas as camadas, e isso **bate com a promessa dos Termos**? O contrato com o Google prevê **eliminação a comando** e os prazos de retenção de backup do próprio Google?
8. **Mídia multi-titular** (lacuna a decidir interpretativamente): como tratar no expurgo em bloco e num pedido individual de eliminação? O **prestador** tem direito de manter prova/portfólio após o cancelamento? É necessária **autorização de uso de imagem** de pessoas retratadas, além da base LGPD?
9. Que **documentação mínima** de retenção/expurgo/aceites manter para accountability? Convém **RIPD**? Precisamos **indicar Encarregado** e canal acessível também a cliente/prestador?

**Fontes:**
- https://lgpd-brasil.info/capitulo_02/artigo_16
- https://lgpd-brasil.info/capitulo_02/artigo_15
- https://www.gov.br/anpd/pt-br/acesso-a-informacao/perguntas-frequentes/perguntas-frequentes/5-adequacao-a-lgpd/5-5-por-quanto-tempo
- https://lgpd-brasil.info/capitulo_03/artigo_18
- https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/guia_legitimo_interesse.pdf
- https://www.gov.br/anpd/pt-br/assuntos/noticias/anpd-publica-regulamento-de-dosimetria
- https://jus.com.br/artigos/68276/lgpd-responsabilidade-dos-agentes-de-tratamento-pela-eliminacao-de-dados-pessoais-compartilhados

---

## Tema 5 — Transferência internacional de dados (Capítulo V)

### (a) Contexto aplicado ao CRIA
O CRIA usa pelo menos **quatro fornecedores estrangeiros** (Google Drive, Supabase, Vercel, FCM). Armazenar/processar dados — especialmente **fotos do interior do imóvel** — em infraestrutura no exterior configura **transferência internacional**, que exige **base/mecanismo de transferência do Art. 33 ALÉM da base de tratamento** (camadas cumulativas). A **escolha de região** de cada provedor é, portanto, uma **decisão de arquitetura com impacto jurídico direto**.

### (b) Pontos relevantes com referência legal
- **Definição e regime**: Art. 5, XV; Arts. 33 a 36. **Verificado**: a operação exige **duas camadas cumulativas** — base de tratamento (Art. 7/11) **e** mecanismo de transferência (Art. 33). *Nuance: o Art. 33 traz "hipóteses/mecanismos de transferência", não "base legal" no sentido estrito; a substância da dupla exigência está correta.* O enquadramento depende da **localização efetiva** dos dados e da **região contratada** — a mera origem estrangeira do fornecedor não basta por si só; **confirmar caso a caso**.
- **Cláusulas-padrão e fim do período de graça**: **Resolução CD/ANPD nº 19/2024** (23/08/2024) aprovou as **cláusulas-padrão contratuais (CPC)** do Anexo II, a serem adotadas **sem modificação**. O **período de graça já encerrou em 23/08/2025** — **não há mais janela de tolerância**. DPAs de fornecedores costumam trazer as **SCC europeias (GDPR)**, que **não são automaticamente válidas no Brasil**.
- **Adequação da UE/EEE**: **Resolução CD/ANPD nº 32/2026 (26/01/2026)** reconheceu **nível adequado** de proteção para a **União Europeia e o EEE** (Islândia, Liechtenstein, Noruega). Transferências para a UE/EEE passam a usar o **Art. 33, I, sem cláusulas-padrão**. Hoje a UE/EEE é o **único** território/organismo com decisão de adequação; **EUA não têm**. **Reavaliação em 4 anos** → risco temporal.
- **Por fornecedor**:
  - **Google Drive/Workspace**: data regions só **EUA ou Europa** (não há Brasil). Configurar **Europe** enquadra no Art. 33, I; caso contrário, cláusulas-padrão para os EUA. **Cobertura parcial** das data regions (dados em repouso de serviços específicos; metadados/alguns processamentos podem ficar fora).
  - **Supabase**: permite **São Paulo (sa-east-1)** — manter o banco no **Brasil elimina a transferência do dado primário**. Resíduo possível em suporte/backups/réplicas/logs/Edge Functions.
  - **Vercel**: oferece **gru1 (São Paulo)** para funções, mas é **CDN/edge global** — cache/execução tendem a ser internacionais. Difícil confinar ao Brasil.
  - **FCM**: **não permite escolher região** e processa em "infraestrutura global do Google" (provável EUA/destino indefinido). **Única via prática: cláusulas-padrão (DPA Google) + minimização** do payload.
- **Consentimento como base de transferência (Art. 33, VIII)**: possível, mas **frágil** — revogável a qualquer tempo; difícil de obter de forma robusta do cliente. Deve ser reservado à **transparência**, não como base única da infraestrutura.
- **Eliminação no exterior**: Art. 33 c/c Art. 18, VI e Art. 16 — as CPC/DPAs devem assegurar **eliminação verificável no importador** (backups/cache no exterior), compatível com a política de 30 dias.
- **Transparência da transferência**: Art. 9, V e Art. 6, VI — informar **arquiteto, cliente e prestador** sobre quais dados vão ao exterior, para quais fornecedores/países e sob qual mecanismo.

### (c) Perguntas/decisões para o(a) advogado(a)
1. Para **cada fornecedor**, qual **inciso do Art. 33** será invocado (I país adequado; II cláusulas-padrão; VIII consentimento)? Confirmar que a base de transferência é tratada **separadamente** da base de tratamento.
2. Os DPAs atuais de Google, Supabase, Vercel e Firebase contemplam as **cláusulas-padrão brasileiras (Anexo II, Res. 19/2024)** ou só as **SCC europeias**? Se só europeias, é preciso **aditivo** incorporando as CPC brasileiras sem modificação? **Quem assina** (CRIA, arquiteto, ambos)?
3. Devemos adotar como **padrão de arquitetura hospedar tudo configurável na UE/EEE** (Art. 33, I) e/ou **Supabase em São Paulo**, em vez de cláusulas-padrão? Há contraindicação (latência, custo, soberania)?
4. **Google Workspace**: exigir **Data Region = Europe** e plano que o suporte? A cobertura das data regions abrange **todos** os dados do fluxo (arquivos no Shared Drive + metadados) ou sobra processamento fora da UE? O **DPA do Google traz as CPC brasileiras**?
5. **Supabase-BR**: ainda há transferência via **suporte/acesso da equipe, backups ou logs** fora do Brasil? Qual base cobre o resíduo?
6. **Vercel**: restringir a gru1/UE e tratar a edge global como transferência coberta por CPC, **ou** minimizar dado pessoal no front e processar tudo no backend BR?
7. **FCM**: confirmar apoio em cláusulas-padrão (DPA Google) e **proibir dados pessoais no payload** (notificação genérica + fetch no backend BR). O **token FCM** é dado pessoal para fins de transferência?
8. **Descartar o consentimento (Art. 33, VIII)** como base da infraestrutura, usando-o só para transparência, e adotar **adequação UE + cláusulas-padrão**?
9. Qual o **mapa definitivo de papéis** (exportador BR x importador exterior) por tipo de dado, e **quem comprova as garantias do Art. 33** à ANPD?
10. As CPC/DPAs garantem **eliminação efetiva e verificável no exterior** (backups/cache) compatível com os 30 dias? Se o cliente pedir eliminação antes do cancelamento do arquiteto, **quem prevalece**?
11. Como **informar cliente e prestador** (que não contratam o CRIA) sobre a transferência — basta a política aceita no app, ou é preciso aviso no convite/upload?
12. **Dúvida a confirmar (não assumir)**: com Supabase-BR + Vercel/Google-UE, ainda haveria **qualquer dado/acesso para país não adequado** (ex.: suporte/engenharia nos EUA)? O **FCM obriga, de qualquer modo, a manter cláusulas-padrão**? Como mitigar o risco de a **adequação da UE ser revista em 4 anos** (manter CPC de reserva)?

**Fontes:**
- https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm
- https://www.gov.br/anpd/pt-br/assuntos/noticias/resolucao-normatiza-transferencia-internacional-de-dados
- https://www.gov.br/anpd/pt-br/assuntos/assuntos-internacionais/transferencia-internacional-de-dados
- https://www.mayerbrown.com/pt/insights/publications/2025/08/end-of-grace-period-implementation-of-brazils-standard-contractual-clauses-in-international-transfers-of-personal-data
- https://www.gov.br/anpd/pt-br/assuntos/noticias/brasil-e-uniao-europeia-reconhecem-adequacao-mutua-em-protecao-de-dados-pessoais
- https://www.trenchrossi.com/en/legal-alerts/brazil-and-the-european-union-mutually-recognize-adequacy-in-personal-data-protection-resolution-no-32-dated-january-26-2026/
- https://workspace.google.com/products/admin/data-regions/
- https://supabase.com/docs/guides/platform/regions
- https://vercel.com/docs/edge-network/regions
- https://firebase.google.com/support/privacy

---

## Tema 6 — Segurança, incidentes e governança (Art. 46, comunicação de incidentes, ROPA/RIPD, Encarregado)

### (a) Contexto aplicado ao CRIA
A definição de papéis (Tema 1) governa quase todas as obrigações de **segurança, incidente e ROPA**. A obrigação de **comunicar incidente** é do **controlador** (Art. 48); o operador apenas **avisa o controlador sem demora injustificada**. As fotos do interior do imóvel elevam o **perfil de risco** e podem **desenquadrar o CRIA do regime simplificado de pequeno porte**.

### (b) Pontos relevantes com referência legal
- **Papéis governam tudo**: Art. 5, VI/VII/VIII; Art. 37 (ROPA); Arts. 42 e 44 (responsabilização/solidariedade); Art. 48 (comunicação de incidente pelo **controlador**). **Verificado.**
- **Segurança "by design"**: Art. 46 (medidas técnicas e administrativas, "desde a concepção"); Art. 6, VII e VIII. **Guia de Segurança da Informação para Agentes de Pequeno Porte da ANPD (out/2021)** — referência de boas práticas (não vinculante): política de segurança, controle de acesso/senhas, backups, criptografia, atualizações, cuidados com nuvem/terceiros, checklist.
- **Comunicação de incidente**: Art. 48; **Resolução CD/ANPD nº 15/2024** (24/04/2024) — prazo de **3 dias úteis** do conhecimento (**em dobro = 6 dias** para agente de pequeno porte), complementação em até 20 dias úteis, conteúdo mínimo (natureza/categorias, medidas, riscos, contato/encarregado). Vazamento de fotos do interior tende a ser **"risco relevante"**. **Confirmar a redação literal dos arts. 5, 6 e 9 da Resolução no DOU.**
- **Registro interno de incidentes** (inclusive os não comunicados): Resolução 15/2024 — **prazo de guarda a confirmar** (relatado como 5 anos); correlato ao Art. 6, X.
- **ROPA e RIPD**: Art. 37 (ROPA); Art. 5, XVII e Art. 38 (RIPD); **Resolução CD/ANPD nº 2/2022** (art. 9 — ROPA **simplificado** para pequeno porte) e **modelo de ROPA simplificado da ANPD (jun/2023)**. O **alto risco** das fotos pode exigir **ROPA completo + RIPD** e desenquadrar o pequeno porte.
- **Encarregado (DPO)**: Art. 41; Art. 52, §1, IX (boas práticas); **Resolução 2/2022, art. 11** (dispensa para pequeno porte + dever de manter **canal de comunicação** com o titular); **Resolução CD/ANPD nº 18/2024** (atuação do encarregado: PF ou PJ, designação formal, vedação a conflito de interesse, encarregado substituto). **A dispensa depende de NÃO realizar tratamento de alto risco** — se as fotos + escala forem alto risco, a dispensa cai.
- **Sub-operadores e expurgo no exterior**: Arts. 39-40; Arts. 33-36 + Res. 19/2024; Art. 46; Art. 16.

### (c) Perguntas/decisões para o(a) advogado(a)
1. Por categoria de dado, o CRIA é **controlador, cocontrolador ou operador**? O arquiteto é controlador dos dados dos seus clientes/prestadores? Precisamos de **DPA com o arquiteto e com cada subprocessador**?
2. Qual o **conjunto mínimo de medidas do Art. 46** a implementar e documentar antes do lançamento (criptografia em repouso/trânsito, controle de acesso por papel, **logs de acesso às fotos**, gestão da **service account** do Drive, backups, retenção)? Fotos do interior devem ser tratadas como **sensível por precaução**? O Guia de pequeno porte é baseline suficiente ou o risco exige padrão mais alto?
3. **Quem dispara a comunicação à ANPD** num vazamento de fotos — CRIA ou arquiteto? O CRIA é **pequeno porte** (prazo em dobro)? Quais incidentes classificamos previamente como **"risco relevante"**? Como tratar incidentes **originados em fornecedores** (cláusula de notificação imediata)? **Quais titulares** notificar (cliente, prestador, arquiteto) e por **qual canal**?
4. Qual o **prazo de guarda e o conteúdo mínimo** do **registro interno de incidentes** (Res. 15/2024)? Que **template** adotar e como integrar aos logs de Supabase/Drive?
5. O CRIA pode usar **ROPA simplificado** ou o perfil de risco exige **ROPA completo + RIPD**? Qual a **base legal de cada tratamento**? A política de retenção (zip 30 dias + expurgo no Drive) está adequada e refletida no ROPA? O **arquiteto** precisa de ROPA próprio?
6. O CRIA se enquadra como **pequeno porte** (dispensa de encarregado), ou as fotos do interior + escala o desenquadram? Se dispensado, **qual canal** atende o Art. 41, §2, I para cliente/prestador? Vale indicar **encarregado voluntariamente** (e substituto, Res. 18/2024), e pode ser **PJ/terceirizado** sem conflito de interesse?
7. Precisamos de **DPA/cláusulas Arts. 39-40** com Google, Supabase, Hostinger/EasyPanel, Vercel e Firebase? Como **comprovar o expurgo "de verdade"** no Drive (lixeira, versões, backups dos provedores) dentro dos 30 dias?

**Fontes:**
- https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm
- https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/comunicado-de-incidente-de-seguranca-cis
- https://www.gov.br/anpd/pt-br/assuntos/noticias/anpd-aprova-o-regulamento-de-comunicacao-de-incidente-de-seguranca
- https://www.gov.br/anpd/pt-br/assuntos/noticias/anpd-publica-guia-de-seguranca-para-agentes-de-tratamento-de-pequeno-porte
- https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/atos-normativos/regulamentacoes_anpd/resolucao-cd-anpd-no-2-de-27-de-janeiro-de-2022
- https://www.conjur.com.br/2024-ago-03/atuacao-do-encarregado-de-dados-pessoais-apos-a-resolucao-cd-anpd-18/
- https://www.tauilchequer.com.br/pt/insights/publications/2023/06/anpd-publishes-record-of-processing-activities-ropa-template-for-small-processing-agents

---

## Tema 7 — Documentos jurídicos e fluxos de aceite

### (a) Contexto aplicado ao CRIA
Quem assina/paga é o **arquiteto**, mas os titulares incluem **cliente e prestador**. São necessários **três documentos distintos e não intercambiáveis**: **Termos de Uso** (relação contratual com o arquiteto), **Política/Aviso de Privacidade** (transparência perante **todos** os titulares) e **DPA** (instruções e responsabilidades entre agentes). **"Aceitar os Termos" não equivale a "consentir"** como base legal da LGPD.

### (b) Pontos relevantes com referência legal
- **Funções distintas dos documentos**: Art. 6, VI (transparência) e X (responsabilização); Art. 9 (acesso facilitado às informações); Art. 39 (operador segue instruções). **Verificado.** *Nuance: a LGPD não exige um "DPA" por esse nome — é instrumento de boa prática que materializa o Art. 39; e Termo de Uso ≠ consentimento (Art. 7/8).*
- **Base legal por finalidade ANTES do aceite**: Art. 7 (rol taxativo — "somente poderá"), I/V/IX; Art. 6 (finalidade, necessidade); **Guia ANPD de Legítimo Interesse (02/02/2024)** — LIA em 3 fases; **não se aplica a dado sensível**. Execução de contrato (Art. 7, V) cobre o **arquiteto**, mas **pode não cobrir o cliente** (que não é parte do contrato).
- **Papéis refletidos no DPA**: Art. 5, VI/VII/IX; Art. 39; Art. 42, §1, I e II (solidariedade). Critérios de **controladoria conjunta** a testar operação a operação; os papéis decorrem da **realidade fática**, não do rótulo.
- **Conteúdo obrigatório do aviso**: Art. 9, I-VI (finalidade; **forma e duração**; identificação e contato do controlador; compartilhamento; responsabilidades) e §1 (nulidade se informação enganosa/abusiva ou não apresentada previamente). A **janela de 30 dias**, o **expurgo real (inclusive Drive)** e os **subprocessadores** (Google/Supabase/Firebase/Hostinger/Vercel) devem ser declarados de forma **clara e prévia**.
- **Fluxo de aceite com prova**: Art. 8 (consentimento por meio que demonstre a manifestação; §2 ônus da prova do controlador; §4 nulidade de autorizações genéricas; §5 revogação gratuita e facilitada; §6 informar mudança de finalidade); Art. 9, §1. Registrar **quem aceitou, quando, qual versão, com que base** (identificador, papel, timestamp, hash/versão, IP). Aceites em **momentos diferentes**: arquiteto no signup; cliente/prestador no **primeiro acesso** ao convite.
- **Tensão titular x contratante**: Arts. 18, 15, 16, 8 §5 e 9, II. O cliente precisa **saber e aceitar previamente** que seu acesso está atrelado à conta do arquiteto, **sem que isso anule** seus direitos de obter/eliminar os próprios dados. **Entregar a mídia do interior do cliente ao arquiteto cancelante pode ser um compartilhamento** que exige base legal.
- **Retenção ancorada no Art. 16**: a janela de 30 dias deve caber numa exceção do Art. 16 ou ter base própria; revogação/eliminação antes dos 30 dias pode **conflitar** com a janela fixa.
- **DPA — cláusulas essenciais**: Art. 39; Art. 37; Art. 42, §1, I; Art. 48; **Res. 15/2024** (operador informa o controlador sem demora; controlador comunica em 3 dias úteis, em dobro para pequeno porte). Instruções documentadas, finalidade limitada, sigilo, segurança, **gestão de subprocessadores**, notificação de incidente, suporte a direitos, **devolução/eliminação ao término**.
- **Transferência internacional nos documentos**: Arts. 33-36; Art. 9, V; **Res. 19/2024** (CPC). Política e DPA devem refletir a transferência (ver Tema 5).
- **Crianças/sensíveis nas fotos** (dúvida): Art. 14 (regime reforçado para menores); Art. 11; Guia de Legítimo Interesse (não cobre sensível); Enunciado CD/ANPD nº 1/2023.

### (c) Perguntas/decisões para o(a) advogado(a)
1. Confirmar a **arquitetura documental**: (a) Termos de Uso para o arquiteto; (b) Política de Privacidade **única e pública** ou **avisos segmentados por papel** (arquiteto, cliente, prestador); (c) DPA autônomo. Qual texto apresentar a **cada papel** e **em que momento**?
2. **Mapear base legal por finalidade e por papel**: qual base sustenta os dados do **cliente** e as **fotos do interior**, já que o cliente não é o contratante? Onde se usa legítimo interesse, **fazer e documentar a LIA**. Há finalidade que exija consentimento (ex.: **marketing**)?
3. Por categoria de tratamento, o CRIA é **controlador, operador ou cocontrolador**? Como **declarar** isso no DPA e no aviso (Art. 9, VI)?
4. Revisar minuta da Política contra o **Art. 9**: a janela de 30 dias, o expurgo real, os subprocessadores e o canal de direitos estão **claros e prévios**? Qual a **redação da cláusula de "duração do tratamento"** que sustenta o expurgo?
5. Que **evidências de aceite** armazenar? Aceite **único ou granular por finalidade**? Quando uma nova versão exige **re-aceite** e como tratar usuários ativos? Para o cliente convidado, o aceite no **primeiro acesso** é suficiente?
6. **Quem é o destinatário legítimo do .zip** — arquiteto, cliente, ambos? Entregá-lo ao arquiteto que cancelou **exige consentimento/aviso específico do cliente**? Que **redação no aceite** do cliente e do arquiteto deixa a dependência juridicamente sustentável?
7. Qual a **base/exceção do Art. 16** que sustenta a janela de 30 dias? Pedido de eliminação/revogação **antes** dos 30 dias deve ser atendido de imediato? Há dados a **reter por obrigação legal** mesmo após o expurgo (faturamento/pagamento)?
8. Quais **cláusulas o DPA deve conter** e **quem assina**? Cadeia de subprocessadores por **autorização geral + lista** ou **aprovação caso a caso**? Fluxo e prazos de notificação de incidente (Res. 15/2024). O CRIA é **pequeno porte**?
9. **Crianças/sensíveis nas fotos**: é preciso instrução/aviso ao prestador e cliente para **não fotografar terceiros**, base legal e aceite específicos, ou **controles de produto** (blur, restrição)? Como refletir o Art. 14 e o Art. 11 nos documentos e no fluxo?

**Fontes:**
- https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm
- https://lgpd-brasil.info/capitulo_02/artigo_09
- https://lgpd-brasil.info/capitulo_02/artigo_07
- https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/guia_legitimo_interesse.pdf
- https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/2021.05.27GuiaAgentesdeTratamento_Final.pdf
- https://confidata.com.br/blog/clausulas-contratuais-lgpd-contratos-terceiros
- https://lgpd-brasil.info/capitulo_02/artigo_16
- https://lgpd-brasil.info/capitulo_02/artigo_14
- https://goadopt.io/blog/termos-de-uso-lgpd/

---

## Documentos a produzir

| Documento | Função | Destinatário(s) | Pontos críticos a endereçar |
|---|---|---|---|
| **Termos de Uso** | Reger a relação contratual/comercial e o uso da plataforma | **Arquiteto** (pagante) | Objeto, assinatura/pagamento, obrigações do arquiteto como controlador, política de cancelamento ("perde acesso imediato", .zip 30 dias, expurgo), declaração de papéis, instrução para não subir fotos de terceiros/crianças. **Não confundir com consentimento.** |
| **Política/Aviso de Privacidade** | Transparência (Arts. 6, VI; 9) | **Arquiteto, cliente e prestador** (única e pública e/ou segmentada por papel) | Finalidades; **forma e duração/retenção** (30 dias + expurgo, inclusive Drive); bases legais por finalidade; subprocessadores (Google/Supabase/Vercel/Firebase/Hostinger); **transferência internacional** e mecanismo do Art. 33; direitos do Art. 18 e canal; contato do encarregado; regra "cancelamento do arquiteto afeta cliente/prestador". |
| **DPA / Acordo de Tratamento** | Materializar Art. 39 (instruções, responsabilidades) | Entre **CRIA e arquiteto**; e entre **CRIA e cada subprocessador** | Instruções documentadas, finalidade limitada, sigilo, segurança (Art. 46), **gestão de subprocessadores** (autorização), **notificação de incidente** (Res. 15/2024), suporte ao exercício de direitos (com SLA e fronteira controlador/operador conforme **correção do Art. 18, §4**), **cláusulas-padrão de transferência (Res. 19/2024)**, **devolução/eliminação ao término**. |
| **(Avaliar) RIPD** | Documentar risco e salvaguardas | Interno / ANPD sob demanda | Necessidade dada a combinação fotos sensíveis + larga escala + possíveis menores + transferência internacional. |
| **(Avaliar) Termo de consentimento específico do cliente** | Base para fotos sensíveis/imagem e dados de menores | Cliente (e responsável legal) | Consentimento destacado, específico, no app; verificação parental (Art. 14). |
| **ROPA** | Registro das operações (Art. 37) | Interno / ANPD sob demanda | Simplificado (pequeno porte) ou completo conforme enquadramento de risco. |
| **Plano de Resposta a Incidentes** | Cumprir Art. 48 / Res. 15/2024 | Interno | Detecção, prazos (3/6 dias úteis), conteúdo da comunicação, registro interno, notificação de fornecedores. |

---

## Checklist de pré-lançamento

**Definição de papéis e contratos**
- [ ] Mapa **operação por operação** de controlador/operador/cocontrolador (com parecer sobre o papel do CRIA nas decisões de produto — expurgo, perda de acesso).
- [ ] Posição confirmada do **cliente** (somente titular x cocontrolador das fotos) e do **prestador**.
- [ ] **DPA** com o arquiteto assinado/aceito (com cláusulas mínimas e fronteira de atendimento de direitos).
- [ ] **DPAs com subprocessadores** (Google, Supabase, Vercel, Firebase, Hostinger) verificados e arquivados.

**Bases legais e fotos**
- [ ] **Base legal definida por finalidade e por papel**, com **LIA documentada** onde houver legítimo interesse.
- [ ] Critério operacional para fotos do interior (tratar como **potencialmente sensível**?) e decisão sobre **consentimento do cliente**.
- [ ] Estratégia para **crianças/terceiros** nas fotos (instrução, aviso, salvaguardas técnicas, consentimento parental).
- [ ] Vedação contratual/arquitetural de uso das fotos para **marketing/treino de IA**.

**Transferência internacional**
- [ ] **Região definida** por fornecedor (Supabase-BR; Google/Vercel-UE conforme decisão) e enquadramento no Art. 33.
- [ ] **Cláusulas-padrão brasileiras (Res. 19/2024)** incorporadas onde necessário — período de graça **já encerrado (23/08/2025)**.
- [ ] **FCM**: payload sem dados pessoais (notificação genérica + fetch no backend BR); confirmação de DPA/CPC.
- [ ] Plano de contingência para **reavaliação da adequação UE em 4 anos**.

**Direitos do titular**
- [ ] Canal de exercício de direitos **acessível a cliente e prestador**, com identificação via autenticação do app (sem CPF/RG).
- [ ] Fluxo definido conforme **correção**: pedido tratado pelo **controlador (arquiteto)**; CRIA repassa/executa por **instrução contratual** (não pelo Art. 18, §4).
- [ ] Prazos internos prometidos (ex.: **15 dias** por analogia ao Art. 19) e SLA do arquiteto.
- [ ] **Canal próprio do cliente** para baixar/eliminar/portar as próprias fotos, independentemente do arquiteto.
- [ ] **Exportação de portabilidade** em formato adequado e para o destinatário correto (separada do .zip do arquiteto).
- [ ] **Botão de revogação** facilitado no app + aviso de que revogar não apaga automaticamente.

**Retenção, expurgo e tensão central**
- [ ] **Justificativa documentada** da janela de 30 dias (enquadramento no Art. 16).
- [ ] **Notificação independente** ao cliente/prestador antes do expurgo, com janela própria.
- [ ] Decisão sobre **destinatário do .zip** (e base legal se entregue ao arquiteto).
- [ ] **Expurgo comprovável** em todas as camadas (banco, Drive — lixeira/versões, backups Supabase, caches) com log/atestado (Art. 18, §6).
- [ ] Política para **mídia multi-titular** (lacuna legal — decisão interpretativa documentada).

**Governança e segurança**
- [ ] **ROPA** elaborado (simplificado ou completo conforme risco).
- [ ] Decisão sobre **RIPD**.
- [ ] **Encarregado** indicado/decisão de dispensa (pequeno porte) + **canal publicado**.
- [ ] **Medidas do Art. 46** implementadas e documentadas (criptografia, controle de acesso por papel, logs de acesso às fotos, gestão da service account do Drive, backups).
- [ ] **Plano de resposta a incidentes** + template de **registro interno** (Res. 15/2024), incluindo notificação por fornecedores.

**Documentos e aceite**
- [ ] **Termos de Uso, Política de Privacidade e DPA** finalizados e revisados pelo(a) advogado(a).
- [ ] **Fluxo de aceite com prova versionada** (quem, quando, versão, base, papel) para arquiteto, cliente e prestador.
- [ ] Redação que torna **clara e prévia** ao cliente a regra "acesso atrelado à conta do arquiteto" e a retenção/expurgo.
- [ ] Plano de **re-aceite** para novas versões dos documentos.

---

*Documento preparado para orientar a consultoria jurídica especializada em LGPD. Não constitui parecer nem aconselhamento jurídico. Itens marcados como "dúvida a confirmar" e "lacuna legal" exigem decisão expressa do(a) advogado(a) antes do lançamento.*
