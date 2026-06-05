# ROPA — Registro de Operações de Tratamento de Dados Pessoais — CRIA

> **RASCUNHO/registro interno para revisão jurídica — não é aconselhamento jurídico.**

Documento elaborado nos termos do **Art. 37 da LGPD** (Lei 13.709/2018), seguindo o **modelo simplificado de ROPA da ANPD para agentes de tratamento de pequeno porte** (Resolução CD/ANPD nº 2/2022, art. 9; modelo de jun/2023). ⚠️ **O enquadramento como agente de pequeno porte está A CONFIRMAR COM ADVOGADO** — ver nota de enquadramento abaixo. Este registro é preparado para **revisão por advogado(a) especializado(a) em LGPD** e **não constitui parecer nem aconselhamento jurídico**. As bases legais e fronteiras de papel marcadas com ⚠️ exigem decisão expressa do(a) advogado(a). Para a análise temática detalhada, ver [`docs/briefing-juridico-lgpd.md`](../briefing-juridico-lgpd.md).

---

## A) Cabeçalho — Identificação

| Campo | Conteúdo |
|---|---|
| **Operadora / Controladora (conforme operação)** | [RAZÃO SOCIAL] (provavelmente GoIdea — ⚠️ A CONFIRMAR) — produto **CRIA** |
| **CNPJ** | [CNPJ] |
| **Endereço** | [ENDEREÇO] |
| **Encarregado(a) (DPO) e contato** | [ENCARREGADO/DPO E CONTATO] |
| **Data de elaboração / última revisão** | [DATA] |
| **Versão** | Rascunho 0.1 — pendente de revisão jurídica |

### Nota de enquadramento (agente de pequeno porte)

⚠️ **A CONFIRMAR COM ADVOGADO.** Este ROPA adota o **formato simplificado** previsto para **agentes de tratamento de pequeno porte** (Resolução CD/ANPD nº 2/2022). Contudo, o enquadramento **pode não se sustentar**: o CRIA trata **fotos do interior de imóveis de clientes**, que têm alta probabilidade de revelar **dado pessoal sensível por inferência** (Art. 5, II; Art. 11), e o faz em **escala potencialmente relevante** (múltiplos arquitetos × obras × clientes). A combinação **dado potencialmente sensível + larga escala + possível presença de crianças/adolescentes nas imagens + transferência internacional** caracteriza **perfil de alto risco**, o que pode **desenquadrar o regime simplificado** e exigir **ROPA completo + RIPD** (Art. 38), além de afastar a dispensa de encarregado (Resolução 2/2022, art. 11). **Decisão de enquadramento a cargo do(a) advogado(a).**

### Papéis (resumo)

- **Arquiteto** = **CONTROLADOR** dos dados que insere (clientes, prestadores, obras, fotos, orçamentos).
- **CRIA** = **OPERADORA** dessas operações (trata "por conta de" e segundo instruções do Arquiteto — Art. 5, VII; Art. 39) **E CONTROLADORA** das suas finalidades próprias: conta/autenticação do Arquiteto, faturamento, segurança e **decisões de produto** (retenção, expurgo, perda de acesso de cliente/prestador). ⚠️ **Fronteira operadora × controladora a confirmar operação a operação com advogado.**
- **Cliente** e **Prestador** = **TITULARES** (Cliente provavelmente não é controlador das próprias fotos — ⚠️ a confirmar; é o coração da tensão do produto).

> Convenção desta planilha: a coluna **"Papel da CRIA"** indica, por operação, se o CRIA atua como **operadora** (controlador = Arquiteto) ou **controladora** (finalidade própria).

---

## B) Tabela principal — Operações de tratamento

> **Decisão de minimização registrada:** o CRIA **NÃO coleta CPF** (Art. 6, III — necessidade).

