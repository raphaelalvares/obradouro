-- 0106_reguas_planos.sql  (Monetização — régua de 3 planos: Canteiro / Alicerce / Mestre)
--
-- Só DADOS: o motor de planos (catálogo public.planos + plano_do_tenant/plano_limite/plano_flag,
-- triggers de obras_ativas 0021 e armazenamento_mb 0042) já existe. Aqui a gente (a) semeia o 3º
-- plano, (b) retuna limites/flags/preço dos três e (c) introduz a flag NOVA 'portal'.
--
--   codigo     nome        obras  armaz_mb  export_pdf  logo   chat   portal  historico   preço
--   free       Canteiro      1       500      false     false  false  false   false       R$   0
--   alicerce   Alicerce      5      5120(5G)  true      true   false  false   false       R$  59
--   pro        Mestre       -1     51200(50G) true      true   true   true    true        R$ 179
--
-- Notas:
--  * -1 = ilimitado. TODAS as chaves presentes em cada linha — como 'limites'/'flags' é substituído
--    inteiro, OMITIR uma chave a zera (armazenamento_mb ausente = 0 = bloqueia todo upload!).
--  * codigos 'free'/'pro' são ESTÁVEIS (o webhook do Stripe e o fallback STRIPE_PRICE_PRO referem
--    'pro'); só o NOME muda p/ a marca. 'alicerce' é novo.
--  * 'portal' é flag nova: o cliente entrar no portal (convite por e-mail) é exclusivo do Mestre.
--    plano_flag() já devolve false p/ chave ausente, então quem não tiver a chave fica bloqueado —
--    mas semeamos explícito nos três p/ o catálogo do painel admin listar certo.
--  * 'chat' (assistente IA) passa a ser enforçado por-tenant (antes era só flag global de env).
--  * preco_mensal alimenta o MRR do painel admin (antes 'pro' era NULL → receita zerada).
--  * stripe_price_id NÃO é tocado aqui: crie 2 Stripe Prices (Alicerce e Mestre) e cole os IDs pelo
--    painel admin (Catálogo de planos) ou por UPDATE — sem isso o plano não aparece p/ assinar.
--  * Downgrade é grandfathering: quem cair de plano MANTÉM o que já criou acima do teto; só a
--    próxima criação/reativação bloqueia (comportamento do trigger 0021, inalterado).

insert into public.planos (codigo, nome, limites, flags, ordem, preco_mensal) values
  ('free', 'Canteiro',
   '{"obras_ativas": 1,  "revisoes_projeto": 3,  "armazenamento_mb": 500}'::jsonb,
   '{"export_pdf": false, "logo": false, "chat": false, "portal": false, "historico": false}'::jsonb,
   0, 0),
  ('alicerce', 'Alicerce',
   '{"obras_ativas": 5,  "revisoes_projeto": -1, "armazenamento_mb": 5120}'::jsonb,
   '{"export_pdf": true,  "logo": true,  "chat": false, "portal": false, "historico": false}'::jsonb,
   5, 59),
  ('pro', 'Mestre',
   '{"obras_ativas": -1, "revisoes_projeto": -1, "armazenamento_mb": 51200}'::jsonb,
   '{"export_pdf": true,  "logo": true,  "chat": true,  "portal": true,  "historico": true}'::jsonb,
   10, 179)
on conflict (codigo) do update set
  nome         = excluded.nome,
  limites      = excluded.limites,
  flags        = excluded.flags,
  ordem        = excluded.ordem,
  preco_mensal = excluded.preco_mensal;
