# Versionamento da API

## Por que importa

Os apps Flutter são instalados no dispositivo e o usuário atualiza **devagar** (lag da loja).
O backend **não pode quebrar clientes antigos** ao evoluir. Por isso a API é versionada por
caminho desde o início.

## Convenção

- **Prefixo de versão no path:** `/api/v1/...` (configurável em `API_V1_PREFIX`).
- Toda rota nova entra sob a versão atual (`v1`).
- **Mudança compatível** (campo novo opcional, rota nova): fica em `v1`.
- **Mudança incompatível** (remover/renomear campo, mudar tipo/semântica): cria-se `v2`,
  mantendo `v1` no ar até a base de apps antigos cair a um nível aceitável.
- **Nunca** remover/alterar de forma quebrando um endpoint já publicado em uma versão viva.

## Estrutura no código

```
backend/app/api/
  v1/
    router.py            # agrega os routers da v1
    routes/
      health.py          # /api/v1/health
      ...                # cada recurso vira um módulo aqui
```

Uma futura `v2` seria `backend/app/api/v2/` incluída em paralelo no `main.py`.

## Boas práticas adicionais

- **Descoberta de versão mínima (futuro):** um endpoint leve (ex.: `/api/v1/health` ou um
  `/api/meta`) pode informar a versão mínima de app suportada, para o app avisar o usuário a
  atualizar quando necessário.
- **OpenAPI:** o schema é exposto em `/api/v1/openapi.json` e a doc interativa em `/docs`.