| # | Operação | Categorias de titulares | Categorias de dados | Finalidade | Base legal (Art. 7 / 11) | Papel da CRIA | Suboperadores | Transf. internacional | Retenção |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Cadastro / conta do Arquiteto** | Arquiteto (usuário pagante) | Nome, e-mail, telefone (opcional) | Criar e manter a conta; identificar o titular do contrato | **Execução de contrato** (Art. 7, V) | **Controladora** | Supabase (banco/Auth) | ⚠️ A CONFIRMAR — depende da região do Supabase [REGIÃO DOS PROVEDORES]; se São Paulo, sem transferência do dado primário | Enquanto durar a conta; após cancelamento → expurgo (ver Tabela D) |
| 2 | **Autenticação / login** | Arquiteto (e, no futuro, Cliente/Prestador convidados) | E-mail, credenciais (hash de senha gerido pelo provedor), tokens de sessão/JWT | Autenticar acesso; manter sessão segura | **Execução de contrato** (Art. 7, V) + **segurança** ⚠️ A CONFIRMAR COM ADVOGADO se há base autônoma de legítimo interesse p/ segurança da autenticação (Art. 7, IX) | **Controladora** | Supabase (Auth) | ⚠️ A CONFIRMAR — conforme região do Supabase [REGIÃO DOS PROVEDORES] | Tokens/sessão: vida útil curta; credenciais: enquanto durar a conta |
| 3 | **Faturamento da assinatura** | Arquiteto (assinante) | Nome, e-mail, dados de pagamento **tratados pela Stripe** (a CRIA **não armazena cartão**); identificadores de cobrança/assinatura | Cobrar a assinatura; gerir pagamentos; cumprir obrigações fiscais | **Execução de contrato** (Art. 7, V) + **obrigação legal/fiscal** (Art. 7, II) ⚠️ alcance da guarda fiscal A CONFIRMAR | **Controladora** | **Stripe** (processador de pagamento) | **SIM — Stripe (EUA).** EUA **sem decisão de adequação** → exige **cláusulas-padrão (Res. CD/ANPD 19/2024)** ⚠️ A CONFIRMAR mecanismo do Art. 33 | Dados de faturamento podem ter **guarda legal própria** (fiscal/contábil) que **sobrevive ao expurgo geral** ⚠️ prazo A CONFIRMAR |
| 4 | **Cadastro de Cliente e Prestador** | Cliente; Prestador | Nome, e-mail, telefone (opcional), papel (cliente/prestador), vínculo à obra | Permitir ao Arquiteto gerir os participantes da obra | ⚠️ **A CONFIRMAR COM ADVOGADO** — provável legítimo interesse do Arquiteto (Art. 7, IX, com LIA) ou execução de contrato do Arquiteto (Art. 7, V); o contrato é do **Arquiteto**, não do titular | **Operadora** (controlador = Arquiteto) | Supabase | ⚠️ conforme região do Supabase [REGIÃO DOS PROVEDORES] | Acompanha a obra/conta do Arquiteto; expurgo conforme Tabela D |
| 5 | **Convite / vínculo por e-mail ou código de obra** | Cliente; Prestador (convidados) | E-mail; código de convite/obra | Convidar e vincular participantes à obra | ⚠️ **A CONFIRMAR** — execução de contrato/legítimo interesse do Arquiteto (Art. 7, V/IX) | **Operadora** | Supabase (envio de e-mails transacionais) | ⚠️ conforme região do Supabase / infra de e-mail [REGIÃO DOS PROVEDORES] | E-mail de convite: até consumação/expiração do convite; vínculo: enquanto durar a obra |
| 6 | **Checklist / cronograma e orçamento** | Cliente; Prestador; Arquiteto | Etapas, itens, datas/prazos, valores orçados, observações de execução | Gerir o andamento e o orçamento da obra | ⚠️ **A CONFIRMAR** — execução de contrato/legítimo interesse do Arquiteto (Art. 7, V/IX) | **Operadora** | Supabase | ⚠️ conforme região do Supabase [REGIÃO DOS PROVEDORES] | Enquanto durar a obra/conta; expurgo conforme Tabela D |
| 7 | **Notas fiscais (NF-e) — controle de materiais** | Cliente; Prestador; terceiros citados na NF (emitente) | Emitente, produtos, quantidades, valores | **Controle de materiais da obra** (SEM cunho fiscal/escrituração) | ⚠️ **A CONFIRMAR** — legítimo interesse do Arquiteto (Art. 7, IX, com LIA) — **finalidade NÃO é obrigação fiscal** | **Operadora** | Supabase (dados); armazenamento de mídia próprio se houver imagem da NF | ⚠️ conforme região do Supabase [REGIÃO DOS PROVEDORES] | Enquanto durar a obra/conta; expurgo conforme Tabela D |
| 8 | **Fotos e observações da obra** ⚠️ **ALTO RISCO** | Cliente (dono do imóvel); pessoas retratadas; Prestador; Arquiteto | Imagens do canteiro **e do INTERIOR do imóvel do Cliente**; observações textuais associadas. **Potencialmente DADO SENSÍVEL POR INFERÊNCIA** (Art. 5, II; Art. 11) — interior do lar pode revelar saúde, religião, origem racial etc., mesmo sem rostos; risco adicional de **crianças/adolescentes** (Art. 14) | Registrar e acompanhar a execução da obra | ⚠️ **A CONFIRMAR COM ADVOGADO — provável CONSENTIMENTO específico e destacado do Cliente** (Art. 11, I) p/ dado sensível; legítimo interesse **NÃO se aplica a dado sensível**. **Vedar uso para marketing e para treino de IA.** | **Operadora** (controlador = Arquiteto) | **Armazenamento de mídia em infraestrutura PRÓPRIA** (atual); Supabase (metadados). *Google Drive = futuro (Tabela C)* | ⚠️ A CONFIRMAR — depende de onde reside a infra própria [REGIÃO DOS PROVEDORES]; no futuro, Drive (EUA ou Europa) gera transferência | Enquanto durar a obra/conta; expurgo conforme Tabela D — **alcançar lixeira/versões/backups** (Art. 18, §6) |
| 9 | **Exportação / portabilidade de dados (.zip sob demanda)** | Arquiteto (e, conforme decisão, Cliente/Prestador) | Pacote consolidado dos dados da conta/obra (cadastros, checklist, orçamento, NF, fotos, observações) | Disponibilizar cópia/portabilidade dos dados | **Atendimento a direito do titular** (Art. 18, V; Art. 19, §3) — operacionaliza obrigação legal | **Operadora** (executa por instrução do Arquiteto-controlador) ⚠️ destinatário legítimo do .zip A CONFIRMAR | Armazenamento próprio (geração do .zip); Supabase | ⚠️ conforme infra [REGIÃO DOS PROVEDORES] | **.zip disponível por 30 dias** após cancelamento (ver Tabela D) ⚠️ proporcionalidade do prazo A CONFIRMAR |
| 10 | **Logs de acesso e segurança** | Arquiteto; Cliente; Prestador (titulares que acessam) | Registros de acesso/eventos, identificadores de sessão, IP, timestamps, ações relevantes | Segurança da informação; rastreabilidade; prevenção a fraude/abuso | ⚠️ **A CONFIRMAR COM ADVOGADO** — **legítimo interesse / segurança** (Art. 7, IX, com LIA) e/ou guarda de logs de aplicação (Marco Civil da Internet) | **Controladora** | Supabase; infraestrutura própria (backend) | ⚠️ conforme região dos provedores [REGIÃO DOS PROVEDORES] | ⚠️ prazo A CONFIRMAR (eventual guarda mínima de logs de aplicação — Marco Civil) |
| 11 | **(FUTURO) Notificações push** | Arquiteto; Cliente; Prestador (usuários de app móvel) | **Token FCM** (identificador de dispositivo) ⚠️ token pode ser dado pessoal para fins de transferência | Enviar notificações ao app móvel | ⚠️ **A CONFIRMAR** — provável legítimo interesse/execução de contrato (Art. 7, IX/V) | **Controladora** (finalidade própria de produto) | **Firebase Cloud Messaging (FCM)** — *futuro* | **SIM (futuro) — Google/FCM (infra global, provável EUA), sem escolha de região** → exige **cláusulas-padrão**; **minimizar payload** (sem dado pessoal na notificação) | Token enquanto válido/registrado; renovação/expurgo no logout |

