# CRIA — Painel web (arquiteto)

SPA em **Vite + React + TypeScript**, **Tailwind + shadcn/ui** (tema dark/âmbar do protótipo).
Consome **só a API Python** (FastAPI) — inclusive auth: login/sessão/refresh vão pela API e a
sessão vive em **cookie httpOnly** (BFF), fora do alcance de XSS. O front não fala direto com o
Supabase; o token CSRF (double-submit) é reenviado no header `X-CSRF-Token` nas mutações.

## Rodar local

```bash
cd web
npm install
cp .env.example .env.local   # preencha VITE_API_BASE_URL
npm run dev                  # http://localhost:5173
```

> Precisa do backend rodando (default `http://localhost:8000`) e de um usuário para logar.
> `npm run build` faz typecheck (`tsc --noEmit`) + build de produção.

## Estrutura

```
src/
  app/        # router + AppShell (topbar mobile-first) + ProtectedRoute
  auth/       # AuthProvider (sessão via BFF/cookie) + bff (cliente dos endpoints de auth) + useAuth
  components/
    ui/       # primitivos shadcn-style tematizados (button, input, card, dialog, label)
    brand/    # Wordmark
    feedback/ # estados de loading / vazio / erro
  features/
    auth/     # LoginPage
    obras/    # lista + criar (consome a API real)
  lib/        # api (fetch+cookie+CSRF+refresh+problem+json), env, utils(cn), uuid
  index.css   # tema (CSS vars dark-first) + base
```

## Princípios (herdados do produto)

- **Dark-first** + identidade preto/âmbar (Oswald display + Outfit corpo).
- **Mobile-first**: a maioria acessa pelo celular (inclusive o painel). Desenhar do 390px pra cima.
- **Poka-yoke**: erro impossível na entrada (selects, toggles, validação inline), fricção
  proporcional ao risco (criar = leve; destrutivo = confirmação séria), nunca uma tela morta
  (sempre estados de vazio/carregando/erro).
- **API-only**: nada de query direta ao Postgres pelo browser; só a API Python.
- O **soft-limit** do backend (RFC 9457 `problem+json`) vira CTA de upgrade no front (ver `lib/api.ts`).
