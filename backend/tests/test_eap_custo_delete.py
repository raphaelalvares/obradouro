"""Simetria do custo no delete da EAP (sem banco, fake session): ao excluir a ÚLTIMA folha de um
pai, o custo empurrado pra baixo é DEVOLVIDO ao pai (_mover_custo folha→pai); com irmãos, não. Testa
o branching de `_devolver_custo_no_delete` (o P0 "custo some ao excluir o único filho")."""

import asyncio
import uuid

from app.services.checklist import _CUSTO_COLS, _devolver_custo_no_delete


class _Row:
    """Linha com ._mapping (o que _mover_custo lê) e atributos (o que os .first() truthy usam)."""

    def __init__(self, mapping):
        self._mapping = mapping


class _Res:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None


class _SeqSession:
    def __init__(self, fila):
        self.execs: list[tuple[str, dict | None]] = []
        self._fila = list(fila)

    async def execute(self, stmt, params=None):
        self.execs.append((str(stmt), params))
        return _Res(self._fila.pop(0) if self._fila else [])


def _com_custo() -> dict:
    """_mapping de uma folha COM custo (todas as _CUSTO_COLS setadas)."""
    return {c: (1000.0 if c == "custo_total" else 1.0) for c in _CUSTO_COLS}


def test_ultima_subtarefa_devolve_custo_ao_pai():
    """Sub-tarefa sem irmãos → a Tarefa-pai volta a ser folha e RECUPERA o custo da subtarefa."""
    child, parent, etapa = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    fila = [
        [],               # sibling check: nenhuma outra subtarefa
        [_Row(_com_custo())],  # _mover_custo: SELECT do custo da folha (child)
        [],               # _mover_custo: UPDATE destino (parent)
        [],               # _mover_custo: UPDATE origem = null (child)
    ]
    s = _SeqSession(fila)
    asyncio.run(
        _devolver_custo_no_delete(
            s, item_id=child, etapa_id=etapa, subetapa_id=None, parent_item_id=parent
        )
    )
    # devolveu: UPDATE no pai com o custo (where c = parent) e zerou o filho (where p = child).
    updates_destino = [p for sql, p in s.execs if "= :custo_total" in sql]
    assert updates_destino and updates_destino[0]["c"] == str(parent)
    updates_null = [p for sql, p in s.execs if "custo_total = null" in sql]
    assert updates_null and updates_null[0]["p"] == str(child)


def test_subtarefa_com_irmao_nao_devolve():
    """Sub-tarefa com irmã → o pai continua agregador; NÃO devolve custo (nada de _mover_custo)."""
    child, parent, etapa = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    s = _SeqSession([[_Row({"x": 1})]])  # sibling check acha uma irmã
    asyncio.run(
        _devolver_custo_no_delete(
            s, item_id=child, etapa_id=etapa, subetapa_id=None, parent_item_id=parent
        )
    )
    assert len(s.execs) == 1  # só o sibling check
    assert not any("custo_total = null" in sql for sql, _ in s.execs)


def test_tarefa_direta_esvazia_etapa_devolve_custo():
    """Tarefa direta, sem subetapa nem outra tarefa direta → etapa vira folha e recupera o custo."""
    item, etapa = uuid.uuid4(), uuid.uuid4()
    fila = [
        [],               # sem subetapas na etapa
        [],               # sem outra tarefa direta
        [_Row(_com_custo())],  # _mover_custo: custo da folha (item)
        [],               # UPDATE etapa (destino)
        [],               # UPDATE item = null
    ]
    s = _SeqSession(fila)
    asyncio.run(
        _devolver_custo_no_delete(
            s, item_id=item, etapa_id=etapa, subetapa_id=None, parent_item_id=None
        )
    )
    destino = [p for sql, p in s.execs if "update public.etapas" in sql and "= :custo_total" in sql]
    assert destino and destino[0]["c"] == str(etapa)


def test_tarefa_direta_com_subetapa_na_etapa_nao_devolve():
    """Se a etapa ainda tem uma subetapa, ela NÃO volta a ser folha → sem devolução de custo."""
    item, etapa = uuid.uuid4(), uuid.uuid4()
    s = _SeqSession([[_Row({"x": 1})]])  # existe subetapa na etapa
    asyncio.run(
        _devolver_custo_no_delete(
            s, item_id=item, etapa_id=etapa, subetapa_id=None, parent_item_id=None
        )
    )
    assert len(s.execs) == 1
    assert not any("custo_total = null" in sql for sql, _ in s.execs)
