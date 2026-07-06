-- 0105_remover_stack_codigo_obra.sql  (remove a pilha MORTA de convite/código de OBRA)
--
-- Decisão de produto (auditoria do fluxo do cliente): a camada de "prestadores/equipe" da obra
-- (convite por e-mail + código de obra + gestão de membros da obra) estava 100% morta no front — o
-- card "Prestadores" era só um selo "Em breve" e nada gravava nela. O backend dessa pilha
-- (routes/membros, routes/vinculo, services/{membros,convites,codigo}) já foi removido; esta
-- migration limpa os objetos de banco que ficaram órfãos:
--   * obra_codigos (tabela) — só era escrita/lida pelo services/codigo (removido) e por
--     resgatar_codigo_obra; o cascade derruba as policies (0016/0072), índices e o trigger de
--     updated_at;
--   * resgatar_codigo_obra() (0018) — RPC do resgate, sem chamador;
--   * minhas_obras_pendentes() (0015) — rótulo de convites pendentes, sem chamador.
--
-- FICA intacto: obras/obra_membros e seus papéis (arquiteto/cliente materializado pelo Portal),
-- criar_obra (0018) e as policies de obra_membros. O papel 'prestador' e o estado 'pendente' de
-- obra_membros passam a ser inalcançáveis (nenhum produtor restante), consistente com a remoção —
-- o enum papel_obra NÃO é tocado (o cliente materializado depende dele; dropar custaria mais do que
-- vale). Linhas 'pendente' legadas de prestador (se houver) ficam invisíveis no RLS (não são 'ativo').
--
-- Se "Prestadores" voltar ao roadmap, reintroduzir a pilha limpa. Depende de: 0006/0015/0016/0018/
-- 0072. Aplicar como postgres, após 0104. Idempotente.

begin;

drop function if exists public.resgatar_codigo_obra(text);
drop function if exists public.minhas_obras_pendentes();
drop table    if exists public.obra_codigos cascade;

commit;