> **Observações transversais:**
> - **Estado atual × planejado:** são **ativos atuais** apenas — painel web React (Vercel), backend Python/FastAPI (Hostinger/EasyPanel), Supabase (banco/Auth/e-mails transacionais), Stripe (assinatura) e **armazenamento de mídia em infraestrutura própria**. São **FUTUROS** (não operam hoje): **apps móveis**, **Firebase Cloud Messaging (push)** e **Google Drive** (migração da mídia).
> - **Transferência internacional (camada cumulativa):** cada operação que toque provedor/região no exterior exige **base de tratamento (Art. 7/11) E mecanismo de transferência (Art. 33)** — duas camadas. ⚠️ Enquadramento por fornecedor A CONFIRMAR (ver Tabela C).

---

## C) Suboperadores / terceiros

> Mecanismos de transferência: **Art. 33, I** (país/organismo com decisão de adequação — hoje apenas **UE/EEE**, Res. CD/ANPD nº 32/2026, reavaliação em 4 anos); **Art. 33, II** (**cláusulas-padrão contratuais — Res. CD/ANPD nº 19/2024**, adotar sem modificação; período de graça encerrado em 23/08/2025); **Art. 33, VIII** (consentimento específico — frágil, reservar à transparência). ⚠️ **Mecanismo definitivo por fornecedor A CONFIRMAR COM ADVOGADO** (inclusive se DPAs trazem SCC europeias × cláusulas-padrão brasileiras).

