-- 0093_cancelar_assinatura.sql  (Self-service: o arquiteto cancela a própria assinatura no app)
--
-- O caminho hospedado (Customer Portal) já permitia cancelar, mas o usuário quer um botão NATIVO
-- "Cancelar assinatura" na tela de conta (e o inverso, "Reativar"). Cancelamento é SEMPRE no fim do
-- período pago (cancel_at_period_end no Stripe): o arquiteto mantém o acesso até o que já pagou
-- acabar; aí o webhook (customer.subscription.deleted) derruba pro free. Aqui só guardamos o FLAG
-- "cancelamento agendado" p/ a UI mostrar "acesso até …" + "Reativar" sem chamar o Stripe a cada load.
--
-- Aplicar como postgres, DEPOIS do 0092. Depende de 0052 (tenant_cobranca) e 0070 (padrão de guard
-- por auth.uid em função SECURITY DEFINER concedida a authenticated).

begin;

-- Flag espelhado do Stripe (Subscription.cancel_at_period_end). Default false = renova normalmente.
alter table public.tenant_cobranca
  add column if not exists cancel_at_period_end boolean not null default false;

-- Grava o agendamento de cancelamento. Dois chamadores legítimos:
--   • caminho AUTENTICADO (espelho otimista logo após o modify no Stripe) → roda como authenticated,
--     auth.uid() = o próprio tenant;
--   • WEBHOOK (customer.subscription.updated reflete cancel_at_period_end) → roda como cria_app, SEM
--     JWT, auth.uid() NULL.
-- Guard (A1, ver 0070): se HÁ usuário autenticado, ele só pode mexer no PRÓPRIO tenant (anti-forja
-- cross-tenant via PostgREST/Path B). auth.uid() NULL = webhook/cria_app → liberado.
create or replace function public.cobranca_set_cancelamento(p_tenant uuid, p_cancel boolean)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if (select auth.uid()) is not null and (select auth.uid()) is distinct from p_tenant then
    raise exception
      'cobranca_set_cancelamento: p_tenant (%) deve ser o proprio tenant', p_tenant
      using errcode = 'insufficient_privilege';
  end if;
  update public.tenant_cobranca
     set cancel_at_period_end = coalesce(p_cancel, false)
   where tenant_id = p_tenant;
end; $$;
alter function public.cobranca_set_cancelamento(uuid, boolean) owner to postgres;
revoke all on function public.cobranca_set_cancelamento(uuid, boolean) from public, anon;
grant execute on function public.cobranca_set_cancelamento(uuid, boolean) to authenticated, cria_app;

commit;
