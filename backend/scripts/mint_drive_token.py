"""Gera o refresh token do Google Drive e cria a pasta-raiz do storage. RODE UMA VEZ, localmente.

Contexto: o backend usa o Google Drive como storage agindo COMO você (a conta dona dos 5 TB), via um
refresh token offline — não é service account (que teria cota própria e não usaria seu Google One).
Ver app/services/storage/drive.py. Escopo drive.file: a app só acessa o que ela cria, então a
pasta-raiz é criada aqui (por isso o script devolve o id dela).

Pré-requisitos (no Google Cloud Console, tudo grátis):
  1. Crie um projeto (qualquer nome).
  2. APIs e serviços → Biblioteca → ative a "Google Drive API".
  3. Tela de permissão OAuth: tipo "Externo"; em "Usuários de teste" adicione o SEU e-mail
     (pode ficar em modo "Testing" — é só você, não precisa verificação/publicação).
  4. Credenciais → Criar credenciais → ID do cliente OAuth → tipo "APP PARA COMPUTADOR" (Desktop).
     (Desktop libera o redirect de loopback http://localhost:PORT sem você registrar nada.)
  5. Copie o Client ID e o Client secret.

Como rodar (na raiz do repo):
  GOOGLE_DRIVE_CLIENT_ID=xxx GOOGLE_DRIVE_CLIENT_SECRET=yyy \
    backend/.venv/Scripts/python.exe backend/scripts/mint_drive_token.py
  (ou rode sem env que ele pergunta os dois no terminal.)

O navegador abre pra você autorizar com a conta dos 5 TB. No fim, o script imprime as 4 variáveis
(CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN, ROOT_FOLDER_ID) prontas pra colar no ambiente do backend
(EasyPanel/.env) junto com STORAGE_BACKEND=drive. Guarde REFRESH_TOKEN e CLIENT_SECRET como segredo.
"""

import http.server
import json
import os
import socket
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser

SCOPE = "https://www.googleapis.com/auth/drive.file"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
FILES_URL = "https://www.googleapis.com/drive/v3/files"
FOLDER_MIME = "application/vnd.google-apps.folder"
ROOT_NAME = "Obra D'Ouro — Storage"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _capture_code(port: int) -> str:
    """Sobe um servidor de loopback e espera o Google redirecionar com ?code=..."""
    holder: dict[str, str] = {}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(q)
            holder["code"] = (params.get("code") or [""])[0]
            holder["error"] = (params.get("error") or [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Erro: " + holder["error"] if holder.get("error") else "Autorizado! Pode fechar."
            self.wfile.write(f"<html><body><h2>{msg}</h2></body></html>".encode())
            done.set()

        def log_message(self, *_args):  # silencia o log do servidor
            return

    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    done.wait(timeout=300)
    server.shutdown()
    if holder.get("error"):
        sys.exit(f"Autorização negada: {holder['error']}")
    if not holder.get("code"):
        sys.exit("Não recebi o código de autorização (timeout).")
    return holder["code"]


def _post_form(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(req) as r:  # noqa: S310 (URL fixa do Google)
        return json.loads(r.read())


def _create_root_folder(access_token: str) -> str:
    body = json.dumps({"name": ROOT_NAME, "mimeType": FOLDER_MIME}).encode()
    req = urllib.request.Request(
        FILES_URL + "?fields=id",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:  # noqa: S310
        return json.loads(r.read())["id"]


def main() -> None:
    client_id = os.environ.get("GOOGLE_DRIVE_CLIENT_ID") or input("Client ID: ").strip()
    client_secret = (
        os.environ.get("GOOGLE_DRIVE_CLIENT_SECRET") or input("Client secret: ").strip()
    )
    if not client_id or not client_secret:
        sys.exit("Client ID e Client secret são obrigatórios.")

    port = _free_port()
    redirect_uri = f"http://localhost:{port}/"
    auth = AUTH_URL + "?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            "prompt": "consent",  # força o Google a devolver refresh_token mesmo em reautorização
        }
    )
    print("\nAbrindo o navegador para você autorizar com a conta dos 5 TB…")
    print("Se não abrir sozinho, cole esta URL no navegador:\n" + auth + "\n")
    webbrowser.open(auth)

    code = _capture_code(port)
    tokens = _post_form(
        TOKEN_URL,
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    refresh_token = tokens.get("refresh_token")
    access_token = tokens.get("access_token")
    if not refresh_token:
        sys.exit(
            "Não veio refresh_token. Revogue o acesso do app em "
            "https://myaccount.google.com/permissions e rode de novo (prompt=consent)."
        )

    root_id = _create_root_folder(access_token)

    print("\n" + "=" * 68)
    print("PRONTO. Cole estas variáveis no ambiente do backend (e STORAGE_BACKEND=drive):\n")
    print("STORAGE_BACKEND=drive")
    print(f"GOOGLE_DRIVE_CLIENT_ID={client_id}")
    print(f"GOOGLE_DRIVE_CLIENT_SECRET={client_secret}")
    print(f"GOOGLE_DRIVE_REFRESH_TOKEN={refresh_token}")
    print(f"GOOGLE_DRIVE_ROOT_FOLDER_ID={root_id}")
    print("=" * 68)
    print(f"\nPasta-raiz criada no seu Drive: '{ROOT_NAME}' (id {root_id}).")
    print("Guarde REFRESH_TOKEN e CLIENT_SECRET como segredo — nunca no front nem no git.")


if __name__ == "__main__":
    main()