| Nome | Finalidade | País / Região | Transferência internacional e mecanismo (Art. 33) | Status |
|---|---|---|---|---|
| **Supabase** | Banco de dados (Postgres), autenticação, e-mails transacionais | [REGIÃO DOS PROVEDORES] — São Paulo (sa-east-1) disponível; ⚠️ confirmar região contratada | Se **São Paulo**, dado primário **sem transferência**; resíduo possível (suporte/backups/réplicas/logs) ⚠️. Se região externa → **cláusulas-padrão (Art. 33, II)** ⚠️ A CONFIRMAR | **Atual** |
| **Stripe** | Processamento da assinatura/pagamento (a CRIA não armazena cartão) | **EUA** | **EUA sem adequação** → **cláusulas-padrão (Art. 33, II)** ⚠️ confirmar se o DPA da Stripe contempla as cláusulas-padrão brasileiras (Res. 19/2024) ou só SCC europeias | **Atual** |
| **Hostinger / EasyPanel** | Hospedagem do backend Python (FastAPI) — VPS | [REGIÃO DOS PROVEDORES] ⚠️ confirmar país/região da VPS | Se VPS fora do Brasil → **cláusulas-padrão (Art. 33, II)**; se região adequada (UE/EEE) → Art. 33, I ⚠️ A CONFIRMAR | **Atual** |
| **Vercel** | Hospedagem do painel web React (CDN/edge) | [REGIÃO DOS PROVEDORES] — gru1 (São Paulo) disponível p/ funções, mas é **edge/CDN global** | Difícil confinar ao Brasil (cache/execução tendem a ser internacionais) → **cláusulas-padrão (Art. 33, II)** e/ou **minimizar dado pessoal no front** ⚠️ A CONFIRMAR | **Atual** |
| **Google Drive** (service account / Shared Drives) | Armazenamento de mídia (fotos/observações) | **EUA ou Europa** (sem região Brasil) | **FUTURO.** Configurar **Europe** → **Art. 33, I** (adequação UE/EEE); caso EUA → **cláusulas-padrão (Art. 33, II)**. Cobertura parcial das data regions ⚠️ A CONFIRMAR | **Futuro (planejado)** |
| **Firebase Cloud Messaging (FCM)** | Notificações push para apps móveis | **Infra global do Google** (provável EUA; **sem escolha de região**) | **FUTURO.** **Cláusulas-padrão (Art. 33, II)** + **minimização do payload** (sem dado pessoal na notificação) ⚠️ A CONFIRMAR | **Futuro (planejado)** |

