# Certificados

## `supabase-ca.crt` — CA raiz do Supabase (TLS verify-full do Postgres)

Em produção o backend conecta no Postgres via **Session Pooler** do Supabase, que apresenta um
certificado emitido pela **CA própria do Supabase** (não está no trust store do SO). Para fazer
`verify-full` (validar cadeia + hostname) é preciso fornecer essa CA.

### Como obter

1. Supabase → **Project Settings → Database → SSL Configuration**.
2. Clique em **Download certificate** (vem um arquivo tipo `prod-ca-2021.crt`).
3. Salve o conteúdo **exatamente** como `backend/certs/supabase-ca.crt` (este diretório).
4. Commite o arquivo. **Não é segredo** — é uma CA pública; pode ir pro git.

### Como é usado

- O [Dockerfile](../Dockerfile) faz `COPY backend/certs ./certs` → o cert vira `/app/certs/supabase-ca.crt`.
- A env **`DB_SSL_ROOT_CERT=/app/certs/supabase-ca.crt`** (no EasyPanel) liga o `verify-full`
  (ver [app/core/database.py](../app/core/database.py) `_ssl_arg`).
- Sem `DB_SSL_ROOT_CERT`, o TLS verifica contra o trust store do SO (falha com a CA do Supabase).

> ⚠️ O `COPY backend/certs ./certs` **exige** que `supabase-ca.crt` exista no momento do build.
> Adicione o cert no **mesmo commit** das mudanças, senão o build do EasyPanel falha.
> (Este `README.md` é ignorado pelo Docker via `.dockerignore` — só o `.crt` entra na imagem.)
