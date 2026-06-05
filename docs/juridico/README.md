# Trilha jurídica / LGPD — CRIA

> **Estes documentos são RASCUNHOS de trabalho. NÃO são aconselhamento jurídico e NÃO devem ser
> publicados/assinados sem revisão de advogado(a) especializado(a) em LGPD.** Os pontos marcados com
> **⚠️ A CONFIRMAR COM ADVOGADO** e os **placeholders entre colchetes** exigem decisão e preenchimento
> antes de ir ao ar.

## O que tem aqui

| Documento | Para quê | Destinatário |
|---|---|---|
| [`../briefing-juridico-lgpd.md`](../briefing-juridico-lgpd.md) | **Briefing** com a análise LGPD por tema + perguntas/decisões para o(a) advogado(a) | Insumo para a consultoria |
| [`politica-de-privacidade.md`](politica-de-privacidade.md) | **Política de Privacidade** (transparência, Arts. 6/9) | Público: Arquiteto, Cliente e Prestador |
| [`termos-de-uso.md`](termos-de-uso.md) | **Termos de Uso** (contrato de uso da Plataforma) | Arquiteto (e Cliente/Prestador no 1º acesso) |
| [`dpa-adendo-tratamento.md`](dpa-adendo-tratamento.md) | **DPA / Adendo de Tratamento** (Art. 39) | Entre CRIA (operadora) e Arquiteto (controlador) |
| [`ropa.md`](ropa.md) | **ROPA** — registro das operações de tratamento (Art. 37) | Interno / ANPD sob demanda |

## Como estes rascunhos foram feitos (premissas)

- Sob medida para a **arquitetura real** do CRIA, com **a Stripe** incluída (suboperador novo da Fase 9
  — dado de pagamento nos EUA → transferência internacional).
- **Estado atual × planejado:** descrevem como **ativos** apenas o que existe hoje (painel web React/
  Vercel; backend Python/Hostinger-EasyPanel; Supabase de banco/auth/e-mails; Stripe da assinatura;
  **mídia em infraestrutura própria**). Tratam como **futuro** (não vigente): **apps móveis**,
  **Firebase Cloud Messaging (push)** e **Google Drive** (migração da mídia).
  - ⚠️ **Divergência a alinhar:** o `briefing-juridico-lgpd.md` (escrito na Fase 1) descreve Google
    Drive, app Flutter e FCM como infraestrutura **ativa**. Hoje eles são **planejados**. Avisar o(a)
    advogado(a) dessa atualização ao entregar o briefing.

## Preencher antes de publicar (placeholders)

Substitua em **todos** os documentos:

- [ ] **[RAZÃO SOCIAL]** — entidade que opera o CRIA (provavelmente GoIdea — confirmar)
- [ ] **[CNPJ]**
- [ ] **[ENDEREÇO]** (sede)
- [ ] **[E-MAIL DE PRIVACIDADE]** / **[E-MAIL DE CONTATO]** / **[E-MAIL/ENCARREGADO]** — definir os e-mails
      (privacidade x contato geral) e usar de forma consistente
- [ ] **[ENCARREGADO/DPO E CONTATO]** — indicar Encarregado (ou decidir dispensa de pequeno porte ⚠️) + canal
- [ ] **[URL]** — endereço público onde a Política/Termos ficarão hospedados
- [ ] **[DATA DE VIGÊNCIA]** / **[DATA]**
- [ ] **[PREÇO DO PLANO]** — valores/limites dos planos (hoje: Pro R$ 97/mês em test)
- [ ] **[COMARCA/FORO]**
- [ ] **[REGIÃO DOS PROVEDORES]** — região contratada de Supabase, Hostinger/EasyPanel e Vercel
      (define se há transferência internacional)
- [ ] **[12 (doze)] meses** — teto de limitação de responsabilidade (Termos, cláusula 10.5)

## Decisões jurídicas críticas (resumo dos ⚠️)

Os documentos sinalizam, mas o(a) advogado(a) precisa **decidir**:

1. **Papéis operação a operação** (operadora × controladora × controladoria conjunta), em especial nas
   decisões de produto (retenção/expurgo) e na posição do **Cliente** (titular × cocontrolador das fotos).
2. **Base legal das fotos do interior** (provável **consentimento** do Cliente; dado sensível por
   inferência; risco de **menores** — Art. 14) + **vedação de uso para marketing/IA**.
3. **Transferência internacional** por fornecedor (mecanismo do Art. 33; cláusulas-padrão Res. 19/2024
   × adequação UE/EEE Res. 32/2026; região do Supabase/Vercel/Hostinger).
4. **Cancelamento/retenção:** proporcionalidade dos **30 dias**, **destinatário do .zip**, **notificação
   independente ao Cliente**, **mídia multi-titular**, guarda fiscal e logs do Marco Civil.
5. **Direitos do titular:** prazo (15 dias por analogia ⚠️), fluxo controlador/operador, canal próprio do
   Cliente, verificação de identidade pelo login (sem CPF/RG).
6. **Forma de aceite** dos Termos/DPA (clique embutido × instrumento apartado) e **prova versionada**.
7. **Enquadramento de pequeno porte** (ROPA simplificado × completo + **RIPD**); **Encarregado** (indicar × dispensa).

## Ainda falta produzir (próximo lote — posso gerar quando quiser)

Da lista "Documentos a produzir" do briefing, ainda não rascunhados:

- [ ] **RIPD** (Relatório de Impacto) — provavelmente exigível (fotos sensíveis + escala + possíveis menores + transferência internacional).
- [ ] **Termo de consentimento específico do Cliente** para fotos (e verificação parental, Art. 14).
- [ ] **Plano de Resposta a Incidentes** (interno — Art. 48 / Res. 15/2024).

## Follow-up de engenharia (derivado destes documentos)

Não é jurídico, é implementação — quando os textos estiverem fechados:

- [ ] **Tela/rota pública** servindo Política e Termos em **[URL]**.
- [ ] **Fluxo de aceite versionado** com prova (quem, quando, qual versão, papel): Arquiteto no cadastro;
      Cliente/Prestador no 1º acesso (convite/código). Re-aceite quando a versão mudar.
- [ ] **Canal de direitos do titular** (e-mail de privacidade; e, idealmente, um fluxo no app).

---

*Pasta preparada para subsidiar a consultoria jurídica especializada em LGPD. Revisão por advogado(a)
é obrigatória antes do lançamento.*