---

## D) Tabela de retenção

> **Política de produto (já definida):** ao **cancelar**, o Arquiteto **perde acesso imediato**; os dados são empacotados em **.zip disponível por 30 dias**; depois ocorre **expurgo real** — inclusive **banco, armazenamento de mídia, lixeira/versões e backups**. **Cliente e Prestador daquela obra perdem acesso junto.** A eliminação é a **regra** (Art. 15/16); a conservação é exceção e deve caber numa hipótese do **Art. 16**. ⚠️ **Toda a coluna de prazos/critérios está sujeita a confirmação jurídica** (proporcionalidade dos 30 dias, guarda fiscal, logs do Marco Civil, mídia multi-titular).

| Categoria de dado | Prazo / critério | Gatilho de eliminação |
|---|---|---|
| **Cadastro/conta do Arquiteto** (op. 1) | Enquanto durar a conta | Cancelamento → janela de 30 dias (.zip) → **expurgo real** |
| **Autenticação** — credenciais (op. 2) | Enquanto durar a conta | Cancelamento → expurgo; tokens/sessão expiram por vida útil curta |
| **Faturamento da assinatura** (op. 3) | ⚠️ **Guarda legal própria** (fiscal/contábil) pode **sobreviver ao expurgo geral** — prazo A CONFIRMAR COM ADVOGADO | Decurso do prazo legal de guarda (não pelo cancelamento) |
| **Cadastro de Cliente e Prestador** (op. 4) | Enquanto durar a obra/conta do Arquiteto | Cancelamento → 30 dias (.zip) → expurgo; ou pedido de eliminação do titular |
| **Convite/vínculo** (op. 5) | Até consumação/expiração do convite; vínculo enquanto durar a obra | Consumo/expiração do convite; cancelamento → expurgo |
| **Checklist/cronograma/orçamento** (op. 6) | Enquanto durar a obra/conta | Cancelamento → 30 dias (.zip) → expurgo |
| **Notas fiscais — controle de materiais** (op. 7) | Enquanto durar a obra/conta (uso é controle de materiais, **não** escrituração fiscal) ⚠️ confirmar se há guarda legal incidente | Cancelamento → 30 dias (.zip) → expurgo |
| **Fotos e observações da obra** (op. 8) ⚠️ | Enquanto durar a obra/conta | Cancelamento → 30 dias (.zip) → **expurgo real alcançando lixeira/versões/backups** (Art. 18, §6); ou pedido de eliminação do titular (Cliente) ⚠️ tensão titular × contratante A CONFIRMAR |
| **Exportação/.zip** (op. 9) | **30 dias** após o cancelamento | Decurso dos 30 dias → eliminação do pacote ⚠️ proporcionalidade A CONFIRMAR |
| **Logs de acesso e segurança** (op. 10) | ⚠️ prazo A CONFIRMAR — eventual **guarda mínima de logs de aplicação (Marco Civil da Internet)** pode sobreviver ao expurgo geral | Decurso do prazo de guarda definido |
| **(Futuro) Token FCM** (op. 11) | Enquanto válido/registrado | Logout/desregistro do dispositivo; renovação do token |

> **Gatilho transversal — direito do titular:** independentemente do cancelamento do Arquiteto, o **Cliente/Prestador** pode pedir **eliminação** (Art. 18, IV/VI) a qualquer tempo; o expurgo deve **propagar-se** a todos os suboperadores e camadas (Art. 18, §6). ⚠️ Conflito entre eliminação imediata pedida pelo Cliente e janela fixa de 30 dias **a resolver com advogado**.

