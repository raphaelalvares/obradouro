// Modelo do gráfico de Gantt a partir da árvore do checklist (etapas + tarefas com datas).
// Tudo em "YYYY-MM-DD" (dias corridos, inclusivos). Posições em PORCENTAGEM da janela total,
// para a faixa de tempo escalar sozinha: no celular ela tem min-width e ROLA; na impressão
// vira 100% e CABE na página (paisagem). Reaproveita a aritmética de datas de cronograma.ts.

import { addDays, duracaoDias } from "@/features/checklist/cronograma"
import type { Etapa, Item } from "@/features/checklist/checklistApi"

const MES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

function primeiroDiaMes(iso: string): string {
  return `${iso.slice(0, 7)}-01`
}
function proximoMes(iso: string): string {
  let [y, m] = iso.slice(0, 7).split("-").map(Number)
  m += 1
  if (m > 12) {
    m = 1
    y += 1
  }
  return `${y}-${String(m).padStart(2, "0")}-01`
}

/** "YYYY-MM-DD" de hoje (local). Usado p/ derivar atraso e gatear a tela do Gantt. */
export function hojeISO(): string {
  const d = new Date()
  const m = String(d.getMonth() + 1).padStart(2, "0")
  const dia = String(d.getDate()).padStart(2, "0")
  return `${d.getFullYear()}-${m}-${dia}`
}

// Situação derivada (sem campo novo no backend): verde = concluído; vermelho = atrasado (venceu e o
// checklist não fechou — só dá p/ afirmar quando HÁ checklist); âmbar = previsto/andamento.
export type GanttStatus = "concluido" | "atrasado" | "normal"

function statusDe(fim: string | null, progresso: number | null, hoje: string): GanttStatus {
  if (progresso === null) return "normal" // sem sub-itens → não dá p/ afirmar conclusão/atraso
  if (progresso >= 1) return "concluido"
  if (fim && fim < hoje) return "atrasado"
  return "normal"
}

export interface GanttRow {
  id: string
  kind: "etapa" | "tarefa"
  nome: string
  seq: number | null
  inicio: string | null
  fim: string | null
  /** 0..1 dos sub-itens concluídos; null quando não há sub-itens (nada a medir). */
  progresso: number | null
  status: GanttStatus
}

export interface GanttSegmento {
  label: string
  leftPct: number
  widthPct: number
}

export interface GanttModelo {
  rows: GanttRow[]
  min: string
  max: string
  totalDias: number
  meses: GanttSegmento[]
  /** leftPct de cada divisa de semana (a cada 7 dias a partir do início), exclui 0 e 100. */
  semanas: number[]
  hojeLeftPct: number | null
  /** 0..1 dos sub-itens concluídos na obra toda; null se não há sub-itens. */
  progressoGeral: number | null
}

/** progresso (0..1) dos sub-itens de uma lista de tarefas; null se não houver sub-itens. */
function progressoDeTarefas(tarefas: Item[]): number | null {
  let total = 0
  let feitos = 0
  for (const t of tarefas) {
    for (const s of t.subitens) {
      total += 1
      if (s.estado === "concluido") feitos += 1
    }
  }
  return total > 0 ? feitos / total : null
}

/** offset/largura em % da janela [min..max] para um intervalo [inicio..fim]. */
function posicao(min: string, totalDias: number, inicio: string, fim: string) {
  const offset = duracaoDias(min, inicio) - 1 // dias antes do início da barra
  const largura = duracaoDias(inicio, fim)
  return {
    leftPct: (offset / totalDias) * 100,
    widthPct: (largura / totalDias) * 100,
  }
}

