-- 0073_sec_a4_a5_membros_delete_estado.sql  (SEGURANÇA — Fase 2, itens A4 + A5 / ALTO)
-- Vale para obra_membros E projeto_membros (a verificação de policies mostrou os MESMOS furos nos
-- dois lados). Confirmados exploráveis DIRETO via /rest/v1 (a RLS é a única fronteira).
--
-- A4 (DELETE liberado a qualquer membro): as policies `obra_membros_delete` (0014) e
--    `projeto_membros_delete` (0039) eram `using (… in current_*_ids())` → QUALQUER membro ativo
--    (cliente/prestador) podia DELETAR a linha de qualquer membro, INCLUSIVE a do arquiteto →
--    sequestro/DoS da obra/projeto. A regra "só arquiteto remove / nunca o último arquiteto" vivia
--    só na API (membros.py / projeto_vinculo.py, ambos gateados por *_writable).
--    CORREÇÃO: DELETE restrito a arquiteto ativo (RLS) + guard de defesa "não remover o último
--    arquiteto ativo" (espelha a checagem da API). O guard é cascade-safe: `exists(parent)` evita
--    bloquear o cascade de exclusão da própria obra/projeto.
--
-- A5 (guard de UPDATE não travava `estado`): os guards (0019/0040) barravam mudança de
--    papel/profile_id/obra(projeto)_id por não-arquiteto, mas NÃO `estado`. Como a policy de UPDATE
--    permite `… in current_*_ids() OR profile_id = auth.uid()`, um membro podia dar UPDATE no
--    `estado` de OUTRO membro: auto-ativar um pendente sem aprovação, ou REBAIXAR o arquiteto para
--    'pendente' (que o tira de current_*_ids, pois filtra estado='ativo') → DoS/escalada.
--    CORREÇÃO: o guard passa a recusar mudança de `estado` em linha de TERCEIRO por não-arquiteto.
--    O auto-aceite (própria linha pendente→ativo) continua: a checagem só dispara quando
--    `old.profile_id <> auth.uid()`.
--
-- NÃO QUEBRA NENHUM FLUXO (verificado):
--   - remover membro (membros.py:remove_membro / projeto_vinculo): gateado por *_writable (arquiteto)
--     e roda como `authenticated` → is_arquiteto_ativo* = true → DELETE passa; remover o último
--     arquiteto já dava 409 na API (o guard é a 2ª camada).
--   - aceitar convite (convites.py / projeto_vinculo.py): UPDATE estado='ativo' na PRÓPRIA linha
--     (old.profile_id = auth.uid()) → a checagem de A5 não dispara → passa.
--   - não há fluxo de auto-remoção (sair sozinho) — confirmado: nenhum DELETE de membro sem *_writable.
--
-- Mantém os guards SECURITY DEFINER + search_path='' (anti-hijack). Aplicar como postgres, DEPOIS da
-- 0019 e da 0040. DEV antes de PROD.
--
-- VERIFICAR após aplicar:
--   -- (1) policies de DELETE restritas a arquiteto:
--   select tablename, policyname, qual from pg_policies
--   where schemaname='public' and tablename in ('obra_membros','projeto_membros') and cmd='DELETE';
--   -- (2) ataque negado: como cliente/prestador ativo, DELETE direto de outro membro → 42501;
--   --     UPDATE do estado de outro membro → 42501. Aceitar o PRÓPRIO convite ainda funciona.

begin;

-- ===================== A4: DELETE restrito a arquiteto ativo =====================
drop policy if exists obra_membros_delete on public.obra_membros;
create policy obra_membros_delete on public.obra_membros
  for delete to authenticated
  using ( public.is_arquiteto_ativo(obra_id) );

drop policy if exists projeto_membros_delete on public.projeto_membros;
create policy projeto_membros_delete on public.projeto_membros
  for delete to authenticated
  using ( public.is_arquiteto_ativo_projeto(projeto_id) );

