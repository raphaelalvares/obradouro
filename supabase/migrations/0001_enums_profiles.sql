-- 0001_enums_profiles.sql  (Fase 1 — espinha)
-- Enums de domínio, tabela profiles (identidade global 1:1 com auth.users) e o
-- trigger handle_new_user (rede de segurança no signup).
-- Aplicar como postgres (SQL Editor / db push). DEV antes de PROD.

-- Extensões (citext já vem do 0000_baseline; idempotente)
create extension if not exists citext;
create extension if not exists pgcrypto;

-- Enums (domínios estáveis na Fase 1; ver risco "enum vs lookup" no design)
create type public.papel_obra    as enum ('arquiteto', 'cliente', 'prestador');
create type public.estado_membro as enum ('pendente', 'ativo');
create type public.status_obra   as enum ('ativa', 'arquivada');

-- profiles: PK = auth.users.id (o sub do JWT). SEM CPF (minimização LGPD).
-- Identidade GLOBAL e reutilizável: tenant e papel NÃO ficam aqui (vivem em obra_membros).
create table public.profiles (
  id          uuid        primary key references auth.users(id) on delete cascade,
  email       citext      not null unique,
  nome        text,
  telefone    text,
  created_by  uuid        references public.profiles(id) on delete set null,  -- só histórico
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create trigger trg_profiles_updated_at
  before update on public.profiles
  for each row execute function public.set_updated_at();

-- Rede de segurança: ao nascer um usuário em auth.users, cria a linha mínima em profiles.
-- O backend é dono do conteúdo (faz UPSERT logo após a Admin API). Ambos idempotentes.
-- NUNCA derrubar o signup: erros são engolidos.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, email)
  values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
exception
  when others then
    return new;
end;
$$;

alter function public.handle_new_user() owner to postgres;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