---

## E) Medidas de segurança (Art. 46)

- **RLS (Row-Level Security) no banco** como **2ª camada** de isolamento por tenant (a 1ª camada é a API — app/web falam só com a API Python/JWT).
- **Controle de acesso por papel** (gating de UI/ações conforme `meu_papel`; autorização no backend).
- **Autenticação via JWT**; gestão de sessão/tokens pelo provedor (Supabase Auth).
- **TLS** em trânsito (API e provedores).
- **Backups** (banco/Supabase) ⚠️ confirmar política de retenção e eliminação verificável dos backups.
- **Minimização**: **não se coleta CPF**; telefone é opcional (Art. 6, III).
- **Logs** de acesso e segurança para rastreabilidade.
- **Mídia trafega pela API (JWT)** — front busca por `fetch` e usa blob URL (padrão `AnexoImage`), evitando exposição direta do armazenamento.
- ⚠️ **A REFORÇAR / A CONFIRMAR COM ADVOGADO:** **logs de acesso às fotos** (interior do imóvel), **gestão de credenciais e da service account** do armazenamento de mídia (atual e do futuro Drive), **criptografia em repouso** da mídia, e tratamento das fotos como **potencialmente sensível por precaução**.

---

## F) Pendências / decisões (remetem ao briefing detalhado)

Ver análise completa em [`docs/briefing-juridico-lgpd.md`](../briefing-juridico-lgpd.md).

- **Enquadramento de pequeno porte** (ROPA simplificado × completo + **RIPD**): fotos do interior + escala podem desenquadrar — ⚠️ decidir (briefing Tema 6).
- **Mapa de papéis operação a operação** (operadora × controladora × controladoria conjunta), em especial nas **decisões de produto** (expurgo/perda de acesso) — ⚠️ briefing Tema 1.
- **Posição do Cliente**: somente titular × cocontrolador das próprias fotos — ⚠️ briefing Tema 2.
- **Base legal das fotos do interior** (provável **consentimento** do Cliente; vedar marketing/treino de IA) e **dado sensível por inferência** + **crianças** (Art. 14) — ⚠️ briefing Tema 2.
- **Base legal de cadastro de Cliente/Prestador, checklist, orçamento, NF** (contrato é do Arquiteto, não do titular) — ⚠️ briefing Temas 1, 4 e 7.
- **Transferência internacional por fornecedor** (mecanismo do Art. 33; cláusulas-padrão Res. 19/2024 × adequação UE/EEE Res. 32/2026; região do Supabase/Vercel/Hostinger) — ⚠️ briefing Tema 5.
- **Retenção**: justificativa documentada dos **30 dias**, **guarda fiscal** do faturamento, **logs (Marco Civil)**, **mídia multi-titular** e **destinatário legítimo do .zip** (entregar mídia do interior ao Arquiteto cancelante pode ser compartilhamento que exige base) — ⚠️ briefing Temas 3 e 4.
- **Expurgo comprovável** em todas as camadas (banco, mídia, lixeira/versões, backups) com log/atestado (Art. 18, §6) — ⚠️ briefing Temas 4 e 6.
- **Encarregado/DPO**: indicar × dispensa (pequeno porte) + **canal publicado** acessível a Cliente/Prestador — ⚠️ briefing Temas 3 e 6.
- **Documentos de aceite** (Termos de Uso × Política de Privacidade × DPA) e **prova versionada** de aceite por papel — ⚠️ briefing Tema 7.
- **Futuros** (apps móveis, **FCM/push**, **Google Drive**): reavaliar este ROPA quando entrarem em produção — ⚠️ briefing Temas 5 e 6.

---

*Rascunho/registro interno preparado para revisão por advogado(a) especializado(a) em LGPD. Não constitui parecer nem aconselhamento jurídico. Itens marcados ⚠️ exigem decisão expressa antes do lançamento.*