/** Monta o modelo do Gantt; retorna null quando não há nenhuma data preenchida. */
export function montarGantt(etapas: Etapa[], hoje: string): GanttModelo | null {
  const rows: GanttRow[] = []
  const datas: string[] = []
  let subTotal = 0
  let subFeitos = 0

  for (const e of etapas) {
    // sub-itens da obra inteira (p/ o % geral) — independe das datas.
    for (const t of e.itens) {
      for (const s of t.subitens) {
        subTotal += 1
        if (s.estado === "concluido") subFeitos += 1
      }
    }

    // tarefas DESENHÁVEIS: precisam das duas datas p/ virar barra.
    const tarefas = e.itens.filter(
      (t): t is Item & { data_inicio: string; data_fim: string } =>
        !!t.data_inicio && !!t.data_fim,
    )

    // Span da etapa derivado SÓ do que é visível: a barra-resumo bate com as tarefas e a janela
    // do gráfico nunca estica por uma data que não vira barra. Etapa sem tarefas agendadas usa as
    // datas próprias — exigindo as duas p/ desenhar.
    let inicio: string | null = null
    let fim: string | null = null
    if (tarefas.length > 0) {
      inicio = tarefas.reduce((a, t) => (t.data_inicio < a ? t.data_inicio : a), tarefas[0].data_inicio)
      fim = tarefas.reduce((a, t) => (t.data_fim > a ? t.data_fim : a), tarefas[0].data_fim)
    } else if (e.data_inicio && e.data_fim) {
      inicio = e.data_inicio
      fim = e.data_fim
    } else if (e.sem_itens && e.concluida) {
      // marco concluído SEM datas: vira um ponto na data de conclusão (ou hoje, no otimismo antes
      // do servidor responder). Garante que o marco concluído apareça (verde) no Gantt.
      const d = e.concluida_em ? e.concluida_em.slice(0, 10) : hoje
      inicio = d
      fim = d
    } else {
      continue // nada agendado e desenhável nesta etapa
    }

    datas.push(inicio, fim)
    // etapa SEM tarefas: a conclusão é o marco manual (e.concluida) — não há checklist p/ derivar.
    // etapa COM tarefas: deriva do checklist (subitens), como as tarefas.
    let progEtapa: number | null
    let statusEtapa: GanttStatus
    if (!e.sem_itens) {
      progEtapa = progressoDeTarefas(e.itens)
      statusEtapa = statusDe(fim, progEtapa, hoje)
    } else if (e.concluida) {
      progEtapa = 1
      statusEtapa = "concluido"
    } else if (fim && fim < hoje) {
      progEtapa = null
      statusEtapa = "atrasado"
    } else {
      progEtapa = null
      statusEtapa = "normal"
    }
    rows.push({
      id: e.id,
      kind: "etapa",
      nome: e.nome,
      seq: e.seq_humano,
      inicio,
      fim,
      progresso: progEtapa,
      status: statusEtapa,
    })
    for (const t of tarefas) {
      const progT = progressoDeTarefas([t])
      rows.push({
        id: t.id,
        kind: "tarefa",
        nome: t.nome,
        seq: t.seq_humano,
        inicio: t.data_inicio,
        fim: t.data_fim,
        progresso: progT,
        status: statusDe(t.data_fim, progT, hoje),
      })
    }
  }

  if (datas.length === 0) return null

  const min = datas.reduce((a, b) => (b < a ? b : a))
  const max = datas.reduce((a, b) => (b > a ? b : a))
  const totalDias = duracaoDias(min, max)

  // segmentos de mês (cada um recortado à janela visível) p/ os rótulos + divisas mais fortes
  const meses: GanttSegmento[] = []
  let cursor = primeiroDiaMes(min)
  while (cursor <= max) {
    const fimMes = addDays(proximoMes(cursor), -1)
    const segInicio = cursor < min ? min : cursor
    const segFim = fimMes > max ? max : fimMes
    const { leftPct, widthPct } = posicao(min, totalDias, segInicio, segFim)
    const [y, m] = cursor.split("-")
    meses.push({ label: `${MES[Number(m) - 1]}/${y.slice(2)}`, leftPct, widthPct })
    cursor = proximoMes(cursor)
  }

  // divisas de semana (a cada 7 dias) — dão a leitura "semanal" sem poluir com rótulos
  const semanas: number[] = []
  for (let d = 7; d < totalDias; d += 7) semanas.push((d / totalDias) * 100)

  const hojeLeftPct =
    hoje >= min && hoje <= max ? (posicao(min, totalDias, hoje, hoje).leftPct as number) : null

  return {
    rows,
    min,
    max,
    totalDias,
    meses,
    semanas,
    hojeLeftPct,
    progressoGeral: subTotal > 0 ? subFeitos / subTotal : null,
  }
}

/** posição (em %) de UMA barra dentro do modelo; null se a barra não tem as duas datas. */
export function barraPos(m: GanttModelo, inicio: string | null, fim: string | null) {
  if (!inicio || !fim) return null
  return posicao(m.min, m.totalDias, inicio, fim)
}
