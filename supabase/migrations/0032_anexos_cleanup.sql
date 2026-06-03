-- 0032_anexos_cleanup.sql  (Fase 4 — consistencia: apagar o pai apaga as linhas de anexo)
-- A FK do anexo e POLIMORFICA (parent_type, parent_id) SEM FK real, entao "on delete cascade" do
-- Postgres nao alcanca o anexo quando a etapa/item e apagada. Sem isto, sobrariam linhas de anexo
-- apontando para um pai inexistente. Trigger AFTER DELETE remove as LINHAS; os BYTES no storage
-- viram orfaos e sao recolhidos pela reconciliacao (app.services.anexos.reconciliar) — expurgo
-- real definitivo e a Fase 8. (Quando a OBRA e apagada, o cascade da FK obra_id ja leva os anexos;
-- estes triggers cobrem o caso de apagar so a etapa/item.)
-- SECURITY DEFINER (owner postgres) p/ rodar a limpeza independente do papel; o ator real continua
-- sendo o arquiteto (unico que apaga etapa/item), entao o guard 0031 do delete interno passa.
create or replace function public.anexos_limpar_orfaos()
returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  delete from public.anexos
   where parent_type = tg_argv[0] and parent_id = old.id;
  return old;
end;
$$;
alter function public.anexos_limpar_orfaos() owner to postgres;

drop trigger if exists trg_etapas_anexos_cleanup on public.etapas;
create trigger trg_etapas_anexos_cleanup
  after delete on public.etapas
  for each row execute function public.anexos_limpar_orfaos('etapa');

drop trigger if exists trg_itens_anexos_cleanup on public.checklist_itens;
create trigger trg_itens_anexos_cleanup
  after delete on public.checklist_itens
  for each row execute function public.anexos_limpar_orfaos('checklist_item');
