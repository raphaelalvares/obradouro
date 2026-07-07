"""Testes da DURABILIDADE do export (reaper + claim idempotente) — sem DB/storage: monkeypatch nas
bordas (claim, coletar, storage, set_status) para exercitar só a lógica de guarda/reprocesso."""

import pytest

from app.services import export


# ------------------------------------------------------------------- fakes de sessão/storage
class _FakeResult:
    def scalar(self):
        return "01/01/2026 10:00"

    def first(self):
        return None

    def all(self):
        return []


class _Begin:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    """Sessão de DB falsa: engole qualquer execute e devolve um result inócuo (o processar só usa o
    to_char(now()) → .scalar(), e o actor_name → .first())."""

    async def execute(self, *a, **k):
        return _FakeResult()

    def begin(self):
        return _Begin()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeStorage:
    def __init__(self):
        self.guardadas: list[tuple[str, bytes, str]] = []

    async def recuperar(self, key):  # noqa: ARG002
        raise FileNotFoundError

    async def guardar(self, key, data, content_type):
        self.guardadas.append((key, data, content_type))


@pytest.fixture(autouse=True)
def _limpa_em_voo():
    export._EM_VOO.clear()
    yield
    export._EM_VOO.clear()


def _mock_worker(monkeypatch, *, claim: bool, set_status: list):
    """Prepara processar() para rodar sem DB: SessionLocal falso, coletar vazio, storage fake, e
    _claim/_set_status controlados. Retorna o storage fake."""
    storage = _FakeStorage()
    monkeypatch.setattr(export, "SessionLocal", lambda: _FakeSession())

    async def _fake_claim(claims, job_id):  # noqa: ARG001
        return claim

    async def _fake_coletar(session):  # noqa: ARG001
        return [], []

    async def _fake_set_status(claims, job_id, **campos):  # noqa: ARG001
        set_status.append(campos)

    monkeypatch.setattr(export, "_claim", _fake_claim)
    monkeypatch.setattr(export, "_coletar", _fake_coletar)
    monkeypatch.setattr(export, "_set_status", _fake_set_status)
    monkeypatch.setattr(export, "get_storage", lambda: storage)
    return storage


# ------------------------------------------------------------------- processar (idempotência)
async def test_processar_sem_claim_nao_faz_trabalho(monkeypatch):
    # perdeu o claim (outro pegou / não reprocessável / estourou tentativas) → nada de storage.
    status: list = []
    storage = _mock_worker(monkeypatch, claim=False, set_status=status)

    coletou = False

    async def _boom(session):  # não deve nem ser chamado
        nonlocal coletou
        coletou = True
        return [], []

    monkeypatch.setattr(export, "_coletar", _boom)

    await export.processar("job-1", {"sub": "tenant-x", "email": None})

    assert coletou is False
    assert storage.guardadas == []
    assert status == []
    assert "job-1" not in export._EM_VOO


async def test_processar_em_voo_pula(monkeypatch):
    # já rodando NESTE processo → nem tenta o claim (guard barato contra double-run).
    chamou_claim = False

    async def _claim_espiao(claims, job_id):  # noqa: ARG001
        nonlocal chamou_claim
        chamou_claim = True
        return True

    monkeypatch.setattr(export, "_claim", _claim_espiao)
    export._EM_VOO.add("job-1")

    await export.processar("job-1", {"sub": "tenant-x", "email": None})

    assert chamou_claim is False


async def test_processar_ok_marca_pronto_e_grava_chave_deterministica(monkeypatch):
    status: list = []
    storage = _mock_worker(monkeypatch, claim=True, set_status=status)

    await export.processar("job-1", {"sub": "tenant-x", "email": None})

    # chave é determinística (sub == tenant_id): inline e reaper gravam a MESMA → sem órfão.
    assert len(storage.guardadas) == 1
    assert storage.guardadas[0][0] == "exports/tenant-x/job-1.zip"
    assert status and status[-1]["status"] == "pronto"
    assert "job-1" not in export._EM_VOO  # liberado no finally


async def test_processar_erro_marca_erro_e_libera(monkeypatch):
    status: list = []
    _mock_worker(monkeypatch, claim=True, set_status=status)

    async def _coletar_explode(session):  # noqa: ARG001
        raise RuntimeError("falha ao coletar")

    monkeypatch.setattr(export, "_coletar", _coletar_explode)

    await export.processar("job-1", {"sub": "tenant-x", "email": None})

    assert status and status[-1]["status"] == "erro"
    assert "falha ao coletar" in status[-1]["erro"]
    assert "job-1" not in export._EM_VOO  # liberado mesmo em erro


# ------------------------------------------------------------------- reaper
async def test_redirecionar_travados_isola_falha(monkeypatch):
    # dois travados; o 1º explode → o 2º ainda é tentado e o lote não aborta.
    async def _fake_travados():
        return [("job-1", "tenant-a"), ("job-2", "tenant-b")]

    tentados: list[str] = []

    async def _fake_processar(job_id, claims):  # noqa: ARG001
        tentados.append(job_id)
        if job_id == "job-1":
            raise RuntimeError("boom")

    monkeypatch.setattr(export, "_jobs_travados", _fake_travados)
    monkeypatch.setattr(export, "processar", _fake_processar)

    n = await export.redirecionar_travados()

    assert n == 2
    assert tentados == ["job-1", "job-2"]


async def test_reaper_tick_compoe_falhar_e_redisparar(monkeypatch):
    async def _fake_falhar():
        return 2

    async def _fake_redisparar():
        return 3

    monkeypatch.setattr(export, "_falhar_excedidos", _fake_falhar)
    monkeypatch.setattr(export, "redirecionar_travados", _fake_redisparar)

    assert await export.reaper_tick() == (2, 3)