-- ===================== A4+A5: obra_membros_guard (UPDATE + DELETE) =====================
create or replace function public.obra_membros_guard()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op = 'DELETE' then
    -- A4 (defesa): não deixar a obra sem arquiteto ativo. exists(obras) torna cascade-safe
    -- (exclusão da própria obra cascateia os membros e NÃO deve ser bloqueada aqui).
    if old.papel = 'arquiteto' and old.estado = 'ativo'
       and exists (select 1 from public.obras o where o.id = old.obra_id)
       and (select count(*) from public.obra_membros m
            where m.obra_id = old.obra_id and m.papel = 'arquiteto' and m.estado = 'ativo') <= 1 then
      raise exception 'nao remova o ultimo arquiteto da obra' using errcode = '42501';
    end if;
    return old;
  end if;

  -- UPDATE
  -- (existente) não-arquiteto não muda papel/profile_id/obra_id (o aceite só muda estado)
  if (new.papel is distinct from old.papel
      or new.profile_id is distinct from old.profile_id
      or new.obra_id is distinct from old.obra_id)
     and not public.is_arquiteto_ativo(old.obra_id) then
    raise exception 'apenas arquiteto pode alterar papel/membro' using errcode = '42501';
  end if;
  -- A5: não-arquiteto não muda o ESTADO de OUTRO membro (auto-aceite na própria linha é permitido)
  if new.estado is distinct from old.estado
     and old.profile_id is distinct from (select auth.uid())
     and not public.is_arquiteto_ativo(old.obra_id) then
    raise exception 'apenas arquiteto altera o estado de outro membro' using errcode = '42501';
  end if;
  return new;
end;
$$;
alter function public.obra_membros_guard() owner to postgres;

drop trigger if exists trg_obra_membros_guard on public.obra_membros;
create trigger trg_obra_membros_guard
  before update or delete on public.obra_membros
  for each row execute function public.obra_membros_guard();

-- ===================== A4+A5: projeto_membros_guard (INSERT + UPDATE + DELETE) =====================
create or replace function public.projeto_membros_guard()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op = 'INSERT' then
    if new.papel = 'prestador' then
      raise exception 'prestador nao participa de projeto' using errcode = '23514';
    end if;
    return new;
  end if;

  if tg_op = 'DELETE' then
    -- A4 (defesa): não deixar o projeto sem arquiteto ativo. cascade-safe via exists(projetos).
    if old.papel = 'arquiteto' and old.estado = 'ativo'
       and exists (select 1 from public.projetos pj where pj.id = old.projeto_id)
       and (select count(*) from public.projeto_membros m
            where m.projeto_id = old.projeto_id and m.papel = 'arquiteto' and m.estado = 'ativo') <= 1 then
      raise exception 'nao remova o ultimo arquiteto do projeto' using errcode = '42501';
    end if;
    return old;
  end if;

  -- UPDATE: não-arquiteto não muda papel/profile/projeto (anti-escalada; o aceite só muda estado)
  if (new.papel is distinct from old.papel
      or new.profile_id is distinct from old.profile_id
      or new.projeto_id is distinct from old.projeto_id)
     and not public.is_arquiteto_ativo_projeto(old.projeto_id) then
    raise exception 'apenas arquiteto pode alterar papel/membro' using errcode = '42501';
  end if;
  -- A5: não-arquiteto não muda o ESTADO de OUTRO membro
  if new.estado is distinct from old.estado
     and old.profile_id is distinct from (select auth.uid())
     and not public.is_arquiteto_ativo_projeto(old.projeto_id) then
    raise exception 'apenas arquiteto altera o estado de outro membro' using errcode = '42501';
  end if;
  if new.papel = 'prestador' then              -- nem o arquiteto promove a prestador no projeto
    raise exception 'prestador nao participa de projeto' using errcode = '23514';
  end if;
  return new;
end;
$$;
alter function public.projeto_membros_guard() owner to postgres;

drop trigger if exists trg_projeto_membros_guard on public.projeto_membros;
create trigger trg_projeto_membros_guard
  before insert or update or delete on public.projeto_membros
  for each row execute function public.projeto_membros_guard();

commit;
