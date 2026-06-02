# CRIA API — imagem de produção para o EasyPanel.
#
# IMPORTANTE (monorepo): o contexto de build é a RAIZ do repo (o EasyPanel constrói a
# partir da raiz). Por isso os COPY são relativos a `backend/`.
# Build local:  docker build -f backend/Dockerfile -t cria-api .   (rodando na raiz do repo)
# No EasyPanel: Build = Dockerfile, File = backend/Dockerfile.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Camada de dependências (cacheável): só requirements.txt antes do código.
COPY backend/requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Código da aplicação.
COPY backend/app ./app

# Usuário não-root.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# Health check usa o endpoint da API.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health')" || exit 1

# --proxy-headers + --forwarded-allow-ips: o Traefik do EasyPanel faz a terminação TLS,
# então o uvicorn precisa confiar nos headers X-Forwarded-* do proxy.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
