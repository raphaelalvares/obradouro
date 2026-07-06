-- 0103_unificar_acesso_cliente.sql  (UM só caminho de acesso do cliente + fix "pendente preso")
--
-- Decisão de produto (auditoria do fluxo do cliente): o acesso do cliente ao PROJETO passa a ter UM
-- único caminho — a pré-autorização por e-mail do PORTAL (`acessos_cliente`, 0089/0096/0102), que é a
-- única que carrega PRAZO (validade_tipo/expira_em) e o marco de ENTREGA. Os outros dois caminhos que
-- existiam ("convite por e-mail" e "código de projeto") são APOSENTADOS — eram o "dois convites
-- separados": telas paralelas que materializavam projeto_membros 'cliente' SEM prazo e por fora do
-- portal, deixando o mesmo cliente representado em dois lugares que não se enxergavam.
--
-- Esta migration:
--   (1) CORRIGE o bug "pendente preso" (B1): reconciliar_acessos_cliente() fazia `on conflict do
--       nothing` ao materializar a membership — então um cliente que já existia como 'pendente' (tinha
--       entrado por código/convite) NUNCA era promovido a 'ativo' quando o portal era liberado, e como
--       current_projeto_ids()/current_obra_ids() filtram estado='ativo', o RLS escondia o projeto dele
--       sem recuperação. Passa a `do update set estado='ativo'` (só em linha 'cliente' — nunca promove
--       um arquiteto). O `aplicar_validade_acesso` que já roda logo em seguida carimba o prazo certo.
--   (2) MIGRA os clientes legados (código/convite) para o modelo do portal: cria a linha de
--       `acessos_cliente` que faltava (para aparecerem/serem geridos na tela única) e destrava quem
--       ficou 'pendente' (a rede do B1 para o passado).
--   (3) REMOVE o caminho "código de projeto": função resgatar_codigo_projeto (0041), tabela
--       projeto_codigos (0039 policies + 0040 guard, via cascade) e o guard órfão; e o rótulo de
--       pendentes minhas_inscricoes_projeto_pendentes (0039), que só servia ao convite.
--   O caminho "convite por e-mail" não tem objeto de banco próprio (usava projeto_membros direto) — é
--   removido só no backend/front (rotas/telas). projeto_membros/obra_membros e seus guards FICAM (a
--   reconciliação do portal continua materializando o vínculo).
--
-- Depende de: 0089/0096/0102 (portal/prazo/elo-lead), 0039/0040/0041 (código+guards), 0073 (guard A5).
-- Aplicar como postgres, após 0102. DEV antes de PROD. Idempotente.

begin;

-- ===================== (1) FIX B1 — reconciliar promove 'pendente' → 'ativo' =====================
-- Recria a função da 0096 (expiry-aware) trocando SÓ os 3 `on conflict do nothing` por
-- `do update set estado='ativo'` (com predicado papel='cliente' via alias, p/ nunca tocar arquiteto).
-- Todo o resto (aplicar_validade_acesso, contexto sem vencidos, tem_papel_cliente) é idêntico à 0096.
create or replace function public.reconciliar_acessos_cliente()
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_uid        uuid := (select auth.uid());
  v_email      text;
  v_confirmado boolean := false;
  v_proj       jsonb := '[]'::jsonb;
  v_obras      jsonb := '[]'::jsonb;
  v_arq        boolean;
  v_cli_any    boolean;
  r            record;
