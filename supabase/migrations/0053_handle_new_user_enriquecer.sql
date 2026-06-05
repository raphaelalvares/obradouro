-- 0053_handle_new_user_enriquecer.sql  (Cadastro/OAuth — o perfil já nasce com nome e telefone)
-- Enriquece o trigger handle_new_user (0001) p/ copiar nome/telefone de raw_user_meta_data ao criar
-- a profile. Cobre o cadastro por e-mail (signUp options.data {nome, telefone}) e o login/cadastro
-- via OAuth (Google/Apple trazem full_name/name do provedor). Continua idempotente e à prova de
-- falha (nunca derruba o signup; erros engolidos). Aplicar como postgres. DEV antes de PROD.

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, email, nome, telefone)
  values (
    new.id,
    new.email,
    nullif(btrim(coalesce(
      new.raw_user_meta_data->>'nome',
      new.raw_user_meta_data->>'full_name',
      new.raw_user_meta_data->>'name',
      ''
    )), ''),
    nullif(btrim(coalesce(
      new.raw_user_meta_data->>'telefone',
      new.raw_user_meta_data->>'phone',
      ''
    )), '')
  )
  on conflict (id) do nothing;
  return new;
exception
  when others then
    -- nunca derruba o signup, mas deixa rastro (profile que não nasceu fica visível no log)
    raise warning 'handle_new_user falhou para %: %', new.id, sqlerrm;
    return new;
end;
$$;

alter function public.handle_new_user() owner to postgres;
-- O trigger on_auth_user_created (0001) já aponta para esta função; NÃO recriar o trigger.
