// Modelo do gráfico de Gantt a partir da árvore do checklist (etapas + tarefas com datas).
// Tudo em "YYYY-MM-DD" (dias corridos, inclusivos). Posições em PORCENTAGEM da janela total,
// para a faixa de tempo escalar sozinha: no celular ela tem min-width e ROLA; na impressão
// vira 100% e CABE na página (paisagem). Reaproveita a aritmética de datas de cronograma.ts.

import { addDays, duracaoDias } from "@/features/checklist/cronograma"
import {
  contagemEtapa,
  folhasDe,
  progressoFolha,
  tarefasDaEtapa,
  type Etapa,
  type Item,
} from "@/features/checklist/checklistApi"

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
  /** avanço 0..1 (medição do diário ou binário do estado); null quando não há folhas a medir. */
  progresso: number | null
  status: GanttStatus
  /** tarefa bloqueada por dependência (predecessor não-concluído). Etapas: sempre false. */
  bloqueada: boolean
  /** equipe responsável (só nas tarefas; etapas = null) — pinta o chip / filtra o Gantt. */
  equipe_id: string | null
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
  /** avanço 0..1 da obra toda (ponderado pelas medições do diário); null se não há nada a medir. */
  progressoGeral: number | null
}

/** progresso (0..1) das folhas de uma lista de tarefas: média do avanço de cada folha (medição do
 * diário se houver, senão o binário do estado); null se não houver folhas. */
function progressoDeTarefas(tarefas: Item[]): number | null {
  const fs = folhasDe(tarefas)
  if (fs.length === 0) return null
  return fs.reduce((s, f) => s + progressoFolha(f), 0) / fs.length
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
  let unidadesTotal = 0
  let unidadesFeitas = 0

  for (const e of etapas) {
    // % geral (independe das datas): etapa SEM filhos = 1 unidade (feita se concluida); senão conta
    // as FOLHAS (sub-itens / tarefa-folha) MAIS cada subetapa-marco (1 unidade) via contagemEtapa —
    // assim subetapa-marco concluída entra no progresso (não some por não ter tarefas).
    const tarefasEtapa = tarefasDaEtapa(e)
    if (e.sem_itens) {
      unidadesTotal += 1
      if (e.concluida) unidadesFeitas += 1
    } else {
      const c = contagemEtapa(e)
      unidadesTotal += c.total
      unidadesFeitas += c.progresso * c.total // avanço ponderado (medições do diário)
    }

    // tarefas DESENHÁVEIS: precisam das duas datas p/ virar barra.
    const tarefas = tarefasEtapa.filter(
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
      // marco (etapa sem tarefas) concluído SEM datas: vira um ponto na data de conclusão (ou
      // hoje, no otimismo antes do servidor) p/ aparecer verde no Gantt.
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
      // etapa COM filhos: deriva das folhas + subetapas-marco (contagemEtapa) — sem check manual.
      // Avanço ponderado (medições do diário); a barra só fica verde com TUDO a 100%.
      const c = contagemEtapa(e)
      progEtapa = c.total > 0 ? c.progresso : null
      statusEtapa = statusDe(fim, progEtapa, hoje)
    } else if (e.concluida) {
      // etapa SEM tarefas (marco): a conclusão é o check manual.
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
      bloqueada: false,
      equipe_id: null,
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
        bloqueada: t.bloqueada,
        equipe_id: t.equipe_id,
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
    progressoGeral: unidadesTotal > 0 ? unidadesFeitas / unidadesTotal : null,
  }
}

/** posição (em %) de UMA barra dentro do modelo; null se a barra não tem as duas datas. */
export function barraPos(m: GanttModelo, inicio: string | null, fim: string | null) {
  if (!inicio || !fim) return null
  return posicao(m.min, m.totalDias, inicio, fim)
}
