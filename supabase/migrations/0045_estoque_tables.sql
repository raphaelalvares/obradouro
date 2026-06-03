-- 0045_estoque_tables.sql  (Fase 6 — Estoque por NF-e: tabelas)
-- nota_fiscal (cabecalho) -> nota_item (linhas de produto), escopados a OBRA. A nota e a ENTRADA de
-- materiais; a conferencia (qtd contada vs qtd da nota) vive na linha. Sem cunho fiscal: parseamos o
-- XML so p/ extrair produtos/qtds/valores. Dual-ID: id = UUID (gerado no backend ao importar) +
-- seq_humano por tenant na NOTA (trigger 0046). tenant_id DENORMALIZADO (RLS/seq sem JOIN); coerencia
-- e imutabilidade garantidas pelos guards (0048).
--
-- IDEMPOTENCIA do import = chave de acesso (44 digitos), unica por tenant (ponto "g" do review):
-- reimportar o MESMO XML nao duplica (uq parcial abaixo + exists-check na RPC 0049).
-- nome_fiel_ao_XML: `descricao` guarda o xProd original (imutavel); `nome_editado` e a correcao
-- opcional do arquiteto. data_chegada (manual) e SEPARADA de data_emissao (do XML) — ponto do plano.

-- ===================== NOTAS FISCAIS =====================
create table if not exists public.notas_fiscais (
  id             uuid        primary key,                              -- gerado no backend (import)
  obra_id        uuid        not null references public.obras(id)     on delete cascade,
  tenant_id      uuid        not null references public.profiles(id)  on delete restrict,

  -- chave de acesso da NF-e (44 digitos). NULL so p/ lancamento manual futuro (sem XML).
  chave_acesso   text        check (chave_acesso is null or chave_acesso ~ '^[0-9]{44}$'),
  numero         text,                                                 -- nNF
  serie          text,                                                 -- serie
  emitente_nome  text,                                                 -- emit/xNome
  emitente_cnpj  text,                                                 -- emit/CNPJ
  data_emissao   timestamptz,                                          -- ide/dhEmi (do XML)
  data_chegada   date,                                                 -- manual (≠ emissao)
  valor_total    numeric(15,2) not null default 0,                     -- ICMSTot/vNF
  xml            text,                                                 -- XML cru (auditoria/re-parse)

  seq_humano     bigint,                                               -- trigger 0046
  created_by     uuid        not null references public.profiles(id)  on delete restrict,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

-- rotulo humano unico por tenant (espelha uq_obras_tenant_seq)
create unique index if not exists uq_notas_tenant_seq  on public.notas_fiscais (tenant_id, seq_humano);
-- IDEMPOTENCIA: 1 nota por chave POR TENANT (parcial: lancamento manual sem chave nao colide)
create unique index if not exists uq_notas_tenant_chave on public.notas_fiscais (tenant_id, chave_acesso)
  where chave_acesso is not null;
-- listagem por obra, ja ordenada por chegada ao sistema
create index        if not exists ix_notas_obra        on public.notas_fiscais (obra_id, created_at);

drop trigger if exists trg_notas_fiscais_updated_at on public.notas_fiscais;
create trigger trg_notas_fiscais_updated_at
  before update on public.notas_fiscais
  for each row execute function public.set_updated_at();

-- ===================== ITENS DA NOTA =====================
-- obra_id/tenant_id DENORMALIZADOS (RLS por obra sem JOIN nota->obra). Os campos vindos do XML sao a
-- VERDADE da nota e ficam IMUTAVEIS (guard 0048); so `nome_editado` e a conferencia variam.
create table if not exists public.nota_itens (
  id                   uuid          primary key,                      -- gerado no backend
  nota_id              uuid          not null references public.notas_fiscais(id) on delete cascade,
  obra_id              uuid          not null references public.obras(id)         on delete cascade,
  tenant_id            uuid          not null references public.profiles(id)      on delete restrict,

  codigo               text,                                           -- prod/cProd
  descricao            text          not null,                         -- prod/xProd (nome fiel ao XML)
  nome_editado         text,                                           -- correcao opcional do arquiteto
  ncm                  text,                                           -- prod/NCM
  unidade              text,                                           -- prod/uCom
  quantidade_nota      numeric(15,4) not null default 0,               -- prod/qCom
  valor_unitario       numeric(21,10),                                 -- prod/vUnCom
  valor_total          numeric(15,2),                                  -- prod/vProd

  -- conferencia (quem recebe em obra preenche): NULL = ainda nao conferido
  quantidade_conferida numeric(15,4),
  conferido_por        uuid          references public.profiles(id) on delete set null,
  conferido_em         timestamptz,

  ordem                int           not null default 0,               -- nItem (ordem na nota)
  created_at           timestamptz   not null default now(),
  updated_at           timestamptz   not null default now()
);

-- linhas de uma nota, ja ordenadas
create index if not exists ix_nota_itens_nota on public.nota_itens (nota_id, ordem);
-- saldo/consulta por obra inteira (1 endpoint) sem item->nota->obra
create index if not exists ix_nota_itens_obra on public.nota_itens (obra_id);

drop trigger if exists trg_nota_itens_updated_at on public.nota_itens;
create trigger trg_nota_itens_updated_at
  before update on public.nota_itens
  for each row execute function public.set_updated_at();