begin
  if v_uid is null then
    raise exception 'sem usuario autenticado' using errcode = '28000';
  end if;
  select u.email::text, (u.email_confirmed_at is not null)
    into v_email, v_confirmado
  from auth.users u where u.id = v_uid;

  if v_email is not null and v_confirmado then
    for r in
      select ac.id, ac.tenant_id, ac.projeto_id, ac.obra_id
      from public.acessos_cliente ac
      where lower(ac.email::text) = lower(v_email) and ac.profile_id is null
      for update
    loop
      update public.acessos_cliente set profile_id = v_uid, estado = 'ativo' where id = r.id;

      if r.projeto_id is not null then
        insert into public.projeto_membros as pm (projeto_id, profile_id, papel, estado, invited_by)
        values (r.projeto_id, v_uid, 'cliente', 'ativo', r.tenant_id)
        on conflict (projeto_id, profile_id)
          do update set estado = 'ativo' where pm.papel = 'cliente';   -- B1: destrava pendente
        insert into public.obra_membros as om (obra_id, profile_id, papel, estado, invited_by)
        select pj.obra_id, v_uid, 'cliente', 'ativo', r.tenant_id
        from public.projetos pj
        where pj.id = r.projeto_id and pj.obra_id is not null
        on conflict (obra_id, profile_id)
          do update set estado = 'ativo' where om.papel = 'cliente';
      end if;

      if r.obra_id is not null then
        insert into public.obra_membros as om (obra_id, profile_id, papel, estado, invited_by)
        values (r.obra_id, v_uid, 'cliente', 'ativo', r.tenant_id)
        on conflict (obra_id, profile_id)
          do update set estado = 'ativo' where om.papel = 'cliente';
      end if;

      -- carimba expira_em conforme a validade do acesso (sem_prazo/data/entrega)
      perform public.aplicar_validade_acesso(r.id);
    end loop;
  end if;

  -- contexto: projetos/obras onde sou CLIENTE ativo E NÃO vencido (vencido some do portal)
  select coalesce(jsonb_agg(jsonb_build_object(
           'id', pj.id, 'nome', pj.nome, 'seq_humano', pj.seq_humano, 'obra_id', pj.obra_id)
           order by pj.created_at), '[]'::jsonb)
    into v_proj
  from public.projeto_membros pm
  join public.projetos pj on pj.id = pm.projeto_id
  where pm.profile_id = v_uid and pm.papel = 'cliente' and pm.estado = 'ativo'
    and (pm.expira_em is null or pm.expira_em > now());

  select coalesce(jsonb_agg(jsonb_build_object(
           'id', o.id, 'nome', o.nome, 'seq_humano', o.seq_humano, 'status', o.status)
           order by o.created_at), '[]'::jsonb)
    into v_obras
  from public.obra_membros om
  join public.obras o on o.id = om.obra_id
  where om.profile_id = v_uid and om.papel = 'cliente' and om.estado = 'ativo'
    and (om.expira_em is null or om.expira_em > now());

  v_arq := exists (select 1 from public.obras    where tenant_id = v_uid)
        or exists (select 1 from public.projetos where tenant_id = v_uid);

  v_cli_any := exists (
                 select 1 from public.projeto_membros where profile_id = v_uid and papel = 'cliente')
            or exists (
                 select 1 from public.obra_membros    where profile_id = v_uid and papel = 'cliente');

  return jsonb_build_object(
    'eh_arquiteto',      v_arq,
    'eh_cliente',        (jsonb_array_length(v_proj) > 0 or jsonb_array_length(v_obras) > 0),
    'tem_papel_cliente', v_cli_any,
    'projetos',          v_proj,
    'obras',             v_obras);
end;
$$;
alter function public.reconciliar_acessos_cliente() owner to postgres;
revoke all on function public.reconciliar_acessos_cliente() from public, anon;
grant execute on function public.reconciliar_acessos_cliente() to authenticated;

-- ===================== (2) MIGRA clientes legados (código/convite) → modelo do portal ============
-- Os guards checam auth.uid() (INSERT em acessos_cliente exige tenant_id = auth.uid(); o A5 de
-- projeto/obra_membros barra mudar estado de "terceiro"). Aqui rodamos como postgres (auth.uid() null)
-- → desabilitamos os 3 guards SÓ durante o backfill. É o único ponto que precisa disso; reabilita logo.

-- (2a) cria a linha de acesso do portal que faltava p/ cada cliente de PROJETO materializado sem acesso
alter table public.acessos_cliente disable trigger trg_acessos_cliente_guard;
insert into public.acessos_cliente
    (tenant_id, projeto_id, oportunidade_id, email, profile_id, estado, validade_tipo)
select pj.tenant_id, pm.projeto_id,
       (select op.id from public.oportunidades op
         where op.tenant_id = pj.tenant_id and op.projeto_id = pm.projeto_id limit 1),
       p.email, pm.profile_id, 'ativo', 'sem_prazo'
from public.projeto_membros pm
join public.projetos pj on pj.id = pm.projeto_id
join public.profiles  p  on p.id = pm.profile_id
where pm.papel = 'cliente'
on conflict (projeto_id, email) where projeto_id is not null do nothing;  -- quem já tem acesso: intacto
alter table public.acessos_cliente enable trigger trg_acessos_cliente_guard;

-- (2b) B1 para o passado: destrava clientes que ficaram 'pendente' por código/convite (some do RLS)
alter table public.projeto_membros disable trigger trg_projeto_membros_guard;
update public.projeto_membros set estado = 'ativo' where papel = 'cliente' and estado = 'pendente';
alter table public.projeto_membros enable trigger trg_projeto_membros_guard;

alter table public.obra_membros disable trigger trg_obra_membros_guard;
update public.obra_membros set estado = 'ativo' where papel = 'cliente' and estado = 'pendente';
alter table public.obra_membros enable trigger trg_obra_membros_guard;

-- ===================== (3) REMOVE o caminho "código de projeto" + rótulo de pendentes ============
-- cascade na tabela derruba: policies (0039), trigger trg_projeto_codigos_guard (0040), índices.
-- A função-guard e a RPC de resgate ficam órfãs → drop explícito. minhas_inscricoes_projeto_pendentes
-- (0039) só alimentava o "convite pendente", que sai junto.
drop function if exists public.resgatar_codigo_projeto(text);
drop table    if exists public.projeto_codigos cascade;
drop function if exists public.projeto_codigos_guard();
drop function if exists public.minhas_inscricoes_projeto_pendentes();

commit;
